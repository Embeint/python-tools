#!/usr/bin/env python3

"""Patch encoder minimising the encoded size over candidate matching runs"""

import bisect
import heapq
import math
from collections import defaultdict

import numpy as np

from infuse_iot.cpatch.instructions import CopyInstr, Instr, PatchInstr, SetAddrInstr, WriteInstr


def _len_hdr_size(length: int) -> int:
    """Encoded size of a COPY or WRITE header (mirrors `ctypes_class`)"""
    if length < 16:
        return 1
    elif length < 4096:
        return 2
    elif length < 1048576:
        return 3
    else:
        return 5


def _addr_size(shift: int) -> int:
    """Encoded size of the address instruction required for a shift (mirrors `ctypes_class`)"""
    if shift == 0:
        return 0
    elif -128 <= shift <= 127:
        return 2
    elif -32768 <= shift <= 32767:
        return 3
    else:
        return 5


def _patch_copy_size(length: int) -> float:
    """Encoded size of a COPY inside a PATCH, long copies are split by single byte WRITEs"""
    chunks = (length + 128) // 128
    return 2 * chunks - 1 if chunks <= 3 else math.inf


class _InstrBuilder:
    """Construct an instruction list from the new file, tracking file offsets"""

    def __init__(self, new: bytes):
        self.new = new
        self.instructions: list[Instr] = []
        self.patch: list[Instr] | None = None
        self.new_offset = 0
        self.old_offset = 0

    def patch_start(self):
        assert self.patch is None
        self.patch = []

    def patch_end(self):
        assert self.patch is not None
        self.instructions.append(PatchInstr(self.patch))
        self.patch = None

    def set_addr(self, addr: int):
        assert self.patch is None
        self.instructions.append(SetAddrInstr(self.old_offset, addr))
        self.old_offset = addr

    def write(self, length: int):
        instr = WriteInstr(self.new[self.new_offset : self.new_offset + length])
        if self.patch is None:
            self.instructions.append(instr)
        else:
            assert length < 256 and isinstance(self.patch[-1], CopyInstr)
            self.patch.append(instr)
        self.new_offset += length
        self.old_offset += length

    def copy(self, length: int):
        if self.patch is None:
            self.instructions.append(CopyInstr(length))
            self.new_offset += length
            self.old_offset += length
            return
        while True:
            # Final chunk must not be empty
            chunk = length if length <= 127 else (126 if length == 128 else 127)
            self.patch.append(CopyInstr(chunk))
            self.new_offset += chunk
            self.old_offset += chunk
            length -= chunk
            if length == 0:
                return
            # Separate chunks with a single byte WRITE (data matches the original file)
            self.write(1)
            length -= 1


# How the bytes between two COPY operations are handled
GAP_NONE = 0  # Nothing to write, no PATCH open
GAP_END = 1  # Nothing to write, close the PATCH
GAP_PATCH = 2  # WRITE inside the open PATCH
GAP_PATCH_END = 3  # WRITE inside the open PATCH, then close it
GAP_END_WRITE = 4  # Close the PATCH, then a standalone WRITE
GAP_WRITE = 5  # Standalone WRITE, no PATCH open
# How a COPY operation is encoded
COPY_PATCH = 0  # COPY inside the open PATCH
COPY_END = 1  # Close the PATCH, then a standalone COPY
COPY = 2  # Standalone COPY
COPY_NEW_PATCH = 3  # Start a new PATCH with the COPY


def _kgrams(a: np.ndarray, k: int) -> np.ndarray:
    """Pack every k byte substring into an integer"""
    keys = np.zeros(len(a) - k + 1, dtype=np.uint64)
    for t in range(k):
        keys |= a[t : len(a) - k + 1 + t].astype(np.uint64) << np.uint64(8 * t)
    return keys


def _true_runs(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Start and end indices of runs of True values"""
    edges = np.diff(np.concatenate(([0], mask.view(np.int8), [0])))
    return np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)


def _diagonal_runs(
    old: np.ndarray, new: np.ndarray, diag: int, start: int, end: int, min_len: int
) -> list[tuple[int, int, int]]:
    """Runs of at least `min_len` where `new[start:end]` matches the original at offset `diag`"""
    start = max(start, 0, -diag)
    end = min(end, len(new), len(old) - diag)
    if end - start < min_len:
        return []
    run_start, run_end = _true_runs(new[start:end] == old[start + diag : end + diag])
    keep = (run_end - run_start) >= min_len
    return [
        (s, e, diag) for s, e in zip((run_start[keep] + start).tolist(), (run_end[keep] + start).tolist(), strict=True)
    ]


def _seed_clusters(
    old: np.ndarray,
    new: np.ndarray,
    k: int,
    max_count: int,
    span: int,
    positions: np.ndarray | None = None,
) -> list[tuple[int, int, int]]:
    """Diagonals of k byte matches between the files, clustered along each diagonal

    The diagonal of a match is the offset in the original file minus the offset in the
    new file. Returns (diagonal, first new offset, last new offset + k) of each cluster.
    """
    if len(old) < k or len(new) < k:
        return []
    old_keys = _kgrams(old, k)
    order = np.argsort(old_keys, kind="stable")
    sorted_keys = old_keys[order]
    new_keys = _kgrams(new, k)
    if positions is None:
        positions = np.arange(len(new_keys))
    new_keys = new_keys[positions]
    first = np.searchsorted(sorted_keys, new_keys, "left")
    count = np.searchsorted(sorted_keys, new_keys, "right") - first

    # Substrings that are too common in the original carry little information
    keep = (count > 0) & (count <= max_count)
    positions, first, count = positions[keep], first[keep], count[keep]
    if len(positions) == 0:
        return []
    seed_new = np.repeat(positions, count).astype(np.int64)
    seed_idx = np.repeat(first - (np.cumsum(count) - count), count) + np.arange(len(seed_new))
    seed_diag = order[seed_idx].astype(np.int64) - seed_new

    srt = np.lexsort((seed_new, seed_diag))
    seed_diag = seed_diag[srt]
    seed_new = seed_new[srt]
    breaks = np.flatnonzero((np.diff(seed_diag) != 0) | (np.diff(seed_new) > span)) + 1
    c_first = np.concatenate(([0], breaks))
    c_last = np.concatenate((breaks, [len(seed_diag)])) - 1
    return list(
        zip(seed_diag[c_first].tolist(), seed_new[c_first].tolist(), (seed_new[c_last] + k).tolist(), strict=True)
    )


def _candidate_runs(old: np.ndarray, new: np.ndarray) -> set[tuple[int, int, int]]:
    """Exact matching runs along diagonals that relate the two files"""
    windows = []
    for diag, start, end in _seed_clusters(old, new, k=6, max_count=8, span=256):
        lo = max(0, -diag)
        hi = min(len(new), len(old) - diag)
        if end - start < 48:
            windows.append((diag, start - 8, end + 8, 6))
            continue
        # Regions of firmware that have moved typically still match outside of the
        # relocated pointers. Follow the diagonal while it continues to mostly match.
        while start > lo:
            s = max(lo, start - 128)
            if np.count_nonzero(new[s:start] == old[s + diag : start + diag]) < 0.3 * (start - s):
                start = max(lo, start - 16)
                break
            start = s
        while end < hi:
            e = min(hi, end + 128)
            if np.count_nonzero(new[end:e] == old[end + diag : e + diag]) < 0.3 * (e - end):
                end = min(hi, end + 16)
                break
            end = e
        windows.append((diag, start, end, 2))

    # Long runs of a single value (padding) are too common to seed from k byte matches.
    # Source them from the longest run of the same value in the original.
    def value_runs(a: np.ndarray):
        if len(a) < 2:
            return []
        run_start, run_end = _true_runs(a[1:] == a[:-1])
        keep = (run_end - run_start) >= 15
        return zip(
            a[run_start[keep]].tolist(),
            run_start[keep].tolist(),
            (run_end - run_start + 1)[keep].tolist(),
            strict=True,
        )

    longest: dict[int, tuple[int, int]] = {}
    for value, start, length in value_runs(old):
        if length > longest.get(value, (0, 0))[1]:
            longest[value] = (start, length)
    for value, start, length in value_runs(new):
        if value not in longest:
            continue
        old_start, old_length = longest[value]
        # Longer runs than exist in the original are constructed from repeated copies
        for _ in range(1024):
            chunk = min(length, old_length)
            windows.append((old_start - start, start, start + chunk, 2))
            start += chunk
            length -= chunk
            if length < 16:
                break

    # Merge overlapping windows on the same diagonal so that runs are not split
    windows.sort()
    merged: list[tuple[int, int, int, int]] = []
    for diag, start, end, min_len in windows:
        if merged and merged[-1][0] == diag and start <= merged[-1][2]:
            _, m_start, m_end, m_min_len = merged[-1]
            merged[-1] = (diag, m_start, max(m_end, end), min(m_min_len, min_len))
        else:
            merged.append((diag, start, end, min_len))

    runs = set()
    for diag, start, end, min_len in merged:
        runs.update(_diagonal_runs(old, new, diag, start, end, min_len))
    return runs


def _gap_runs(old: np.ndarray, new: np.ndarray, gaps: list[tuple]) -> set[tuple[int, int, int]]:
    """Short matching runs inside the WRITE regions of an encoding"""
    runs: set[tuple[int, int, int]] = set()
    if len(gaps) == 0:
        return runs
    positions = []
    for start, end, diag_before, diag_after in gaps:
        # Continuing on a neighbouring diagonal requires no address change
        for diag in {diag_before, diag_after}:
            runs.update(_diagonal_runs(old, new, diag, start, end, 2))
        positions.append(np.arange(start, max(start, end - 3)))

    # Other diagonals with short matches, which tend to align similar code
    for diag, start, end in _seed_clusters(old, new, 4, 4, 64, np.concatenate(positions)):
        found = _diagonal_runs(old, new, diag, start - 64, end + 64, 2)
        if sum(e - s for s, e, _ in found) >= 4:
            runs.update(found)
    return runs


def _shortest_path_encode(bin_new: bytes, runs: set[tuple[int, int, int]]) -> tuple[list[Instr], list[tuple]]:
    """Minimum size encoding of the new file from a set of candidate COPY runs

    Each run is (new start, new end, diagonal). Bytes between the runs that are used
    are written. Runs can be entered part way through, which handles overlapping runs.

    Shortest path over the runs, with the exact encoded size of the instructions as the
    cost. Each run has two states, outside a PATCH, or inside a PATCH after a COPY.
    """
    # Total order, so that the encoding does not depend on set iteration order
    tokens = sorted(runs, key=lambda r: (r[1], r[0], r[2]))
    # Node 0 is the start of the file, the final node is the end of the file
    ts = [0] + [r[0] for r in tokens] + [len(bin_new)]
    te = [0] + [r[1] for r in tokens] + [len(bin_new)]
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

    # [outside PATCH, inside PATCH] costs and the transitions that achieved them
    cost = [[math.inf, math.inf] for _ in ts]
    back: list[list[tuple]] = [[(), ()] for _ in ts]
    cost[0][0] = 0
    # Running minimum of (cost outside a PATCH - new offset), for long range transitions
    relay_offset: list[int] = []
    relay_node: list[int] = []
    relay_val = math.inf
    # Runs that contain the current offset
    covering: list[tuple[int, int]] = []
    next_start = 0

    for j in range(end_node):
        if j > 0:
            # Enter from the best prior node, writing everything in between. Covers
            # transitions not explicitly considered below (ADDR_SET_U32 reaches anywhere).
            x = ts[j]
            i = relay_node[bisect.bisect_right(relay_offset, x) - 1]
            G = x - te[i]
            if cost[i][0] <= cost[i][1] + 1:
                c, si, gap_mode = cost[i][0], 0, GAP_WRITE if G else GAP_NONE
            else:
                c, si, gap_mode = cost[i][1] + 1, 1, GAP_END_WRITE if G else GAP_END
            c += (_len_hdr_size(G) + G if G else 0) + _addr_size(td[j] - td[i])
            L = te[j] - x
            if c + _len_hdr_size(L) < cost[j][0]:
                cost[j][0] = c + _len_hdr_size(L)
                back[j][0] = (i, si, gap_mode, COPY)
            if c + 1 + _patch_copy_size(L) < cost[j][1]:
                cost[j][1] = c + 1 + _patch_copy_size(L)
                back[j][1] = (i, si, gap_mode, COPY_NEW_PATCH)

        c_out, c_in = cost[j]
        p = te[j]
        dj = td[j]
        v = min(c_out, c_in + 1) - p
        if v < relay_val:
            relay_val = v
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
            G = s - p
            L = te[k] - s
            if L <= 0:
                continue
            shift = td[k] - dj
            # Cost to be ready for the COPY, either inside a PATCH after a WRITE, or outside
            pre_patch = math.inf
            if G == 0:
                pre_out, out_state, out_gap = c_out, 0, GAP_NONE
                if c_in + 1 < pre_out:
                    pre_out, out_state, out_gap = c_in + 1, 1, GAP_END
            else:
                write = _len_hdr_size(G) + G
                pre_out, out_state, out_gap = c_out + write, 0, GAP_WRITE
                if G <= 255:
                    pre_patch = c_in + G + (G > 1)
                if c_in + 1 + write < pre_out:
                    pre_out, out_state, out_gap = c_in + 1 + write, 1, GAP_END_WRITE
            if shift:
                if pre_patch + 1 < pre_out:
                    pre_out, out_state, out_gap = pre_patch + 1, 1, GAP_PATCH_END
                pre_patch = math.inf
                pre_out += _addr_size(shift)

            ck = cost[k]
            hdr_L = _len_hdr_size(L)
            patch_L = _patch_copy_size(L)
            if pre_patch + patch_L < ck[1]:
                ck[1] = pre_patch + patch_L
                back[k][1] = (j, 1, GAP_PATCH, COPY_PATCH)
            if pre_patch + 1 + hdr_L < ck[0]:
                ck[0] = pre_patch + 1 + hdr_L
                back[k][0] = (j, 1, GAP_PATCH, COPY_END)
            if pre_out + hdr_L < ck[0]:
                ck[0] = pre_out + hdr_L
                back[k][0] = (j, out_state, out_gap, COPY)
            if pre_out + 1 + patch_L < ck[1]:
                ck[1] = pre_out + 1 + patch_L
                back[k][1] = (j, out_state, out_gap, COPY_NEW_PATCH)

        # Write the remainder of the file
        G = len(bin_new) - p
        options = [(c_out + (_len_hdr_size(G) + G if G else 0), 0, GAP_WRITE if G else GAP_NONE)]
        if G == 0:
            options.append((c_in + 1, 1, GAP_END))
        else:
            if G <= 255:
                options.append((c_in + G + (G > 1) + 1, 1, GAP_PATCH_END))
            options.append((c_in + 1 + _len_hdr_size(G) + G, 1, GAP_END_WRITE))
        c, sj, gap_mode = min(options)
        if c < cost[end_node][0]:
            cost[end_node][0] = c
            back[end_node][0] = (j, sj, gap_mode, None)

    # Recover the path
    path = []
    node, state = end_node, 0
    while node != 0:
        j, sj, gap_mode, copy_mode = back[node][state]
        path.append((j, node, gap_mode, copy_mode))
        node, state = j, sj

    # Construct the instructions
    builder = _InstrBuilder(bin_new)
    gaps = []
    for j, k, gap_mode, copy_mode in reversed(path):
        s = max(ts[k], te[j])
        G = s - te[j]
        if G:
            gaps.append((te[j], s, td[j], td[k]))
        if gap_mode in (GAP_END, GAP_END_WRITE):
            builder.patch_end()
        if gap_mode in (GAP_PATCH, GAP_PATCH_END, GAP_END_WRITE, GAP_WRITE):
            builder.write(G)
        if gap_mode == GAP_PATCH_END:
            builder.patch_end()
        if k == end_node:
            break
        target = s + td[k]
        if builder.old_offset != target:
            builder.set_addr(target)
        if copy_mode == COPY_END:
            builder.patch_end()
        elif copy_mode == COPY_NEW_PATCH:
            builder.patch_start()
        builder.copy(te[k] - s)
    assert builder.patch is None
    assert builder.new_offset == len(bin_new)
    return builder.instructions, gaps


def encode(bin_orig: bytes, bin_new: bytes) -> list[Instr]:
    """Encode the new file as instructions applied to the original file"""
    old = np.frombuffer(bin_orig, dtype=np.uint8)
    new = np.frombuffer(bin_new, dtype=np.uint8)

    runs = _candidate_runs(old, new)
    _, gaps = _shortest_path_encode(bin_new, runs)
    # Refine with the short matches available inside the regions that were written
    runs |= _gap_runs(old, new, gaps)
    instructions, _ = _shortest_path_encode(bin_new, runs)
    return instructions
