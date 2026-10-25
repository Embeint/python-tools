#!/usr/bin/env python3

"""Shortest path encoder for the element stream format (version 3), for Cortex-M Thumb-2 images

Uses the candidate COPY runs of `encoder_shortest_path`, with the cost model of an element
stream: each operation costs its header byte and payload, while the copy before it only costs
its length extension. Gaps between runs are filled with any mix of additions and literals.

Every copy relocates the sites it contains, so runs are recomputed against the relocated view
of the original. The relocation map and pointer base are fitted to where a previous encoding
copied code from.
"""

import bisect
import heapq
import math
from collections import defaultdict

import numpy as np

from infuse_iot.cpatch.encoder_shortest_path import _candidate_runs, _gap_runs, _shortest_path_encode, _true_runs
from infuse_iot.cpatch.encoder_shortest_path_delta import _initial_additions
from infuse_iot.cpatch.stream import (
    FLAG_BRANCH,
    FLAG_POINTER,
    MAP_ENTRY_LEN,
    Add,
    AddExplicit,
    Element,
    History,
    Literal,
    LiteralShift,
    NoOp,
    Op,
    Preamble,
    Region,
    Relocator,
    Shift,
    svarint_len,
    thumb_branch_offset,
    uvarint_len,
)

# Largest gap between runs that is considered for filling with additions
MAX_FILL_GAP = 24
# Minimum length of a run
MIN_RUN = 2
# Runs on the same diagonal closer than this are recomputed together
WINDOW_MERGE = 512
# Distance before and after the runs on a diagonal that is searched for relocated runs
WINDOW_MARGIN = 64
# Approximate bytes saved by each site that the relocation map relocates correctly
SITE_VALUE = 2
# Minimum number of pointers explained by a base address or region before relocating them
MIN_POINTERS = 16
# Pointer regions outside of the original image
MAX_REGIONS = 4
# Largest gap between changed pointers in the same region
REGION_GAP = 1 << 16
# Largest change of a pointer into a region
MAX_REGION_SHIFT = 1 << 16

# Gap filling DP states: no literal open, literal of 1 byte open, literal of 2+ bytes open
CLOSED = 0
LIT_1 = 1
LIT_N = 2
# Back pointer of a state reached by an addition (otherwise reached by a literal byte)
BY_ADD = 3

# How the gap before a run is filled
FILL_LITERAL = 0
# Additions on the diagonal of the previous run, then any shift
FILL_BEFORE = 1
# Shift, then additions on the diagonal of the next run
FILL_AFTER = 2
# The final addition extends one byte into the next run
FILL_OVER = 4

# Fill steps: an addition, or a literal of the given length
ADD = -1

Run = tuple[int, int, int]


def _val16(data: bytes, offset: int) -> int:
    return data[offset] | data[offset + 1] << 8


def _val32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "little")


def _ext_cost(length: int) -> int:
    """Encoded size of the length extension of a copy"""
    return 0 if length < 15 else uvarint_len(length - 15)


def _literal_cost(length: int) -> int:
    if length == 0:
        return 0
    if length == 1:
        return 2
    return 1 + uvarint_len(length - 2) + length


def _merged_shift(literal: bool, shift: int) -> int:
    """Saving when a shift directly follows a literal, as LITERAL_SHIFT"""
    return 1 if literal and shift != 0 else 0


def _shift_cost(shift: int) -> int:
    return 0 if shift == 0 else 1 + svarint_len(shift)


class _Predictor:
    """Predicted encoded size of an addition, from the delta history of a previous encoding"""

    def __init__(self, additions: list[tuple[int, int]]):
        history = History()
        self.offsets: list[int] = []
        self.snapshots = [frozenset(history.deltas)]
        for offset, delta in additions:
            history.use(history.find(delta), delta)
            self.offsets.append(offset)
            self.snapshots.append(frozenset(history.deltas))

    def size(self, offset: int, delta: int) -> int:
        snapshot = self.snapshots[bisect.bisect_left(self.offsets, offset)]
        return 1 if delta in snapshot else 3


class _Builder:
    """Construct an element list from the new file, tracking file offsets"""

    def __init__(self, old: bytes, new: bytes):
        self.old = old
        self.new = new
        self.elements: list[Element] = []
        self.history = History()
        # Copy length to include in the next element
        self.pending = 0
        self.new_offset = 0
        self.old_offset = 0
        # (new offset, delta) of each addition
        self.additions: list[tuple[int, int]] = []
        # (new start, new end, diagonal) of the regions produced from the original
        self.coverage: list[Run] = []

    @property
    def diag(self) -> int:
        return self.old_offset - self.new_offset

    def cover(self, start: int, end: int, d: int):
        """Record that `new[start:end]` was produced from the original on diagonal `d`"""
        start = max(start, -d)
        end = min(end, len(self.old) - d)
        if start >= end:
            return
        # Merge contiguous regions, so that sites split between operations are still found
        if self.coverage and self.coverage[-1][2] == d and self.coverage[-1][1] == start:
            self.coverage[-1] = (self.coverage[-1][0], end, d)
        else:
            self.coverage.append((start, end, d))

    def op(self, op: Op):
        self.elements.append(Element(self.pending, op))
        self.pending = 0

    def copy(self, length: int):
        assert length > 0
        self.cover(self.new_offset, self.new_offset + length, self.diag)
        self.pending += length
        self.new_offset += length
        self.old_offset += length

    def shift(self, shift: int):
        self.old_offset += shift
        last = self.elements[-1] if self.elements else None
        if self.pending == 0 and last is not None and isinstance(last.op, Literal):
            self.elements[-1] = Element(last.copy, LiteralShift(last.op.data, shift))
            return
        self.op(Shift(shift))

    def literal(self, length: int):
        n = self.new_offset
        self.op(Literal(self.new[n : n + length]))
        self.new_offset += length
        self.old_offset += length

    def fill(self, steps: list[int], d: int):
        assert self.diag == d
        start = self.new_offset
        for step in steps:
            if step == ADD:
                n, o = self.new_offset, self.old_offset
                delta = (_val16(self.new, n) - _val16(self.old, o)) & 0xFFFF
                index = self.history.find(delta)
                self.op(AddExplicit(delta) if index is None else Add(index))
                self.history.use(index, delta)
                self.additions.append((n, delta))
                self.new_offset += 2
                self.old_offset += 2
            else:
                self.literal(step)
        self.cover(start, self.new_offset, d)


class _Search:
    def __init__(self, old: bytes, new: bytes, predictor: _Predictor):
        self.old = old
        self.new = new
        self.predictor = predictor
        self.fill_cache: dict[tuple[int, int, int], tuple[float, float, float]] = {}

    def add_cost(self, x: int, d: int) -> float:
        o = x + d
        if o < 0 or o + 2 > len(self.old) or x + 2 > len(self.new):
            return math.inf
        delta = (_val16(self.new, x) - _val16(self.old, o)) & 0xFFFF
        return self.predictor.size(x, delta)

    def fill_table(self, p: int, s: int, d: int) -> list[list[list]]:
        """Minimum costs of producing `new[p:s]` with additions on diagonal `d` and literals.
        Index `s - p + 1` is reached by an addition that extends one byte past `s`."""
        g = s - p
        t = [[[math.inf, 0] for _ in range(3)] for _ in range(g + 2)]
        t[0][CLOSED][0] = 0
        for x in range(g):
            add = self.add_cost(p + x, d)
            for state in (CLOSED, LIT_1, LIT_N):
                c = t[x][state][0]
                if c == math.inf:
                    continue
                if state == CLOSED:
                    nxt, inc = LIT_1, 2
                elif state == LIT_1:
                    nxt, inc = LIT_N, 2
                else:
                    nxt, inc = LIT_N, 1
                if c + inc < t[x + 1][nxt][0]:
                    t[x + 1][nxt] = [c + inc, state]
                if c + add < t[x + 2][CLOSED][0]:
                    t[x + 2][CLOSED] = [c + add, BY_ADD + state]
        return t

    def fill_cost(self, p: int, s: int, d: int) -> tuple[float, float, float]:
        """Costs of filling `new[p:s]` on diagonal `d`: ending with an addition, ending with a
        literal, and ending with an addition one byte past `s`"""
        key = (p, s, d)
        cached = self.fill_cache.get(key)
        if cached is not None:
            return cached
        t = self.fill_table(p, s, d)
        g = s - p
        c = (t[g][CLOSED][0], min(t[g][LIT_1][0], t[g][LIT_N][0]), t[g + 1][CLOSED][0])
        self.fill_cache[key] = c
        return c

    def fill_plan(self, p: int, s: int, d: int, over: bool, literal_saving: int) -> list[int]:
        """Steps of the cheapest fill, where ending with a literal saves `literal_saving`"""
        t = self.fill_table(p, s, d)
        g = s - p
        if over:
            x, state = g + 1, CLOSED
        else:
            x = g
            state = min(range(3), key=lambda st: t[g][st][0] - (0 if st == CLOSED else literal_saving))
        steps: list[int] = []
        while x > 0:
            prev = t[x][state][1]
            if prev >= BY_ADD:
                steps.append(ADD)
                x -= 2
                state = prev - BY_ADD
            else:
                if steps and steps[-1] != ADD and state != CLOSED:
                    steps[-1] += 1
                else:
                    steps.append(1)
                x -= 1
                state = prev
        steps.reverse()
        return steps

    def search(self, runs: set[Run], atomic: set[tuple[int, int]]) -> tuple[list[Element], list, list[Run]]:
        """Minimum size encoding over the candidate runs: (elements, additions, coverage)"""
        big_n = len(self.new)
        # Total order, so that the encoding does not depend on set iteration order
        tokens = sorted(runs, key=lambda r: (r[1], r[0], r[2]))
        # Node 0 is the start of the file, the final node is the end of the file
        ts = [0] + [r[0] for r in tokens] + [big_n]
        te = [0] + [r[1] for r in tokens] + [big_n]
        td = [0] + [r[2] for r in tokens] + [0]
        end_node = len(ts) - 1
        by_start = sorted(range(1, end_node), key=lambda i: ts[i])
        starts = [ts[i] for i in by_start]
        # Next few runs on the same diagonal
        diag_runs: dict[int, list[int]] = defaultdict(list)
        for i in by_start:
            diag_runs[td[i]].append(i)
        next_same: list[list[int]] = [[] for _ in ts]
        for lst in diag_runs.values():
            for idx, i in enumerate(lst):
                next_same[i] = lst[idx + 1 : idx + 4]
        next_same[0] = diag_runs[0][:3]

        def cuts(d: int, x: int) -> bool:
            # A copy may not start inside a site that only matches when relocated in full
            return (d, x - 1) in atomic or (d, x - 2) in atomic or (d, x - 3) in atomic

        def op_cost(i: int, g: int, shift: int) -> int:
            # Operation required between two runs: a shift, or splitting consecutive copies
            if shift:
                return _shift_cost(shift)
            return 1 if g == 0 and i != 0 else 0

        cost = [math.inf] * len(ts)
        back = [(0, FILL_LITERAL)] * len(ts)
        cost[0] = 0
        # Running minimum of (cost - new offset), for long range literal transitions
        relay_offset: list[int] = []
        relay_node: list[int] = []
        relay_val = math.inf
        # Runs that contain the current offset
        covering: list[tuple[int, int]] = []
        next_start = 0

        for j in range(end_node):
            if j > 0:
                # Enter from the best prior node, writing everything in between
                x = ts[j]
                i = relay_node[bisect.bisect_right(relay_offset, x) - 1]
                g = x - te[i]
                shift = td[j] - td[i]
                c = cost[i] + _literal_cost(g) + op_cost(i, g, shift) - _merged_shift(g > 0, shift)
                c += _ext_cost(te[j] - x)
                if c < cost[j]:
                    cost[j] = c
                    back[j] = (i, FILL_LITERAL)
            c_j = cost[j]
            p = te[j]
            dj = td[j]
            if c_j - p < relay_val:
                relay_val = c_j - p
                relay_offset.append(p)
                relay_node.append(j)

            # Candidate next runs: covering this offset, on the same diagonal, and starting soon after
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
                g = s - p
                L = te[k] - s
                if L <= 0:
                    continue
                dk = td[k]
                shift = dk - dj
                best = (math.inf, FILL_LITERAL)
                if g == 0:
                    if s == ts[k] or not cuts(dk, s):
                        best = (op_cost(j, g, shift) + _ext_cost(L), FILL_LITERAL)
                else:
                    sc = _shift_cost(shift)
                    best = (_literal_cost(g) + sc - _merged_shift(True, shift) + _ext_cost(L), FILL_LITERAL)
                    if g <= MAX_FILL_GAP:
                        for kind, d in ((FILL_BEFORE, dj), (FILL_AFTER, dk)):
                            if kind == FILL_AFTER and shift == 0:
                                continue
                            closed, literal, over = self.fill_cost(p, s, d)
                            if kind == FILL_BEFORE:
                                exact = min(closed, literal - _merged_shift(True, shift))
                            else:
                                exact = min(closed, literal)
                            if exact + sc + _ext_cost(L) < best[0]:
                                best = (exact + sc + _ext_cost(L), kind)
                            if L >= 2 and not cuts(dk, s + 1) and over + sc + _ext_cost(L - 1) < best[0]:
                                best = (over + sc + _ext_cost(L - 1), kind | FILL_OVER)
                if c_j + best[0] < cost[k]:
                    cost[k] = c_j + best[0]
                    back[k] = (j, best[1])

            # Write the remainder of the file
            g = big_n - p
            if g == 0:
                best = (0 if j == 0 else 1, FILL_LITERAL)
            else:
                best = (_literal_cost(g), FILL_LITERAL)
            if 0 < g <= MAX_FILL_GAP:
                closed, literal, _ = self.fill_cost(p, big_n, dj)
                exact = min(closed, literal)
                if exact < best[0]:
                    best = (exact, FILL_BEFORE)
            if c_j + best[0] < cost[end_node]:
                cost[end_node] = c_j + best[0]
                back[end_node] = (j, best[1])

        # Recover the path
        path = []
        node = end_node
        while node != 0:
            j, kind = back[node]
            path.append((j, node, kind))
            node = j
        path.reverse()

        builder = _Builder(self.old, self.new)
        for j, k, kind in path:
            p = te[j]
            s = big_n if k == end_node else max(ts[k], p)
            dk = td[j] if k == end_node else td[k]
            shift = dk - td[j]
            over = bool(kind & FILL_OVER)
            fill = kind & ~FILL_OVER
            if fill == FILL_BEFORE:
                builder.fill(self.fill_plan(p, s, td[j], over, _merged_shift(True, shift)), td[j])
            elif fill == FILL_AFTER:
                builder.shift(shift)
                builder.fill(self.fill_plan(p, s, dk, over, 0), dk)
            elif s > p:
                builder.literal(s - p)
                if td[j] == dk:
                    # Replaces bytes of the original on the diagonal
                    builder.cover(p, s, dk)
            if k == end_node:
                break
            if fill != FILL_AFTER and shift:
                builder.shift(shift)
            elif s == p and shift == 0 and builder.pending > 0:
                builder.op(NoOp())
            builder.copy(te[k] - builder.new_offset)
        if builder.pending > 0:
            builder.op(NoOp())
        assert builder.new_offset == big_n
        return builder.elements, builder.additions, builder.coverage


def _branch_patterns(old: np.ndarray) -> np.ndarray:
    """Whether a Thumb-2 BL / B.W pattern starts at each halfword"""
    n = (len(old) // 2) * 2
    half = old[:n].view("<u2").astype(np.int64)
    pattern = np.zeros(len(half), dtype=bool)
    if len(half) >= 2:
        h1, h2 = half[:-1], half[1:]
        pattern[:-1] = ((h1 & 0xF800) == 0xF000) & (((h2 & 0xD000) == 0xD000) | ((h2 & 0xD000) == 0x9000))
    return pattern


def _site_offsets(old: np.ndarray, preamble: Preamble) -> list[int]:
    """Sorted original offsets of the relocation sites, as found by `Relocator`"""
    pattern = _branch_patterns(old)
    branch = np.zeros(len(pattern), dtype=bool)
    if preamble.flags & FLAG_BRANCH:
        branch = pattern.copy()
        branch[1:] &= ~pattern[:-1]
    sites = branch.copy()
    if preamble.flags & FLAG_POINTER and len(pattern) >= 2:
        half = old[: len(pattern) * 2].view("<u2").astype(np.int64)
        value = np.zeros(len(pattern), dtype=np.int64)
        value[:-1] = half[:-1] | half[1:] << 16
        in_range = ((value - preamble.base) & 0xFFFFFFFF) < len(old)
        for region in preamble.regions:
            in_range |= ((value - region.base) & 0xFFFFFFFF) < region.length
        overlap = branch.copy()
        overlap[1:] |= branch[:-1]
        overlap[:-1] |= branch[1:]
        pointer = in_range & ~overlap
        pointer[1::2] = False
        pointer[-1] = False
        sites |= pointer
    addresses = np.flatnonzero(sites) * 2
    return addresses[addresses + 4 <= len(old)].tolist()


def _relocated_runs(
    bin_old: bytes, bin_new: bytes, runs: set[Run], reloc: Relocator
) -> tuple[set[Run], set[tuple[int, int]]]:
    """Runs that match the new file when copied with relocation, and the sites inside them that
    only match when copied in full, as (diagonal, new offset)"""
    old = np.frombuffer(bin_old, dtype=np.uint8)
    new = np.frombuffer(bin_new, dtype=np.uint8)
    sites = _site_offsets(old, reloc.preamble)
    found: set[Run] = set()
    atomic: set[tuple[int, int]] = set()

    def window(d: int, start: int, end: int):
        start = max(start, 0, -d)
        end = min(end, len(new), len(old) - d)
        if end - start < MIN_RUN:
            return
        mask = new[start:end] == old[start + d : end + d]
        splits = []
        for a in sites[bisect.bisect_left(sites, start + d) :]:
            if a + 4 > end + d:
                break
            rel = a - d - start
            relocated = reloc.relocate(a, a - d)
            if relocated == bin_old[a : a + 4]:
                continue
            if relocated == bin_new[a - d : a - d + 4]:
                mask[rel : rel + 4] = True
                atomic.add((d, a - d))
            elif mask[rel : rel + 4].all():
                # Copying the site in full would relocate it, the original matches when split
                splits.append(rel + 2)
        run_start, run_end = _true_runs(mask)
        for s, e in zip(run_start.tolist(), run_end.tolist(), strict=True):
            lo = bisect.bisect_right(splits, s)
            hi = bisect.bisect_left(splits, e)
            for x in [*splits[lo:hi], e]:
                if x - s >= MIN_RUN:
                    found.add((start + s, start + x, d))
                s = x

    # Windows around the runs on each diagonal, as copied with relocation. Relocation can join
    # and extend the runs.
    by_diag: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for start, end, diag in runs:
        by_diag[diag].append((start, end))
    for d, spans in sorted(by_diag.items()):
        spans.sort()
        w_start, w_end = spans[0]
        for s, e in spans[1:]:
            if s - w_end > WINDOW_MERGE:
                window(d, w_start - WINDOW_MARGIN, w_end + WINDOW_MARGIN)
                w_start = s
            w_end = max(w_end, e)
        window(d, w_start - WINDOW_MARGIN, w_end + WINDOW_MARGIN)
    return found, atomic


def _words(data: np.ndarray, offsets: np.ndarray) -> np.ndarray:
    """Little endian 32 bit words at arbitrary offsets"""
    out = np.zeros(len(offsets), dtype=np.int64)
    for i in range(4):
        out |= data[offsets + i].astype(np.int64) << (8 * i)
    return out


def _coverage_words(old: np.ndarray, new: np.ndarray, coverage: list[Run]):
    """(original offsets, original values, new values) of the aligned words in each region"""
    for s, e, d in coverage:
        a0 = (s + d + 3) & ~3
        if a0 + 4 > e + d:
            continue
        offsets = np.arange(a0, e + d - 3, 4, dtype=np.int64)
        yield d, offsets, _words(old, offsets), _words(new, offsets - d)


def _pointer_base(old: np.ndarray, new: np.ndarray, coverage: list[Run]) -> int | None:
    """Base address that explains the most changed words of the original as relocated pointers"""
    # Original image regions by the shift they moved with
    by_shift: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for s, e, d in coverage:
        by_shift[-d].append((s + d, e + d))
    for shift, segments in by_shift.items():
        segments.sort()
        merged: list[tuple[int, int]] = []
        for s, e in segments:
            if merged and s <= merged[-1][1] + 64:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))
            else:
                merged.append((s, e))
        by_shift[shift] = merged

    # Each changed word votes for the base addresses under which it points to a region
    # that moved by the same amount
    events: list[tuple[int, int]] = []
    for _, _, v_old, v_new in _coverage_words(old, new, coverage):
        delta = v_new - v_old
        keep = (delta != 0) & (np.abs(delta) < len(old))
        for value, dv in zip(v_old[keep].tolist(), delta[keep].tolist(), strict=True):
            moved = by_shift.get(dv)
            if moved is None or len(moved) > 16:
                continue
            for lo, hi in moved:
                events.append((value - hi + 1, 1))
                events.append((value - lo + 1, -1))
    events.sort()
    # Ranges of base addresses with their vote counts
    ranges = []
    count = 0
    for i, (x, inc) in enumerate(events):
        count += inc
        if i + 1 < len(events) and events[i + 1][0] > x:
            ranges.append((x, events[i + 1][0], count))
    best = max((r[2] for r in ranges), default=0)
    if best < MIN_POINTERS:
        return None

    # Images start on flash page boundaries, prefer the most aligned address that explains
    # close to the most words
    def aligned(lo: int, hi: int) -> tuple[int, int]:
        for k in range(31, -1, -1):
            b = (hi - 1) & ~((1 << k) - 1)
            if b >= lo:
                return b, k
        raise AssertionError

    choice = None
    for lo, hi, c in ranges:
        if c * 50 >= best * 49:
            b, k = aligned(lo, hi)
            if choice is None or (k, c) >= (choice[1], choice[2]):
                choice = (b, k, c)
    assert choice is not None
    base = choice[0]
    return base if 0 <= base <= 0xFFFFFFFF - len(old) else None


def _fit_map(samples: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Piecewise constant fit of (offset, shift) samples, dropping entries that save less than
    they cost"""
    samples = sorted(samples)
    entries: list[tuple[int, int]] = []
    for t, shift in samples:
        if (entries[-1][1] if entries else 0) != shift and (not entries or entries[-1][0] != t):
            entries.append((t, shift))
    while True:
        # Samples matching each entry, beyond those that would match without it
        benefit = [0] * len(entries)
        idx = 0
        for t, shift in samples:
            while idx < len(entries) and entries[idx][0] <= t:
                idx += 1
            if idx > 0:
                e = idx - 1
                prev = entries[e - 1][1] if e > 0 else 0
                benefit[e] += (shift == entries[e][1]) - (shift == prev)
        # Never drop neighbours in the same round, their benefits depend on each other
        keep = [True] * len(entries)
        dropped = False
        for i in range(len(entries)):
            if (i == 0 or keep[i - 1]) and benefit[i] * SITE_VALUE < MAP_ENTRY_LEN:
                keep[i] = False
                dropped = True
        if not dropped:
            break
        merged: list[tuple[int, int]] = []
        for entry, k in zip(entries, keep, strict=True):
            if k and (merged[-1][1] if merged else 0) != entry[1]:
                merged.append(entry)
        entries = merged
    return [(t, shift) for t, shift in entries if t < 1 << 24 and -(1 << 23) <= shift < 1 << 23]


def _pointer_regions(old: np.ndarray, new: np.ndarray, coverage: list[Run], base: int) -> list[Region]:
    """Address ranges outside of the original image where many words changed by small amounts,
    such as pointers into RAM"""
    pattern = _branch_patterns(old)
    # Branch sites, padded so that the halfwords either side of every word can be indexed
    branch = np.zeros(len(pattern) + 2, dtype=bool)
    branch[1:-1] = pattern
    branch[2:-1] &= ~pattern[:-1]
    values: list[int] = []
    for _, offsets, v_old, v_new in _coverage_words(old, new, coverage):
        # Small values are more likely to be constants than pointers, and words that
        # overlap branches are instructions
        k = offsets // 2 + 1
        overlap = branch[k - 1] | branch[k] | branch[k + 1]
        keep = (
            (v_old != v_new)
            & ~overlap
            & (v_old >= 1 << 16)
            & (((v_old - base) & 0xFFFFFFFF) >= len(old))
            & (np.abs(v_new - v_old) < MAX_REGION_SHIFT)
        )
        values.extend(v_old[keep].tolist())
    values.sort()
    clusters = []
    i = 0
    while i < len(values):
        j = i + 1
        while j < len(values) and values[j] - values[j - 1] < REGION_GAP:
            j += 1
        if j - i >= MIN_POINTERS:
            clusters.append((j - i, values[i], values[j - 1] - values[i] + 1))
        i = j
    # Regions with the most changed pointers
    clusters.sort(reverse=True)
    clusters = sorted(clusters[:MAX_REGIONS], key=lambda c: c[1])
    return [Region(base, length) for _, base, length in clusters]


def _build_preamble(bin_old: bytes, bin_new: bytes, coverage: list[Run]) -> Preamble:
    """Relocation preamble fitted to the regions of an existing encoding"""
    old = np.frombuffer(bin_old, dtype=np.uint8)
    new = np.frombuffer(bin_new, dtype=np.uint8)
    preamble = Preamble(FLAG_BRANCH)
    base = _pointer_base(old, new, coverage)
    if base is not None:
        preamble.flags |= FLAG_POINTER
        preamble.base = base
        preamble.regions = _pointer_regions(old, new, coverage, base)
    reloc = Relocator(bin_old, preamble)
    sites = _site_offsets(old, preamble)

    # The shift each site requires to match the new file
    samples: list[tuple[int, int]] = []
    region_samples: list[list[tuple[int, int]]] = [[] for _ in preamble.regions]
    for s, e, d in coverage:
        for a in sites[bisect.bisect_left(sites, s + d) :]:
            if a + 4 > e + d:
                break
            n = a - d
            offset = reloc.branch_site(a)
            if offset is not None:
                target = a + 4 + offset
                h1, h2 = _val16(bin_new, n), _val16(bin_new, n + 2)
                new_offset = thumb_branch_offset(h1, h2)
                if (
                    0 <= target < len(bin_old)
                    and (h2 & 0xD000) == (_val16(bin_old, a + 2) & 0xD000)
                    and new_offset is not None
                ):
                    samples.append((target, n + 4 + new_offset - target))
                continue
            pointer = reloc.pointer_target(a)
            if pointer is not None:
                index, target = pointer
                sample = (target, _val32(bin_new, n) - _val32(bin_old, a))
                (samples if index is None else region_samples[index]).append(sample)
    preamble.map = _fit_map(samples)
    regions = []
    for region, region_sample in zip(preamble.regions, region_samples, strict=True):
        region.map = _fit_map(region_sample)
        # Pointers the region relocates, less the unchanged words it breaks
        starts = [e[0] for e in region.map]
        gain = 0
        for t, needed in region_sample:
            i = bisect.bisect_right(starts, t)
            shift = region.map[i - 1][1] if i else 0
            gain += (needed != 0 and shift == needed) - (needed == 0 and shift != 0)
        if gain * SITE_VALUE > 10 + MAP_ENTRY_LEN * len(region.map):
            regions.append(region)
    preamble.regions = regions
    return preamble


def encode(bin_orig: bytes, bin_new: bytes) -> tuple[Preamble, list[Element]]:
    """Encode the new file as elements applied to the original file"""
    old = np.frombuffer(bin_orig, dtype=np.uint8)
    new = np.frombuffer(bin_new, dtype=np.uint8)

    runs = _candidate_runs(old, new)
    _, gaps = _shortest_path_encode(bin_new, runs)
    runs |= _gap_runs(old, new, gaps)
    _, gaps = _shortest_path_encode(bin_new, runs)
    # Initial prediction from the gaps of the encoding without additions
    additions = _initial_additions(bin_orig, bin_new, gaps)
    best: tuple[int, Preamble, list[Element]] | None = None

    def consider(preamble: Preamble, elements: list[Element]):
        nonlocal best
        size = len(preamble) + sum(len(e) for e in elements)
        if best is None or size < best[0]:
            best = (size, preamble, elements)

    # Without relocation, refining the prediction with the additions actually used
    coverage: list[Run] = []
    for _ in range(2):
        elements, additions, coverage = _Search(bin_orig, bin_new, _Predictor(additions)).search(runs, set())
        consider(Preamble(), elements)

    # Relocation fitted to where the previous encoding copied from. The windows searched for
    # relocated runs grow with the runs already found.
    seed = set(runs)
    for _ in range(2):
        preamble = _build_preamble(bin_orig, bin_new, coverage)
        reloc_runs, atomic = _relocated_runs(bin_orig, bin_new, seed, Relocator(bin_orig, preamble))
        seed |= reloc_runs
        elements, additions, coverage = _Search(bin_orig, bin_new, _Predictor(additions)).search(reloc_runs, atomic)
        consider(preamble, elements)
    assert best is not None
    return best[1], best[2]
