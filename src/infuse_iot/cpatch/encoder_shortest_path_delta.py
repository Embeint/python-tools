#!/usr/bin/env python3

"""Shortest path encoder extended with PATCH_DELTA instructions

Relocating code changes many branch offsets and pointers by the same small amounts. PATCH_DELTA
encodes "COPY N bytes, then add a recently used delta to the next 16 bits" in a single byte.
"""

import bisect
import heapq
import math
from collections import defaultdict

import numpy as np

from infuse_iot.cpatch.encoder_shortest_path import (
    _addr_size,
    _candidate_runs,
    _gap_runs,
    _InstrBuilder,
    _len_hdr_size,
    _patch_copy_size,
    _shortest_path_encode,
)
from infuse_iot.cpatch.instructions import DeltaHistory, Instr, PatchDeltaInstr

# Largest gap between COPY runs that is considered for filling with additions
MAX_DELTA_GAP = 24

# DP states after a COPY run
OUT = 0  # No PATCH or PATCH_DELTA open
IN_PATCH = 1  # PATCH open, last element was a COPY
IN_DELTA = 2  # PATCH_DELTA open, COPY pending in the next element

# Construction actions
END_PATCH = 0
END_DELTA = 1
START_PATCH = 2
START_DELTA = 3
WRITE = 4
ADD = 5
FLUSH = 6


def _delta_copy_size(length: int) -> int:
    """Additional encoded size of a COPY pending in a PATCH_DELTA, beyond the next element header"""
    if length < 15:
        return 0
    if length <= PatchDeltaInstr.MAX_COPY:
        return 1
    extra = max(0, -(-(length - PatchDeltaInstr.MAX_COPY) // PatchDeltaInstr.MAX_COPY))
    length -= extra * PatchDeltaInstr.MAX_COPY
    return 2 * extra + (1 if length >= 15 else 0)


class _DeltaPredictor:
    """Predicted encoded size of an addition, from the delta history of a previous encoding"""

    def __init__(self, additions: list[tuple[int, int]]):
        history = DeltaHistory()
        self.offsets = []
        self.snapshots = [frozenset(history.deltas)]
        for offset, delta in additions:
            history.use(history.find(delta), delta)
            self.offsets.append(offset)
            self.snapshots.append(frozenset(history.deltas))

    def size(self, offset: int, delta: int) -> int:
        snapshot = self.snapshots[bisect.bisect_left(self.offsets, offset)]
        return 1 if delta in snapshot else 3


class _DeltaInstrBuilder(_InstrBuilder):
    def __init__(self, old: bytes, new: bytes):
        super().__init__(new)
        self.old = old
        self.history = DeltaHistory()
        self.delta: list[tuple[int, int, int]] | None = None
        self.pending = 0
        # (new offset, delta) of each addition
        self.additions: list[tuple[int, int]] = []

    def _element(self, addition: int, delta: int):
        assert self.delta is not None
        while self.pending > PatchDeltaInstr.MAX_COPY:
            self.delta.append((PatchDeltaInstr.MAX_COPY, PatchDeltaInstr.NONE, 0))
            self.pending -= PatchDeltaInstr.MAX_COPY
        self.delta.append((self.pending, addition, delta))
        self.pending = 0

    def delta_start(self):
        assert self.patch is None and self.delta is None
        self.delta = []
        self.pending = 0

    def delta_flush(self):
        if self.pending:
            self._element(PatchDeltaInstr.NONE, 0)

    def delta_end(self):
        assert self.delta is not None
        self.delta_flush()
        self.instructions.append(PatchDeltaInstr(self.delta))
        self.delta = None

    def add(self):
        n = self.new_offset
        o = self.old_offset
        delta = (self.new[n] | self.new[n + 1] << 8) - (self.old[o] | self.old[o + 1] << 8)
        delta &= 0xFFFF
        index = self.history.find(delta)
        self._element(PatchDeltaInstr.EXPLICIT if index is None else index, delta)
        self.history.use(index, delta)
        self.additions.append((n, delta))
        self.new_offset += 2
        self.old_offset += 2

    def set_addr(self, addr: int):
        assert self.delta is None
        super().set_addr(addr)

    def write(self, length: int):
        assert self.delta is None
        super().write(length)

    def copy(self, length: int):
        if length <= 0:
            return
        if self.delta is None:
            super().copy(length)
            return
        self.pending += length
        self.new_offset += length
        self.old_offset += length


def _delta_encode(
    bin_old: bytes, bin_new: bytes, runs: set[tuple[int, int, int]], predictor: _DeltaPredictor
) -> tuple[list[Instr], list[tuple[int, int]]]:
    """Minimum size encoding as per `encoder_shortest_path._shortest_path_encode`, with PATCH_DELTA as an option

    Gaps between COPY runs on the same diagonal can be filled with 16 bit additions inside a
    PATCH_DELTA. The size of each addition depends on the delta history, which is predicted.
    """
    N = len(bin_new)
    # Total order, so that the encoding does not depend on set iteration order
    tokens = sorted(runs, key=lambda r: (r[1], r[0], r[2]))
    ts = [0] + [r[0] for r in tokens] + [N]
    te = [0] + [r[1] for r in tokens] + [N]
    td = [0] + [r[2] for r in tokens] + [0]
    end_node = len(ts) - 1
    by_start = sorted(range(1, end_node), key=lambda i: ts[i])
    starts = [ts[i] for i in by_start]
    diag_runs: dict[int, list[int]] = defaultdict(list)
    for i in by_start:
        diag_runs[td[i]].append(i)
    next_same: list[list[int]] = [[] for _ in ts]
    for lst in diag_runs.values():
        for idx, i in enumerate(lst):
            next_same[i] = lst[idx + 1 : idx + 4]
    next_same[0] = diag_runs[0][:3]

    add_cache: dict[tuple[int, int, int], float] = {}

    predicted_size = predictor.size

    def additions_size(start: int, end: int, diag: int) -> float:
        """Size of the additions covering new[start:end], possibly extending one byte past end"""
        key = (start, end, diag)
        size = add_cache.get(key)
        if size is not None:
            return size
        size = 0
        for pos in range(start, end, 2):
            o = pos + diag
            if o < 0 or o + 2 > len(bin_old) or pos + 2 > N:
                size = math.inf
                break
            delta = ((bin_new[pos] | bin_new[pos + 1] << 8) - (bin_old[o] | bin_old[o + 1] << 8)) & 0xFFFF
            size += predicted_size(pos, delta)
        add_cache[key] = size
        return size

    cost = [[math.inf, math.inf, math.inf] for _ in ts]
    back: list[list[tuple]] = [[(), (), ()] for _ in ts]
    cost[0][OUT] = 0
    relay_offset: list[int] = []
    relay_node: list[int] = []
    relay_val = math.inf
    covering: list[tuple[int, int]] = []
    next_start = 0
    # exit_best results for the node currently being expanded
    exit_node = -1
    exit_cache: dict[int, tuple[float, int, tuple]] = {}

    def exit_best(j: int, G: int) -> tuple[float, int, tuple]:
        """Cheapest way to write G bytes after node j, ending outside of any PATCH"""
        nonlocal exit_node, exit_cache
        if j == exit_node:
            cached = exit_cache.get(G)
            if cached is not None:
                return cached
        else:
            exit_node = j
            exit_cache = {}
        c_out, c_in, c_dl = cost[j]
        write = _len_hdr_size(G) + G if G else 0
        best: tuple[float, int, tuple[int, ...]] = (c_out + write, OUT, (WRITE,))
        if c_in + 1 + write < best[0]:
            best = (c_in + 1 + write, IN_PATCH, (END_PATCH, WRITE))
        if 0 < G <= 255 and c_in + G + (G > 1) + 1 < best[0]:
            best = (c_in + G + (G > 1) + 1, IN_PATCH, (WRITE, END_PATCH))
        if c_dl + 2 + write < best[0]:
            best = (c_dl + 2 + write, IN_DELTA, (END_DELTA, WRITE))
        # Each addition is at least 1 byte, skip when that can't be cheaper
        if 0 < G <= MAX_DELTA_GAP and c_dl + 1 + (G + 1) // 2 < best[0]:
            c = c_dl + additions_size(te[j], te[j] + G, td[j]) + 1
            if c < best[0]:
                best = (c, IN_DELTA, (ADD, END_DELTA))
        exit_cache[G] = best
        return best

    for j in range(end_node):
        if j > 0:
            # Enter from the best prior node, writing everything in between
            x = ts[j]
            i = relay_node[bisect.bisect_right(relay_offset, x) - 1]
            G = x - te[i]
            c, si, actions = exit_best(i, G)
            c += _addr_size(td[j] - td[i])
            L = te[j] - x
            for state, size, copy_actions in (
                (OUT, _len_hdr_size(L), ()),
                (IN_PATCH, 1 + _patch_copy_size(L), (START_PATCH,)),
                (IN_DELTA, 1 + _delta_copy_size(L), (START_DELTA,)),
            ):
                if c + size < cost[j][state]:
                    cost[j][state] = c + size
                    back[j][state] = (i, si, actions, copy_actions)

        c_out, c_in, c_dl = cost[j]
        p = te[j]
        dj = td[j]
        v = min(c_out, c_in + 1, c_dl + 2) - p
        if v < relay_val:
            relay_val = v
            relay_offset.append(p)
            relay_node.append(j)

        while next_start < len(by_start) and starts[next_start] <= p:
            i = by_start[next_start]
            heapq.heappush(covering, (te[i], i))
            next_start += 1
        while covering and covering[0][0] <= p:
            heapq.heappop(covering)
        candidates = [i for _, i in covering]
        candidates.extend(next_same[j])
        first = bisect.bisect_right(starts, p)
        for idx in range(first, min(first + 8, len(starts))):
            if starts[idx] > p + 256 and idx > first:
                break
            candidates.append(by_start[idx])

        for k in candidates:
            s = max(ts[k], p)
            G = s - p
            L = te[k] - s
            if L <= 0:
                continue
            shift = td[k] - dj

            # Ready for the COPY outside of any PATCH
            pre_out, out_state, out_actions = exit_best(j, G)
            # Ready for the COPY inside a PATCH, after a WRITE
            pre_patch = c_in + G + (G > 1) if 0 < G <= 255 else math.inf
            # Ready for the COPY inside a PATCH_DELTA, nothing pending
            delta_actions: tuple[int, ...] = ()
            pre_delta, delta_state = math.inf, OUT
            # Odd gaps are covered by additions extending into this run
            L_delta = L - (G & 1)
            if shift:
                # PATCH_DELTA can't change the offset
                pass
            elif G == 0:
                pre_delta, delta_state, delta_actions = c_dl + 1, IN_DELTA, (FLUSH,)
            elif G <= MAX_DELTA_GAP and (
                # Each addition is at least 1 byte, skip when that can't improve either state
                min(c_dl, c_out + 1, c_in + 2) + (G + 1) // 2
                < max(cost[k][IN_DELTA] - _delta_copy_size(L_delta), cost[k][OUT] - 1 - _len_hdr_size(L_delta))
            ):
                size = additions_size(p, s, dj)
                pre_delta, delta_state, delta_actions = min(
                    (c_dl + size, IN_DELTA, (ADD,)),
                    (c_out + 1 + size, OUT, (START_DELTA, ADD)),
                    (c_in + 2 + size, IN_PATCH, (END_PATCH, START_DELTA, ADD)),
                )
            if shift:
                if pre_patch + 1 < pre_out:
                    pre_out, out_state, out_actions = pre_patch + 1, IN_PATCH, (WRITE, END_PATCH)
                pre_out += _addr_size(shift)
                pre_patch = math.inf

            # Same order as the tie-breaking of the original tuple iteration
            ck = cost[k]
            bk = back[k]
            hdr_L = _len_hdr_size(L)
            patch_L = _patch_copy_size(L)
            c = pre_patch + patch_L
            if c < ck[IN_PATCH]:
                ck[IN_PATCH] = c
                bk[IN_PATCH] = (j, IN_PATCH, (WRITE,), ())
            c = pre_patch + 1 + hdr_L
            if c < ck[OUT]:
                ck[OUT] = c
                bk[OUT] = (j, IN_PATCH, (WRITE,), (END_PATCH,))
            c = pre_out + hdr_L
            if c < ck[OUT]:
                ck[OUT] = c
                bk[OUT] = (j, out_state, out_actions, ())
            c = pre_out + 1 + patch_L
            if c < ck[IN_PATCH]:
                ck[IN_PATCH] = c
                bk[IN_PATCH] = (j, out_state, out_actions, (START_PATCH,))
            c = pre_out + 1 + _delta_copy_size(L)
            if c < ck[IN_DELTA]:
                ck[IN_DELTA] = c
                bk[IN_DELTA] = (j, out_state, out_actions, (START_DELTA,))
            if pre_delta != math.inf:
                c = pre_delta + _delta_copy_size(L_delta)
                if c < ck[IN_DELTA]:
                    ck[IN_DELTA] = c
                    bk[IN_DELTA] = (j, delta_state, delta_actions, ())
                c = pre_delta + 1 + _len_hdr_size(L_delta)
                if c < ck[OUT]:
                    ck[OUT] = c
                    bk[OUT] = (j, delta_state, delta_actions, (END_DELTA,))

        G = N - p
        c, sj, actions = exit_best(j, G)
        if c < cost[end_node][OUT]:
            cost[end_node][OUT] = c
            back[end_node][OUT] = (j, sj, actions, None)

    # Recover the path
    path = []
    node, state = end_node, OUT
    while node != 0:
        j, sj, gap_actions, copy_actions = back[node][state]
        path.append((j, node, gap_actions, copy_actions))
        node, state = j, sj

    builder = _DeltaInstrBuilder(bin_old, bin_new)
    for j, k, gap_actions, copy_actions in reversed(path):
        s = max(ts[k], te[j])
        for action in gap_actions:
            if action == END_PATCH:
                builder.patch_end()
            elif action == END_DELTA:
                builder.delta_end()
            elif action == START_DELTA:
                builder.delta_start()
            elif action == FLUSH:
                builder.delta_flush()
            elif action == WRITE:
                if s > builder.new_offset:
                    builder.write(s - builder.new_offset)
            elif action == ADD:
                while builder.new_offset < s:
                    builder.add()
        if k == end_node:
            break
        target = builder.new_offset + td[k]
        if builder.old_offset != target:
            builder.set_addr(target)
        for action in copy_actions:
            if action == END_PATCH:
                builder.patch_end()
            elif action == END_DELTA:
                builder.delta_end()
            elif action == START_PATCH:
                builder.patch_start()
            elif action == START_DELTA:
                builder.delta_start()
        builder.copy(te[k] - builder.new_offset)
    assert builder.patch is None and builder.delta is None
    assert builder.new_offset == N
    return builder.instructions, builder.additions


def encode(bin_orig: bytes, bin_new: bytes) -> list[Instr]:
    """Encode the new file as instructions applied to the original file"""
    old = np.frombuffer(bin_orig, dtype=np.uint8)
    new = np.frombuffer(bin_new, dtype=np.uint8)

    runs = _candidate_runs(old, new)
    _, gaps = _shortest_path_encode(bin_new, runs)
    runs |= _gap_runs(old, new, gaps)
    best, gaps = _shortest_path_encode(bin_new, runs)
    best_size = sum(len(i) for i in best)

    # Initial prediction from the gaps of the encoding without additions
    additions = []
    for start, end, diag_before, diag_after in gaps:
        if diag_before == diag_after and end - start <= MAX_DELTA_GAP:
            for pos in range(start, end, 2):
                o = pos + diag_before
                if o >= 0 and o + 2 <= len(bin_orig) and pos + 2 <= len(bin_new):
                    delta = (bin_new[pos] | bin_new[pos + 1] << 8) - (bin_orig[o] | bin_orig[o + 1] << 8)
                    additions.append((pos, delta & 0xFFFF))

    # Refine the prediction with the additions actually used
    for _ in range(2):
        instructions, additions = _delta_encode(bin_orig, bin_new, runs, _DeltaPredictor(additions))
        size = sum(len(i) for i in instructions)
        if size < best_size:
            best, best_size = instructions, size
    return best
