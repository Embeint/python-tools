#!/usr/bin/env python3

"""Greedy patch encoder, matching hashed substrings followed by cleanup passes"""

from infuse_iot.cpatch.instructions import CopyInstr, Instr, PatchInstr, SetAddrInstr, WriteInstr


def _naive_diff(old: bytes, new: bytes, hash_len: int = 8):
    """Construct basic runs of WRITE, COPY, and SET_ADDR instructions"""
    instr: list[Instr] = []
    old_offset = 0
    new_offset = 0
    write_start = 0
    write_pending = 0

    # Pre-hash original image
    pre_hash = {}
    prev_val = None
    for offset in range(len(old) - hash_len + 1):
        val = old[offset : offset + hash_len]
        if val == prev_val:
            continue
        if val not in pre_hash:
            pre_hash[val] = [offset]
        else:
            pre_hash[val].append(offset)
        prev_val = val

    # Loop until entire image is reconstructed
    while new_offset < len(new):
        val = new[new_offset : new_offset + hash_len]

        # If word exists in original image
        if val in pre_hash:
            if write_pending:
                instr.append(WriteInstr(new[write_start : write_start + write_pending]))
                write_pending = 0

            old_match = -100

            # Check to see if we have a match at current pointer
            if old_offset in pre_hash[val]:
                old_match = 0
                while (
                    (new_offset + old_match) < len(new)
                    and (old_offset + old_match) < len(old)
                    and new[new_offset + old_match] == old[old_offset + old_match]
                ):
                    old_match += 1

            max_match = old_match
            max_offset = old_offset

            # For each location in original image
            for orig_offset in pre_hash[val]:
                this_match = 0
                while (
                    (new_offset + this_match) < len(new)
                    and (orig_offset + this_match) < len(old)
                    and new[new_offset + this_match] == old[orig_offset + this_match]
                ):
                    this_match += 1

                if this_match > max_match and this_match > (old_match + 8):
                    max_match = this_match
                    max_offset = orig_offset

            if max_offset != old_offset:
                # Update memory address
                instr.append(SetAddrInstr(old_offset, max_offset))

            instr.append(CopyInstr(max_match, max_offset))
            new_offset += max_match
            old_offset = max_offset + max_match
        else:
            if write_pending == 0:
                write_start = new_offset
            write_pending += 1
            new_offset += 1
            old_offset += 1

    if write_pending:
        instr.append(WriteInstr(new[write_start : write_start + write_pending]))
        write_pending = 0

    return instr


def _cleanup_jumps(old: bytes, instructions: list[Instr]) -> list[Instr]:
    """Find locations that jumped backwards just to jump forward to original location"""

    merged: list[Instr] = []
    while len(instructions) > 0:
        instr = instructions.pop(0)
        replaced = False

        if isinstance(instr, SetAddrInstr):
            copy = instructions[0]
            assert isinstance(copy, CopyInstr)

            if len(instructions) >= 2 and isinstance(instructions[1], SetAddrInstr):
                # ADDR, COPY, ADRR
                if instr.shift == -instructions[1].shift:
                    # Replace with a write instead
                    merged.append(WriteInstr(old[instr.new : instr.new + copy.length]))
                    replaced = True
                    instructions.pop(0)
                    instructions.pop(0)
            elif (
                len(instructions) >= 3
                and isinstance(instructions[1], WriteInstr)
                and isinstance(instructions[2], SetAddrInstr)
                # ADDR, COPY, WRITE, ADRR
                and instr.shift == -instructions[2].shift
            ):
                write = instructions[1]
                # Replace with a merged write instead
                merged.append(WriteInstr(old[instr.new : instr.new + copy.length] + write.data))
                replaced = True
                instructions.pop(0)
                instructions.pop(0)
                instructions.pop(0)

        if not replaced:
            merged.append(instr)

    # We may have sequential WRITE commands due to the merging, do a pass
    cleaned = [merged[0]]
    for instr in merged[1:]:
        if isinstance(instr, WriteInstr) and isinstance(cleaned[-1], WriteInstr):
            cleaned[-1].data += instr.data
        else:
            cleaned.append(instr)
    return cleaned


def _merge_operations(instructions: list[Instr]) -> list[Instr]:
    """Merge runs of COPY and WRITE into PATCH"""
    merged: list[Instr] = []
    to_merge: list[Instr] = []

    def finalise():
        nonlocal merged
        nonlocal to_merge
        if len(to_merge) == 0:
            return
        elif len(to_merge) == 1:
            merged.append(to_merge[0])
        else:
            merged.append(PatchInstr(to_merge))
        to_merge = []

    for instr in instructions:
        if (isinstance(instr, CopyInstr) and instr.length < 128) or (
            isinstance(instr, WriteInstr) and len(to_merge) > 0 and len(instr.data) < 256
        ):
            to_merge.append(instr)
        else:
            finalise()
            merged.append(instr)

    if len(to_merge) > 0:
        finalise()
    return merged


def _write_crack(old: bytes, instructions: list[Instr]) -> list[Instr]:
    """Crack a WRITE operation into a [WRITE,COPY,WRITE] if COPY is at least 2 bytes"""

    cracked: list[Instr] = []
    old_offset = 0

    while len(instructions):
        instr = instructions.pop(0)

        if isinstance(instr, CopyInstr):
            old_offset = instr.original_offset + instr.length
            cracked.append(instr)
            continue
        elif isinstance(instr, SetAddrInstr):
            old_offset = instr.new
            cracked.append(instr)
            continue
        assert isinstance(instr, WriteInstr)

        split = [0]
        for idx, b in enumerate(instr.data):
            if old_offset + idx >= len(old):
                # Add remainder of write to last split
                split[-1] += len(instr.data) - idx
                break
            if old[old_offset + idx] != b:
                if len(split) % 2:
                    # Already on a WRITE
                    split[-1] += 1
                else:
                    # On a COPY, swap to a WRITE
                    split.append(1)
                continue

            if len(split) % 2:
                # On a WRITE, switch to a COPY
                split.append(1)
            else:
                # Already on a COPY
                split[-1] += 1

        # Total data count should remain the same
        assert sum(split) == len(instr.data)

        if len(split) % 2 == 0:
            # Ended on a copy
            copy_len = split.pop()
            if len(instructions) > 0 and isinstance(instructions[0], CopyInstr):
                # Push the match into the next instruction if possible
                instructions[0].length += copy_len
                instructions[0].original_offset -= copy_len
            else:
                # Merge the copy back into the previous write
                split[-1] += copy_len

        # Should now have N*[WRITE, COPY] + [WRITE]
        assert len(split) % 2 == 1

        # Construct the [WRITE, COPY] pairs
        offset = 0
        while len(split) > 1:
            write_len = split.pop(0)
            copy_len = split.pop(0)

            # If the copy was only 1 byte, roll it back
            if copy_len == 1:
                split[0] += write_len + copy_len
            else:
                # WRITE is empty if the data started with a match
                if write_len:
                    cracked.append(WriteInstr(instr.data[offset : offset + write_len]))
                offset += write_len
                cracked.append(CopyInstr(copy_len, old_offset + offset))
                offset += copy_len

        # Append the final WRITE
        write_len = split.pop()
        cracked.append(WriteInstr(instr.data[offset : offset + write_len]))

    return cracked


def encode(bin_orig: bytes, bin_new: bytes) -> list[Instr]:
    """Encode the new file as instructions applied to the original file"""
    best_patch = []
    best_patch_len = 2**32

    # Find best diff across range
    for i in range(4, 8):
        instr = _naive_diff(bin_orig, bin_new, i)
        instr = _cleanup_jumps(bin_orig, instr)
        instr = _write_crack(bin_orig, instr)
        instr = _merge_operations(instr)
        patch_len = sum([len(i) for i in instr])

        if patch_len < best_patch_len:
            best_patch = instr
            best_patch_len = patch_len

    return best_patch
