#!/usr/bin/env python3

"""Element stream patch format (version 3)

Patch data is a preamble describing how the original image moved, followed by a stream of
elements. There is no instruction framing: each element copies bytes from the original file,
then performs a single operation.

Element header byte: `(copy << 4) | op`. A copy of 15 is followed by a uvarint of `copy - 15`.
Operations:

* `0..HISTORY_SIZE`: add `history[op]` to the next 16 bits of the original (little endian)
* `ADD_EXPLICIT`: as above, with an explicit u16 delta that is inserted into the history
* `LITERAL_1`: one literal byte follows
* `LITERAL`: uvarint of `n - 2`, then `n` literal bytes
* `LITERAL_SHIFT`: uvarint of `n - 1`, `n` literal bytes, then a shift as for `SHIFT`
* `SHIFT`: zigzag svarint added to the original file offset
* `NONE`: copy only (`copy == 0` is reserved for extended operations)

Additions and literals advance the original file offset by the number of bytes output.

Every copy relocates the sites it fully contains according to the preamble: Thumb-2 BL / B.W
instructions are re-targeted by the shift of the original image offset they reference. 32 bit
words that point into the original image, or into another region (such as RAM), are moved by
the shift of the address they reference.

Relocation (only when a flag is set). Sites are found from the original file alone, so whether
an offset is a site does not depend on where copies start or end:

* Branch site (`FLAG_BRANCH`): even offset `a` with `a + 4 <= len(original)` where the
  halfwords `h1` at `a` and `h2` at `a + 2` are a BL / B.W (encoding T4) instruction:
  `h1 & 0xF800 == 0xF000` and `h2 & 0xD000` is `0xD000` or `0x9000`. It is not a site if the
  halfwords at `a - 2` and `a` are also such an instruction, so only the first of a chain of
  overlapping patterns is a site. The target is `t = a + 4 + imm`. If `0 <= t < len(original)`,
  the instruction is output with the offset `t + shift(t) - (o + 4)`, where `o` is the output
  file offset of the site, and the same instruction type (`h2 & 0xD000`). If `t` is outside the
  original file, or the new offset is outside of `-2^24 <= offset < 2^24`, it is output unchanged.
* Pointer site (`FLAG_POINTER`): offset `a` that is a multiple of 4 with `a + 4 <= len(original)`,
  where no branch site starts at `a - 2`, `a` or `a + 2`, and the little endian u32 `v` at `a`
  points into the original image (`(v - base) mod 2^32 < len(original)`) or into a region
  (`(v - region.base) mod 2^32 < region.length`). The original image takes precedence over the
  regions, then the first matching region in preamble order. The output is
  `(v + shift(target)) mod 2^32` using the map of the image or region, where `target` is the
  offset of `v` into it.
* `shift(t)` is the shift of the last map entry with an offset `<= t`, 0 if there is none.
* A copy of the original from `old` to `old + n` scans `address` from `old` rounded up to even.
  If a site starts at `address` and `address + 4 <= old + n`, its relocated bytes are output and
  the scan continues at `address + 4`, otherwise at `address + 2`. Sites never overlap.

Pointers are relocated on the assumption that the new image runs at the same base address as
the original.

Preamble:

* `u8 flags`
* if any flag is set, the original image map: `u16 count`, then `count` entries of
  `(u24 original offset, i24 shift)` sorted by offset
* if `FLAG_POINTER`, `u32 base` (address of the original image), `u8 count`, then `count`
  regions of `u32 base`, `u32 length` and a map of region offsets as above

Map entries are fixed width so that appliers can binary search them in place instead of
caching them in RAM.
"""

import bisect
import dataclasses

HISTORY_SIZE = 10
ADD_EXPLICIT = 10
LITERAL_1 = 11
LITERAL = 12
LITERAL_SHIFT = 13
SHIFT = 14
NONE = 15

# Relocate Thumb-2 BL / B.W instructions
FLAG_BRANCH = 1 << 0
# Relocate absolute pointers into the original image
FLAG_POINTER = 1 << 1

MAP_ENTRY_LEN = 6


class ValidationError(Exception):
    """Invalid element stream"""


class History:
    """Most recently used 16 bit deltas"""

    INITIAL = [1, 0xFFFF, 2, 0xFFFE, 3, 0xFFFD, 4, 0xFFFC, 5, 0xFFFB]

    def __init__(self):
        self.deltas = list(self.INITIAL)

    def find(self, delta: int) -> int | None:
        try:
            return self.deltas.index(delta)
        except ValueError:
            return None

    def use(self, index: int | None, delta: int) -> int:
        """Update the history after a delta has been used, returning the delta"""
        # Explicit deltas evict the least recently used entry
        if index is None:
            self.deltas.pop()
        else:
            delta = self.deltas.pop(index)
        self.deltas.insert(0, delta)
        return delta


@dataclasses.dataclass(frozen=True)
class Add:
    index: int


@dataclasses.dataclass(frozen=True)
class AddExplicit:
    delta: int


@dataclasses.dataclass(frozen=True)
class Literal:
    data: bytes


@dataclasses.dataclass(frozen=True)
class LiteralShift:
    """Literal, then a shift of the original file offset"""

    data: bytes
    shift: int


@dataclasses.dataclass(frozen=True)
class Shift:
    shift: int


@dataclasses.dataclass(frozen=True)
class NoOp:
    pass


Op = Add | AddExplicit | Literal | LiteralShift | Shift | NoOp


def uvarint_len(v: int) -> int:
    length = 1
    while v >= 0x80:
        v >>= 7
        length += 1
    return length


def _zigzag(v: int) -> int:
    return (v << 1) if v >= 0 else ((-v) << 1) - 1


def svarint_len(v: int) -> int:
    return uvarint_len(_zigzag(v))


def _uvarint(v: int) -> bytes:
    out = bytearray()
    while v >= 0x80:
        out.append((v & 0x7F) | 0x80)
        v >>= 7
    out.append(v)
    return bytes(out)


def _get_uvarint(b: bytes, offset: int) -> tuple[int, int]:
    v = 0
    for shift in range(0, 64, 7):
        if offset >= len(b):
            raise ValidationError("Truncated varint")
        byte = b[offset]
        offset += 1
        v |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return v, offset
    raise ValidationError("Varint too long")


def _get_svarint(b: bytes, offset: int) -> tuple[int, int]:
    v, offset = _get_uvarint(b, offset)
    return (v >> 1) ^ -(v & 1), offset


def _take(b: bytes, offset: int, length: int) -> tuple[bytes, int]:
    if offset + length > len(b):
        raise ValidationError("Truncated element")
    return b[offset : offset + length], offset + length


@dataclasses.dataclass(frozen=True)
class Element:
    copy: int
    op: Op

    def __bytes__(self) -> bytes:
        op = self.op
        if isinstance(op, Add):
            code = op.index
        elif isinstance(op, AddExplicit):
            code = ADD_EXPLICIT
        elif isinstance(op, Literal):
            code = LITERAL_1 if len(op.data) == 1 else LITERAL
        elif isinstance(op, LiteralShift):
            code = LITERAL_SHIFT
        elif isinstance(op, Shift):
            code = SHIFT
        else:
            code = NONE
        assert self.copy != 0 or code != NONE
        out = bytearray([min(self.copy, 15) << 4 | code])
        if self.copy >= 15:
            out += _uvarint(self.copy - 15)
        if isinstance(op, AddExplicit):
            out += op.delta.to_bytes(2, "little")
        elif isinstance(op, Literal):
            assert len(op.data) != 0
            if len(op.data) > 1:
                out += _uvarint(len(op.data) - 2)
            out += op.data
        elif isinstance(op, LiteralShift):
            out += _uvarint(len(op.data) - 1) + op.data + _uvarint(_zigzag(op.shift))
        elif isinstance(op, Shift):
            out += _uvarint(_zigzag(op.shift))
        return bytes(out)

    def __len__(self) -> int:
        length = 1 + (uvarint_len(self.copy - 15) if self.copy >= 15 else 0)
        op = self.op
        if isinstance(op, AddExplicit):
            length += 2
        elif isinstance(op, Literal):
            length += len(op.data) + (uvarint_len(len(op.data) - 2) if len(op.data) > 1 else 0)
        elif isinstance(op, LiteralShift):
            length += uvarint_len(len(op.data) - 1) + len(op.data) + svarint_len(op.shift)
        elif isinstance(op, Shift):
            length += svarint_len(op.shift)
        return length

    @classmethod
    def from_bytes(cls, b: bytes, offset: int) -> tuple["Element", int]:
        header, offset = _take(b, offset, 1)
        copy = header[0] >> 4
        if copy == 15:
            extra, offset = _get_uvarint(b, offset)
            copy += extra
        code = header[0] & 0x0F
        op: Op
        if code == ADD_EXPLICIT:
            delta, offset = _take(b, offset, 2)
            op = AddExplicit(int.from_bytes(delta, "little"))
        elif code == LITERAL_1:
            data, offset = _take(b, offset, 1)
            op = Literal(data)
        elif code == LITERAL:
            length, offset = _get_uvarint(b, offset)
            data, offset = _take(b, offset, length + 2)
            op = Literal(data)
        elif code == LITERAL_SHIFT:
            length, offset = _get_uvarint(b, offset)
            data, offset = _take(b, offset, length + 1)
            shift, offset = _get_svarint(b, offset)
            op = LiteralShift(data, shift)
        elif code == SHIFT:
            shift, offset = _get_svarint(b, offset)
            op = Shift(shift)
        elif code == NONE:
            if copy == 0:
                raise ValidationError("Unsupported extended operation")
            op = NoOp()
        else:
            op = Add(code)
        return cls(copy, op), offset

    def __str__(self) -> str:
        out = f" COPY: {self.copy:6d} bytes"
        op = self.op
        if isinstance(op, Add):
            out += f", ADD: history[{op.index}]"
        elif isinstance(op, AddExplicit):
            out += f", ADD: {op.delta:04x}"
        elif isinstance(op, (Literal, LiteralShift)):
            more = "..." if len(op.data) > 64 else ""
            out += f", WRITE: {len(op.data)} bytes ({op.data[:64].hex()}{more})"
            if isinstance(op, LiteralShift):
                out += f", SHIFT: {op.shift:+d}"
        elif isinstance(op, Shift):
            out += f", SHIFT: {op.shift:+d}"
        return out


def _map_bytes(entries: list[tuple[int, int]]) -> bytes:
    out = len(entries).to_bytes(2, "little")
    for start, shift in entries:
        out += start.to_bytes(3, "little") + shift.to_bytes(3, "little", signed=True)
    return out


def _map_from_bytes(b: bytes, offset: int) -> tuple[list[tuple[int, int]], int]:
    count_bytes, offset = _take(b, offset, 2)
    entries: list[tuple[int, int]] = []
    for _ in range(int.from_bytes(count_bytes, "little")):
        e, offset = _take(b, offset, MAP_ENTRY_LEN)
        start = int.from_bytes(e[0:3], "little")
        if entries and entries[-1][0] >= start:
            raise ValidationError("Relocation map not sorted")
        entries.append((start, int.from_bytes(e[3:6], "little", signed=True)))
    return entries, offset


def _map_shift(entries: list[tuple[int, int]], length: int, offset: int) -> int:
    """Shift of an offset into a region of `length` bytes"""
    if not 0 <= offset < length:
        return 0
    idx = bisect.bisect_right(entries, offset, key=lambda e: e[0])
    return entries[idx - 1][1] if idx else 0


@dataclasses.dataclass
class Region:
    """Address range outside of the original image whose pointers are relocated"""

    base: int
    length: int
    # (region offset, shift), sorted by offset
    map: list[tuple[int, int]] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class Preamble:
    """How the original image moved, used to relocate the sites inside copies"""

    flags: int = 0
    # Address of the start of the original image, for FLAG_POINTER
    base: int = 0
    # (original offset, shift), sorted by offset
    map: list[tuple[int, int]] = dataclasses.field(default_factory=list)
    # Other address ranges whose pointers are relocated, for FLAG_POINTER
    regions: list[Region] = dataclasses.field(default_factory=list)

    def __bytes__(self) -> bytes:
        out = bytes([self.flags])
        if self.flags:
            out += _map_bytes(self.map)
        if self.flags & FLAG_POINTER:
            out += self.base.to_bytes(4, "little") + bytes([len(self.regions)])
            for region in self.regions:
                out += region.base.to_bytes(4, "little") + region.length.to_bytes(4, "little")
                out += _map_bytes(region.map)
        return out

    def __len__(self) -> int:
        length = 1
        if self.flags:
            length += 2 + MAP_ENTRY_LEN * len(self.map)
        if self.flags & FLAG_POINTER:
            length += 5 + sum(10 + MAP_ENTRY_LEN * len(r.map) for r in self.regions)
        return length

    @classmethod
    def from_bytes(cls, b: bytes, offset: int) -> tuple["Preamble", int]:
        flags_byte, offset = _take(b, offset, 1)
        flags = flags_byte[0]
        if flags & ~(FLAG_BRANCH | FLAG_POINTER):
            raise ValidationError(f"Unsupported relocation flags ({flags:02x})")
        preamble = cls(flags)
        if flags:
            preamble.map, offset = _map_from_bytes(b, offset)
        if flags & FLAG_POINTER:
            base, offset = _take(b, offset, 4)
            preamble.base = int.from_bytes(base, "little")
            count, offset = _take(b, offset, 1)
            for _ in range(count[0]):
                fields, offset = _take(b, offset, 8)
                region_map, offset = _map_from_bytes(b, offset)
                preamble.regions.append(
                    Region(int.from_bytes(fields[0:4], "little"), int.from_bytes(fields[4:8], "little"), region_map)
                )
        return preamble, offset


def thumb_branch_offset(h1: int, h2: int) -> int | None:
    """Offset of a Thumb-2 BL or B.W (encoding T4) instruction, None if not a branch"""
    if (h1 & 0xF800) != 0xF000 or (h2 & 0xD000) not in (0xD000, 0x9000):
        return None
    s = (h1 >> 10) & 1
    i1 = 1 - (((h2 >> 13) & 1) ^ s)
    i2 = 1 - (((h2 >> 11) & 1) ^ s)
    offset = (s << 24) | (i1 << 23) | (i2 << 22) | ((h1 & 0x3FF) << 12) | ((h2 & 0x7FF) << 1)
    return offset - (1 << 25) if s else offset


def thumb_branch_encode(h2_original: int, offset: int) -> tuple[int, int] | None:
    """Encode a branch offset, keeping the instruction type of `h2_original`. None if out of range"""
    if not -(1 << 24) <= offset < (1 << 24) or offset & 1:
        return None
    value = offset & 0x1FFFFFF
    s = value >> 24
    j1 = (1 - ((value >> 23) & 1)) ^ s
    j2 = (1 - ((value >> 22) & 1)) ^ s
    h1 = 0xF000 | (s << 10) | ((value >> 12) & 0x3FF)
    h2 = (h2_original & 0xD000) | (j1 << 13) | (j2 << 11) | ((value >> 1) & 0x7FF)
    return h1, h2


class Relocator:
    """Relocation applied by copies, as described by a `Preamble`"""

    def __init__(self, old: bytes, preamble: Preamble):
        self.old = old
        self.preamble = preamble

    @property
    def enabled(self) -> bool:
        return self.preamble.flags != 0

    def shift(self, offset: int) -> int:
        """Shift of an original image offset"""
        return _map_shift(self.preamble.map, len(self.old), offset)

    def _u16(self, offset: int) -> int:
        return self.old[offset] | self.old[offset + 1] << 8

    def _branch_pattern(self, address: int) -> int | None:
        if address < 0 or address & 1 or address + 4 > len(self.old):
            return None
        return thumb_branch_offset(self._u16(address), self._u16(address + 2))

    def branch_site(self, address: int) -> int | None:
        """Offset of the BL / B.W starting at `address`, if relocating copies treat it as a site

        A branch pattern is a site unless the previous halfword also starts a branch pattern, so
        that sites do not depend on where a copy starts.
        """
        if not self.preamble.flags & FLAG_BRANCH:
            return None
        offset = self._branch_pattern(address)
        if offset is None or self._branch_pattern(address - 2) is not None:
            return None
        return offset

    def pointer_target(self, address: int) -> tuple[int | None, int] | None:
        """Where the word at `address` points, if it is relocated as a pointer: the region (None
        for the original image) and the offset within it"""
        if not self.preamble.flags & FLAG_POINTER or address & 3 or address + 4 > len(self.old):
            return None
        value = int.from_bytes(self.old[address : address + 4], "little")
        target = (value - self.preamble.base) & 0xFFFFFFFF
        found: tuple[int | None, int] | None = None
        if target < len(self.old):
            found = (None, target)
        else:
            for i, region in enumerate(self.preamble.regions):
                target = (value - region.base) & 0xFFFFFFFF
                if target < region.length:
                    found = (i, target)
                    break
        # Words that overlap a branch site are not pointers
        if found is None or any(self.branch_site(address + i) is not None for i in (-2, 0, 2)):
            return None
        return found

    def pointer_site(self, address: int) -> bool:
        return self.pointer_target(address) is not None

    def relocate(self, address: int, new_address: int) -> bytes | None:
        """Bytes output for the site at original offset `address` when copied to `new_address`.
        None if there is no site at `address`."""
        offset = self.branch_site(address)
        if offset is not None:
            target = address + 4 + offset
            if 0 <= target < len(self.old):
                encoded = thumb_branch_encode(self._u16(address + 2), target + self.shift(target) - (new_address + 4))
                if encoded is not None:
                    return encoded[0].to_bytes(2, "little") + encoded[1].to_bytes(2, "little")
            return self.old[address : address + 4]
        pointer = self.pointer_target(address)
        if pointer is None:
            return None
        region, target = pointer
        if region is None:
            shift = self.shift(target)
        else:
            r = self.preamble.regions[region]
            shift = _map_shift(r.map, r.length, target)
        value = int.from_bytes(self.old[address : address + 4], "little")
        return ((value + shift) & 0xFFFFFFFF).to_bytes(4, "little")

    def copy(self, old: int, length: int, new: int) -> bytes:
        """Output of copying `length` bytes from original offset `old` to output offset `new`"""
        out = bytearray(self.old[old : old + length])
        if not self.enabled:
            return bytes(out)
        # Sites never overlap, and are always halfword aligned
        address = old + (old & 1)
        while address + 4 <= old + length:
            relocated = self.relocate(address, address - old + new)
            if relocated is not None:
                rel = address - old
                out[rel : rel + 4] = relocated
                address += 4
            else:
                address += 2
        return bytes(out)


def decode(data: bytes) -> tuple[Preamble, list[Element]]:
    """Decode version 3 patch data"""
    preamble, offset = Preamble.from_bytes(data, 0)
    elements = []
    while offset < len(data):
        element, offset = Element.from_bytes(data, offset)
        elements.append(element)
    return preamble, elements


def encode(preamble: Preamble, elements: list[Element]) -> bytes:
    return bytes(preamble) + b"".join(bytes(e) for e in elements)


def apply(original: bytes, preamble: Preamble, elements: list[Element]) -> bytes:
    """Construct the output file from the original file and decoded patch data"""
    reloc = Relocator(original, preamble)
    history = History()
    out = bytearray()
    offset = 0

    def in_range(length: int) -> int:
        if offset < 0 or offset + length > len(original):
            raise ValidationError("Read outside of original file")
        return offset

    for element in elements:
        # Literals can move the offset outside of the original file, it is only checked on reads
        if element.copy:
            out += reloc.copy(in_range(element.copy), element.copy, len(out))
            offset += element.copy
        op = element.op
        if isinstance(op, (Add, AddExplicit)):
            if isinstance(op, Add):
                delta = history.use(op.index, 0)
            else:
                delta = history.use(None, op.delta)
            start = in_range(2)
            value = original[start] | original[start + 1] << 8
            out += ((value + delta) & 0xFFFF).to_bytes(2, "little")
            offset += 2
        elif isinstance(op, Literal):
            out += op.data
            offset += len(op.data)
        elif isinstance(op, LiteralShift):
            out += op.data
            offset += len(op.data) + op.shift
        elif isinstance(op, Shift):
            offset += op.shift
    return bytes(out)


def validation(original: bytes) -> tuple[Preamble, list[Element]]:
    """Preamble and elements that run every operation and relocation type, reconstructing
    `original`. Sites are relocated by copying them to other sites that they reproduce when
    relocated, with the copies that keep every other relocated site in place splitting it."""
    n = len(original)
    missing = "Input file does not contain the values required for element stream validation"
    if n >= 1 << 24:
        raise ValueError("Input file too large for element stream validation")

    def val16(o: int) -> int:
        return original[o] | original[o + 1] << 8

    def val32(o: int) -> int:
        return int.from_bytes(original[o : o + 4], "little")

    def fits(shift: int) -> bool:
        return shift != 0 and -(1 << 23) <= shift < 1 << 23

    # Phase 1, every operation, is output before `n // 2`. Relocated sites are output after it.
    branches = Relocator(original, Preamble(FLAG_BRANCH))
    branch_sites = [a for a in range(0, n - 3, 2) if branches.branch_site(a) is not None]

    def branch_target(a: int) -> int:
        offset = branches.branch_site(a)
        assert offset is not None
        return a + 4 + offset

    def word_site(a: int) -> bool:
        return all(branches.branch_site(a + i) is None for i in (-2, 0, 2))

    # A branch copied to another branch of the same type, by the shift of its target
    branch = None
    for dst in (a for a in branch_sites if a >= n // 2):
        for src in branch_sites:
            t_src, t_dst = branch_target(src), branch_target(dst)
            if (
                src != dst
                and 0 <= t_src < n
                and fits(t_dst - t_src)
                and val16(src + 2) & 0xD000 == val16(dst + 2) & 0xD000
            ):
                branch = (src, dst, t_src, t_dst - t_src)
                break
        if branch is not None:
            break
    if branch is None:
        raise ValueError(missing)
    b_src, b_dst, b_target, b_shift = branch

    def word_pair(start: int, accept) -> tuple[int, int]:
        """Source and destination words, where the destination is at or after `start`"""
        for dst in range((start + 3) & ~3, n - 3, 4):
            for src in range(max(dst - 1024, 0), min(dst + 1024, n - 3), 4):
                if src != dst and word_site(src) and fits(val32(dst) - val32(src)) and accept(src):
                    return src, dst
        raise ValueError(missing)

    def pointer_target(value: int) -> int | None:
        """Original image offset to point `value` at, such that the image base is valid"""
        lo, hi = max(0, value - (0xFFFFFFFF - n)), min(n - 1, value)
        for t in (n // 2, lo, hi, lo + 2, hi - 2):
            if lo <= t <= hi and abs(t - b_target) >= 2:
                return t
        return None

    # A pointer into the original image, with the base chosen so that it points at `p_target`
    p_src, p_dst = word_pair(b_dst + 4, lambda src: pointer_target(val32(src)) is not None)
    p_target = pointer_target(val32(p_src))
    assert p_target is not None
    base = val32(p_src) - p_target
    p_shift = val32(p_dst) - val32(p_src)

    # A pointer into a region outside of the original image
    def region_pointer(src: int) -> bool:
        return src != p_src and (val32(src) - base) & 0xFFFFFFFF >= n

    r_src, r_dst = word_pair(p_dst + 4, region_pointer)
    r_value = val32(r_src)

    image_map = [(b_target, b_shift), (b_target + 1, 0), (p_target, p_shift), (p_target + 1, 0)]
    preamble = Preamble(
        FLAG_BRANCH | FLAG_POINTER,
        base,
        sorted(e for e in image_map if e[0] < n),
        [
            Region(r_value, 1, [(0, val32(r_dst) - r_value)]),
            # The first matching region is used
            Region(r_value, 1, []),
            # Pointers into the original image use the image map
            Region(base + p_target, 1, []),
        ],
    )
    reloc = Relocator(original, preamble)
    # Sites that are not output unchanged when copied in place
    moved = [a for a in range(0, n - 3, 2) if reloc.relocate(a, a) not in (None, original[a : a + 4])]

    elements: list[Element] = []
    pending = out = old = 0

    def op(o: Op):
        nonlocal pending
        elements.append(Element(pending, o))
        pending = 0

    def copy(length: int):
        """Copy in place, splitting the sites that would change"""
        nonlocal pending, out, old
        if old != out:
            op(Shift(out - old))
            old = out
        end = out + length
        for a in moved[bisect.bisect_left(moved, out) :]:
            if a + 4 > end:
                break
            pending += a + 2 - out
            op(NoOp())
            out = old = a + 2
        pending += end - out
        out = old = end

    def copy_to(x: int):
        if x > out:
            copy(x - out)

    def copy_exact(length: int):
        """Copy of exactly `length` bytes, after any sites that it would split"""
        while True:
            i = bisect.bisect_left(moved, out)
            if i == len(moved) or moved[i] + 4 > out + length:
                break
            copy_to(moved[i] + 2)
            op(NoOp())
        copy(length)
        op(NoOp())

    def literal(length: int, shift: int = 0):
        nonlocal out, old
        data = original[out : out + length]
        op(LiteralShift(data, shift) if shift else Literal(data))
        out += length
        old += length + shift

    def shift(s: int):
        nonlocal old
        op(Shift(s))
        old += s

    # Every copy length encoding
    for length in [*range(1, 16), 142, 143]:
        copy_exact(length)
    # Every literal length encoding, and shifts in both directions, including outside of the
    # original file (offsets are only checked on reads)
    for length in (1, 2, 200):
        copy(3)
        literal(length)
    copy(4)
    shift(2 * n + 100_000)
    shift(-(2 * n + 100_000))
    copy(4)
    literal(3, 70)
    literal(130, -70)

    # Additions of each history entry, read from a different offset in the original such
    # that the output still matches the original
    history = History()
    positions: dict[int, list[int]] = {}
    for o in range(n - 1):
        positions.setdefault(val16(o), []).append(o)

    def addition(x: int, y: int, index: int | None, delta: int):
        nonlocal out, old
        copy_to(x)
        if old != y:
            shift(y - old)
        op(Add(index) if index is not None else AddExplicit(delta))
        history.use(index, delta)
        out, old = x + 2, y + 2

    def history_addition(accept):
        for x in range(out, n // 2 - 2):
            for index, delta in enumerate(history.deltas):
                for y in positions.get((val16(x) - delta) & 0xFFFF, []):
                    if accept(index, y):
                        addition(x, y, index, 0)
                        return
        raise ValueError(missing)

    for target in range(HISTORY_SIZE - 1, -1, -1):
        history_addition(lambda index, _, target=target: index == target)
    # An addition carrying out of the low byte
    history_addition(lambda index, y: (val16(y) & 0xFF) + (history.deltas[index] & 0xFF) > 0xFF)
    # An explicit delta that is not in the history
    for x in range(out, n // 2 - 3):
        delta = (val16(x) - val16(x + 1)) & 0xFFFF
        if history.find(delta) is None:
            addition(x, x + 1, None, delta)
            break
    else:
        raise ValueError(missing)

    # Sites copied to the sites they reproduce when relocated
    for src, dst in ((b_src, b_dst), (p_src, p_dst), (r_src, r_dst)):
        copy_to(dst)
        shift(src - old)
        pending += 4
        out, old = dst + 4, src + 4
    copy_to(n)
    if pending:
        op(NoOp())
    return preamble, elements


def op_counts(elements: list[Element]) -> list[tuple[str, int]]:
    """Element operation usage counts"""
    names = ["ADD", "ADD_EXPLICIT", "LITERAL_1", "LITERAL", "LITERAL_SHIFT", "SHIFT", "NONE"]
    counts = dict.fromkeys(names, 0)
    for element in elements:
        op = element.op
        if isinstance(op, Add):
            counts["ADD"] += 1
        elif isinstance(op, AddExplicit):
            counts["ADD_EXPLICIT"] += 1
        elif isinstance(op, Literal):
            counts["LITERAL_1" if len(op.data) == 1 else "LITERAL"] += 1
        elif isinstance(op, LiteralShift):
            counts["LITERAL_SHIFT"] += 1
        elif isinstance(op, Shift):
            counts["SHIFT"] += 1
        else:
            counts["NONE"] += 1
    return list(counts.items())
