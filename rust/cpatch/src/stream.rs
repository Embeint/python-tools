//! Element stream patch format (version 3)
//!
//! Patch data is a preamble describing how the original image moved, followed by a stream of
//! elements. There is no instruction framing: each element copies bytes from the original file,
//! then performs a single operation.
//!
//! Element header byte: `(copy << 4) | op`. A copy of 15 is followed by a uvarint of
//! `copy - 15`. Operations:
//!
//! * `0..HISTORY_SIZE`: add `history[op]` to the next 16 bits of the original (little endian)
//! * `ADD_EXPLICIT`: as above, with an explicit u16 delta that is inserted into the history
//! * `LITERAL_1`: one literal byte follows
//! * `LITERAL`: uvarint of `n - 2`, then `n` literal bytes
//! * `LITERAL_SHIFT`: uvarint of `n - 1`, `n` literal bytes, then a shift as for `SHIFT`
//! * `SHIFT`: zigzag svarint added to the original file offset
//! * `NONE`: copy only (`copy == 0` is reserved for extended operations)
//!
//! Additions and literals advance the original file offset by the number of bytes output.
//!
//! Every copy relocates the sites it fully contains according to the preamble:
//! Thumb-2 BL / B.W instructions are re-targeted by the shift of the original image offset they
//! reference. 32 bit words that point into the original image, or into another region (such as
//! RAM), are moved by the shift of the address they reference.
//!
//! Relocation (only when a flag is set). Sites are found from the original file alone, so
//! whether an offset is a site does not depend on where copies start or end:
//!
//! * Branch site (`FLAG_BRANCH`): even offset `a` with `a + 4 <= len(original)` where the
//!   halfwords `h1` at `a` and `h2` at `a + 2` are a BL / B.W (encoding T4) instruction:
//!   `h1 & 0xF800 == 0xF000` and `h2 & 0xD000` is `0xD000` or `0x9000`. It is not a site if the
//!   halfwords at `a - 2` and `a` are also such an instruction, so only the first of a chain of
//!   overlapping patterns is a site. The target is `t = a + 4 + imm`. If `0 <= t < len(original)`,
//!   the instruction is output with the offset `t + shift(t) - (o + 4)`, where `o` is the output
//!   file offset of the site, and the same instruction type (`h2 & 0xD000`). If `t` is outside the
//!   original file, or the new offset is outside of `-2^24 <= offset < 2^24`, it is output
//!   unchanged.
//! * Pointer site (`FLAG_POINTER`): offset `a` that is a multiple of 4 with
//!   `a + 4 <= len(original)`, where no branch site starts at `a - 2`, `a` or `a + 2`, and the
//!   little endian u32 `v` at `a` points into the original image
//!   (`(v - base) mod 2^32 < len(original)`) or into a region
//!   (`(v - region.base) mod 2^32 < region.length`). The original image takes precedence over the
//!   regions, then the first matching region in preamble order. The output is
//!   `(v + shift(target)) mod 2^32` using the map of the image or region, where `target` is the
//!   offset of `v` into it.
//! * `shift(t)` is the shift of the last map entry with an offset `<= t`, 0 if there is none.
//! * A copy of the original from `old` to `old + n` scans `address` from `old` rounded up to
//!   even. If a site starts at `address` and `address + 4 <= old + n`, its relocated bytes are
//!   output and the scan continues at `address + 4`, otherwise at `address + 2`. Sites never
//!   overlap.
//!
//! Pointers are relocated on the assumption that the new image runs at the same base address as
//! the original.
//!
//! Preamble:
//!
//! * `u8 flags`
//! * if any flag is set, the original image map: `u16 count`, then `count` entries of
//!   `(u24 original offset, i24 shift)` sorted by offset
//! * if `FLAG_POINTER`, `u32 base` (address of the original image), `u8 count`, then `count`
//!   regions of `u32 base`, `u32 length` and a map of region offsets as above
//!
//! Map entries are fixed width so that appliers can binary search them in place instead of
//! caching them in RAM.

use std::collections::HashMap;
use std::fmt;

pub const HISTORY_SIZE: usize = 10;
pub const ADD_EXPLICIT: u8 = 10;
pub const LITERAL_1: u8 = 11;
pub const LITERAL: u8 = 12;
pub const LITERAL_SHIFT: u8 = 13;
pub const SHIFT: u8 = 14;
pub const NONE: u8 = 15;

/// Relocate Thumb-2 BL / B.W instructions
pub const FLAG_BRANCH: u8 = 1 << 0;
/// Relocate absolute pointers into the original image
pub const FLAG_POINTER: u8 = 1 << 1;

pub const MAP_ENTRY_LEN: usize = 6;

const HISTORY_INITIAL: [u16; HISTORY_SIZE] = [1, 0xFFFF, 2, 0xFFFE, 3, 0xFFFD, 4, 0xFFFC, 5, 0xFFFB];

/// Most recently used 16 bit deltas
#[derive(Clone)]
pub struct History {
    pub deltas: [u16; HISTORY_SIZE],
}

impl Default for History {
    fn default() -> Self {
        History {
            deltas: HISTORY_INITIAL,
        }
    }
}

impl History {
    pub fn find(&self, delta: u16) -> Option<usize> {
        self.deltas.iter().position(|&d| d == delta)
    }

    /// Update the history after a delta has been used, returning the delta
    pub fn use_delta(&mut self, index: Option<usize>, delta: u16) -> u16 {
        // Explicit deltas evict the least recently used entry
        let (index, delta) = match index {
            Some(i) => (i, self.deltas[i]),
            None => (HISTORY_SIZE - 1, delta),
        };
        self.deltas.copy_within(0..index, 1);
        self.deltas[0] = delta;
        delta
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Op {
    Add(u8),
    AddExplicit(u16),
    Literal(Vec<u8>),
    /// Literal, then a shift of the original file offset
    LiteralShift(Vec<u8>, i64),
    Shift(i64),
    None,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Element {
    pub copy: usize,
    pub op: Op,
}

pub fn uvarint_len(mut v: u64) -> usize {
    let mut len = 1;
    while v >= 0x80 {
        v >>= 7;
        len += 1;
    }
    len
}

fn zigzag(v: i64) -> u64 {
    ((v << 1) ^ (v >> 63)) as u64
}

pub fn svarint_len(v: i64) -> usize {
    uvarint_len(zigzag(v))
}

fn put_uvarint(out: &mut Vec<u8>, mut v: u64) {
    while v >= 0x80 {
        out.push(v as u8 | 0x80);
        v >>= 7;
    }
    out.push(v as u8);
}

fn get_uvarint(b: &[u8], offset: &mut usize) -> Result<u64, String> {
    let mut v = 0u64;
    for shift in (0..64).step_by(7) {
        let byte = *b.get(*offset).ok_or("Truncated varint")?;
        *offset += 1;
        v |= ((byte & 0x7F) as u64) << shift;
        if byte & 0x80 == 0 {
            return Ok(v);
        }
    }
    Err("Varint too long".into())
}

fn get_svarint(b: &[u8], offset: &mut usize) -> Result<i64, String> {
    let v = get_uvarint(b, offset)?;
    Ok((v >> 1) as i64 ^ -((v & 1) as i64))
}

/// Literal length from its encoded value, which excludes the minimum length
fn literal_len(encoded: u64, min: usize) -> Result<usize, String> {
    usize::try_from(encoded)
        .ok()
        .and_then(|len| len.checked_add(min))
        .ok_or_else(|| "Literal too long".into())
}

fn take<'a>(b: &'a [u8], offset: &mut usize, len: usize) -> Result<&'a [u8], String> {
    let end = offset.checked_add(len).ok_or("Truncated element")?;
    let data = b.get(*offset..end).ok_or("Truncated element")?;
    *offset += len;
    Ok(data)
}

impl Element {
    pub fn encode(&self, out: &mut Vec<u8>) {
        let op = match &self.op {
            Op::Add(index) => *index,
            Op::AddExplicit(_) => ADD_EXPLICIT,
            Op::Literal(data) if data.len() == 1 => LITERAL_1,
            Op::Literal(_) => LITERAL,
            Op::LiteralShift(..) => LITERAL_SHIFT,
            Op::Shift(_) => SHIFT,
            Op::None => NONE,
        };
        assert!(self.copy != 0 || op != NONE);
        out.push((self.copy.min(15) as u8) << 4 | op);
        if self.copy >= 15 {
            put_uvarint(out, (self.copy - 15) as u64);
        }
        match &self.op {
            Op::AddExplicit(delta) => out.extend_from_slice(&delta.to_le_bytes()),
            Op::Literal(data) => {
                assert!(!data.is_empty());
                if data.len() > 1 {
                    put_uvarint(out, (data.len() - 2) as u64);
                }
                out.extend_from_slice(data);
            }
            Op::LiteralShift(data, shift) => {
                put_uvarint(out, (data.len() - 1) as u64);
                out.extend_from_slice(data);
                put_uvarint(out, zigzag(*shift));
            }
            Op::Shift(shift) => put_uvarint(out, zigzag(*shift)),
            Op::Add(_) | Op::None => {}
        }
    }

    pub fn encoded_len(&self) -> usize {
        let copy = if self.copy >= 15 {
            uvarint_len((self.copy - 15) as u64)
        } else {
            0
        };
        1 + copy
            + match &self.op {
                Op::AddExplicit(_) => 2,
                Op::Literal(data) if data.len() == 1 => 1,
                Op::Literal(data) => uvarint_len((data.len() - 2) as u64) + data.len(),
                Op::LiteralShift(data, shift) => {
                    uvarint_len((data.len() - 1) as u64) + data.len() + svarint_len(*shift)
                }
                Op::Shift(shift) => svarint_len(*shift),
                Op::Add(_) | Op::None => 0,
            }
    }

    pub fn decode(b: &[u8], offset: &mut usize) -> Result<Element, String> {
        let header = take(b, offset, 1)?[0];
        let mut copy = (header >> 4) as usize;
        if copy == 15 {
            copy = usize::try_from(get_uvarint(b, offset)?)
                .ok()
                .and_then(|extra| copy.checked_add(extra))
                .ok_or("Copy length too long")?;
        }
        let op = match header & 0x0F {
            ADD_EXPLICIT => {
                let d = take(b, offset, 2)?;
                Op::AddExplicit(u16::from_le_bytes([d[0], d[1]]))
            }
            LITERAL_1 => Op::Literal(take(b, offset, 1)?.to_vec()),
            LITERAL => {
                let len = literal_len(get_uvarint(b, offset)?, 2)?;
                Op::Literal(take(b, offset, len)?.to_vec())
            }
            LITERAL_SHIFT => {
                let len = literal_len(get_uvarint(b, offset)?, 1)?;
                let data = take(b, offset, len)?.to_vec();
                Op::LiteralShift(data, get_svarint(b, offset)?)
            }
            SHIFT => Op::Shift(get_svarint(b, offset)?),
            NONE if copy == 0 => return Err("Unsupported extended operation".into()),
            NONE => Op::None,
            index => Op::Add(index),
        };
        Ok(Element { copy, op })
    }
}

impl fmt::Display for Element {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, " COPY: {:6} bytes", self.copy)?;
        match &self.op {
            Op::Add(index) => write!(f, ", ADD: history[{index}]"),
            Op::AddExplicit(delta) => write!(f, ", ADD: {delta:04x}"),
            Op::Literal(data) | Op::LiteralShift(data, _) => {
                let hex: String = data.iter().take(64).map(|b| format!("{b:02x}")).collect();
                let more = if data.len() > 64 { "..." } else { "" };
                write!(f, ", WRITE: {} bytes ({hex}{more})", data.len())?;
                match self.op {
                    Op::LiteralShift(_, shift) => write!(f, ", SHIFT: {shift:+}"),
                    _ => Ok(()),
                }
            }
            Op::Shift(shift) => write!(f, ", SHIFT: {shift:+}"),
            Op::None => Ok(()),
        }
    }
}

/// Address range outside of the original image whose pointers are relocated
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Region {
    pub base: u32,
    pub length: u32,
    /// (region offset, shift), sorted by offset
    pub map: Vec<(u32, i32)>,
}

/// How the original image moved, used to relocate the sites inside copies
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Preamble {
    pub flags: u8,
    /// Address of the start of the original image, for `FLAG_POINTER`
    pub base: u32,
    /// (original offset, shift), sorted by offset
    pub map: Vec<(u32, i32)>,
    /// Other address ranges whose pointers are relocated, for `FLAG_POINTER`
    pub regions: Vec<Region>,
}

fn encode_map(map: &[(u32, i32)], out: &mut Vec<u8>) {
    out.extend_from_slice(&(map.len() as u16).to_le_bytes());
    for &(start, shift) in map {
        out.extend_from_slice(&start.to_le_bytes()[..3]);
        out.extend_from_slice(&shift.to_le_bytes()[..3]);
    }
}

fn decode_map(b: &[u8], offset: &mut usize) -> Result<Vec<(u32, i32)>, String> {
    let count = u16::from_le_bytes(take(b, offset, 2)?.try_into().unwrap());
    let mut map: Vec<(u32, i32)> = Vec::with_capacity(count as usize);
    for _ in 0..count {
        let e = take(b, offset, MAP_ENTRY_LEN)?;
        let start = u32::from_le_bytes([e[0], e[1], e[2], 0]);
        // Sign extend from 24 bits
        let shift = (i32::from_le_bytes([e[3], e[4], e[5], 0]) << 8) >> 8;
        if map.last().is_some_and(|&(s, _)| s >= start) {
            return Err("Relocation map not sorted".into());
        }
        map.push((start, shift));
    }
    Ok(map)
}

fn u32_from(b: &[u8], offset: &mut usize) -> Result<u32, String> {
    Ok(u32::from_le_bytes(take(b, offset, 4)?.try_into().unwrap()))
}

impl Preamble {
    pub fn encode(&self, out: &mut Vec<u8>) {
        out.push(self.flags);
        if self.flags != 0 {
            encode_map(&self.map, out);
        }
        if self.flags & FLAG_POINTER != 0 {
            out.extend_from_slice(&self.base.to_le_bytes());
            out.push(self.regions.len() as u8);
            for region in &self.regions {
                out.extend_from_slice(&region.base.to_le_bytes());
                out.extend_from_slice(&region.length.to_le_bytes());
                encode_map(&region.map, out);
            }
        }
    }

    pub fn encoded_len(&self) -> usize {
        let mut len = 1;
        if self.flags != 0 {
            len += 2 + MAP_ENTRY_LEN * self.map.len();
        }
        if self.flags & FLAG_POINTER != 0 {
            len += 5;
            for region in &self.regions {
                len += 10 + MAP_ENTRY_LEN * region.map.len();
            }
        }
        len
    }

    pub fn decode(b: &[u8], offset: &mut usize) -> Result<Preamble, String> {
        let flags = take(b, offset, 1)?[0];
        if flags & !(FLAG_BRANCH | FLAG_POINTER) != 0 {
            return Err(format!("Unsupported relocation flags ({flags:02x})"));
        }
        let mut preamble = Preamble {
            flags,
            ..Default::default()
        };
        if flags != 0 {
            preamble.map = decode_map(b, offset)?;
        }
        if flags & FLAG_POINTER != 0 {
            preamble.base = u32_from(b, offset)?;
            for _ in 0..take(b, offset, 1)?[0] {
                preamble.regions.push(Region {
                    base: u32_from(b, offset)?,
                    length: u32_from(b, offset)?,
                    map: decode_map(b, offset)?,
                });
            }
        }
        Ok(preamble)
    }
}

/// Shift of an offset into a region of `length` bytes
fn map_shift(map: &[(u32, i32)], length: usize, offset: i64) -> i64 {
    if !(0..length as i64).contains(&offset) {
        return 0;
    }
    let idx = map.partition_point(|&(start, _)| start as i64 <= offset);
    if idx == 0 { 0 } else { map[idx - 1].1 as i64 }
}

/// Offset of a Thumb-2 BL or B.W (encoding T4) instruction, None if not a branch
pub fn thumb_branch_offset(h1: u16, h2: u16) -> Option<i32> {
    if (h1 & 0xF800) != 0xF000 || ((h2 & 0xD000) != 0xD000 && (h2 & 0xD000) != 0x9000) {
        return None;
    }
    let (h1, h2) = (h1 as u32, h2 as u32);
    let s = (h1 >> 10) & 1;
    let i1 = 1 - (((h2 >> 13) & 1) ^ s);
    let i2 = 1 - (((h2 >> 11) & 1) ^ s);
    let value = (s << 24) | (i1 << 23) | (i2 << 22) | ((h1 & 0x3FF) << 12) | ((h2 & 0x7FF) << 1);
    // Sign extend from 25 bits
    Some(((value << 7) as i32) >> 7)
}

/// Encode a branch offset, keeping the instruction type of `h2_original`. None if out of range
pub fn thumb_branch_encode(h2_original: u16, offset: i64) -> Option<(u16, u16)> {
    if !(-(1 << 24)..(1 << 24)).contains(&offset) || offset & 1 != 0 {
        return None;
    }
    let value = (offset as u32) & 0x1FF_FFFF;
    let s = value >> 24;
    let j1 = (1 - ((value >> 23) & 1)) ^ s;
    let j2 = (1 - ((value >> 22) & 1)) ^ s;
    let h1 = 0xF000 | (s << 10) | ((value >> 12) & 0x3FF);
    let h2 = (h2_original as u32 & 0xD000) | (j1 << 13) | (j2 << 11) | ((value >> 1) & 0x7FF);
    Some((h1 as u16, h2 as u16))
}

fn u16_at(data: &[u8], offset: usize) -> u16 {
    u16::from_le_bytes([data[offset], data[offset + 1]])
}

fn u32_at(data: &[u8], offset: usize) -> u32 {
    u32::from_le_bytes(data[offset..offset + 4].try_into().unwrap())
}

/// Relocation applied by copies, as described by a `Preamble`
pub struct Relocator<'a> {
    old: &'a [u8],
    preamble: &'a Preamble,
}

impl<'a> Relocator<'a> {
    pub fn new(old: &'a [u8], preamble: &'a Preamble) -> Self {
        Relocator { old, preamble }
    }

    pub fn enabled(&self) -> bool {
        self.preamble.flags != 0
    }

    /// Shift of an original image offset
    pub fn shift(&self, offset: i64) -> i64 {
        map_shift(&self.preamble.map, self.old.len(), offset)
    }

    fn branch_pattern(&self, address: i64) -> Option<i32> {
        if address < 0 || address & 1 != 0 || address + 4 > self.old.len() as i64 {
            return None;
        }
        let a = address as usize;
        thumb_branch_offset(u16_at(self.old, a), u16_at(self.old, a + 2))
    }

    /// Offset of the BL / B.W starting at `address`, if relocating copies treat it as a site
    ///
    /// A branch pattern is a site unless the previous halfword also starts a branch pattern, so
    /// that sites do not depend on where a copy starts.
    pub fn branch_site(&self, address: i64) -> Option<i32> {
        if self.preamble.flags & FLAG_BRANCH == 0 {
            return None;
        }
        let offset = self.branch_pattern(address)?;
        if self.branch_pattern(address - 2).is_some() {
            return None;
        }
        Some(offset)
    }

    /// Where the word at `address` points, if it is relocated as a pointer: the region (None for
    /// the original image) and the offset within it
    pub fn pointer_target(&self, address: i64) -> Option<(Option<usize>, i64)> {
        if self.preamble.flags & FLAG_POINTER == 0 || address & 3 != 0 || address + 4 > self.old.len() as i64 {
            return None;
        }
        let value = u32_at(self.old, address as usize);
        let target = value.wrapping_sub(self.preamble.base);
        let found = if (target as usize) < self.old.len() {
            Some((None, target as i64))
        } else {
            self.preamble.regions.iter().enumerate().find_map(|(i, r)| {
                let target = value.wrapping_sub(r.base);
                (target < r.length).then_some((Some(i), target as i64))
            })
        };
        // Words that overlap a branch site are not pointers
        if found.is_none()
            || self.branch_site(address - 2).is_some()
            || self.branch_site(address).is_some()
            || self.branch_site(address + 2).is_some()
        {
            return None;
        }
        found
    }

    pub fn pointer_site(&self, address: i64) -> bool {
        self.pointer_target(address).is_some()
    }

    /// Bytes output for the site at original offset `address` when copied to `new_address`.
    /// None if there is no site at `address`.
    pub fn relocate(&self, address: i64, new_address: i64) -> Option<[u8; 4]> {
        let a = address as usize;
        if let Some(offset) = self.branch_site(address) {
            let target = address + 4 + offset as i64;
            let mut out: [u8; 4] = self.old[a..a + 4].try_into().unwrap();
            if (0..self.old.len() as i64).contains(&target)
                && let Some((h1, h2)) =
                    thumb_branch_encode(u16_at(self.old, a + 2), target + self.shift(target) - (new_address + 4))
            {
                out[..2].copy_from_slice(&h1.to_le_bytes());
                out[2..].copy_from_slice(&h2.to_le_bytes());
            }
            return Some(out);
        }
        let (region, target) = self.pointer_target(address)?;
        let shift = match region {
            None => self.shift(target),
            Some(i) => {
                let r = &self.preamble.regions[i];
                map_shift(&r.map, r.length as usize, target)
            }
        };
        Some(
            (u32_at(self.old, a) as i64 + shift).to_le_bytes()[..4]
                .try_into()
                .unwrap(),
        )
    }

    /// Output of copying `length` bytes from original offset `old` to output offset `new`
    pub fn copy(&self, old: usize, length: usize, new: usize, out: &mut Vec<u8>) {
        let start = out.len();
        out.extend_from_slice(&self.old[old..old + length]);
        if !self.enabled() {
            return;
        }
        // Sites never overlap, and are always halfword aligned
        let mut address = old + (old & 1);
        while address + 4 <= old + length {
            if let Some(bytes) = self.relocate(address as i64, (address - old + new) as i64) {
                let rel = start + address - old;
                out[rel..rel + 4].copy_from_slice(&bytes);
                address += 4;
            } else {
                address += 2;
            }
        }
    }
}

/// Decode version 3 patch data
pub fn decode(data: &[u8]) -> Result<(Preamble, Vec<Element>), String> {
    let mut offset = 0;
    let preamble = Preamble::decode(data, &mut offset)?;
    let mut elements = Vec::new();
    while offset < data.len() {
        elements.push(Element::decode(data, &mut offset)?);
    }
    Ok((preamble, elements))
}

pub fn encode(preamble: &Preamble, elements: &[Element]) -> Vec<u8> {
    let mut data = Vec::new();
    preamble.encode(&mut data);
    for element in elements {
        element.encode(&mut data);
    }
    data
}

/// Construct the output file from the original file and decoded patch data
pub fn apply(original: &[u8], preamble: &Preamble, elements: &[Element], out: &mut Vec<u8>) -> Result<(), String> {
    let reloc = Relocator::new(original, preamble);
    let mut history = History::default();
    let mut offset = 0i64;
    let in_range = |offset: i64, length: usize| -> Result<usize, String> {
        usize::try_from(offset)
            .ok()
            .filter(|&start| start.checked_add(length).is_some_and(|end| end <= original.len()))
            .ok_or_else(|| "Read outside of original file".into())
    };
    let advance = |offset: i64, by: i64| -> Result<i64, String> {
        offset
            .checked_add(by)
            .ok_or_else(|| "Original file offset overflow".into())
    };
    for element in elements {
        // Literals can move the offset outside of the original file, it is only checked on reads
        if element.copy > 0 {
            let start = in_range(offset, element.copy)?;
            reloc.copy(start, element.copy, out.len(), out);
            offset += element.copy as i64;
        }
        match &element.op {
            Op::Add(_) | Op::AddExplicit(_) => {
                let (index, delta) = match element.op {
                    Op::Add(index) => (Some(index as usize), 0),
                    Op::AddExplicit(delta) => (None, delta),
                    _ => unreachable!(),
                };
                let delta = history.use_delta(index, delta);
                let start = in_range(offset, 2)?;
                out.extend_from_slice(&u16_at(original, start).wrapping_add(delta).to_le_bytes());
                offset += 2;
            }
            Op::Literal(data) => {
                out.extend_from_slice(data);
                offset = advance(offset, data.len() as i64)?;
            }
            Op::LiteralShift(data, shift) => {
                out.extend_from_slice(data);
                offset = advance(advance(offset, data.len() as i64)?, *shift)?;
            }
            Op::Shift(shift) => offset = advance(offset, *shift)?,
            Op::None => {}
        }
    }
    Ok(())
}

/// Builds the element stream of a validation patch, tracking file offsets
struct ValidationBuilder<'a> {
    original: &'a [u8],
    /// Sites that are not output unchanged when copied in place
    moved: Vec<i64>,
    elements: Vec<Element>,
    history: History,
    pending: usize,
    out: i64,
    old: i64,
}

impl ValidationBuilder<'_> {
    fn op(&mut self, op: Op) {
        self.elements.push(Element { copy: self.pending, op });
        self.pending = 0;
    }

    fn shift(&mut self, shift: i64) {
        self.op(Op::Shift(shift));
        self.old += shift;
    }

    /// Copy in place, splitting the sites that would change
    fn copy(&mut self, length: i64) {
        if self.old != self.out {
            self.shift(self.out - self.old);
        }
        let end = self.out + length;
        let first = self.moved.partition_point(|&a| a < self.out);
        for i in first..self.moved.len() {
            let a = self.moved[i];
            if a + 4 > end {
                break;
            }
            self.pending += (a + 2 - self.out) as usize;
            self.op(Op::None);
            self.out = a + 2;
            self.old = a + 2;
        }
        self.pending += (end - self.out) as usize;
        self.out = end;
        self.old = end;
    }

    fn copy_to(&mut self, x: i64) {
        if x > self.out {
            self.copy(x - self.out);
        }
    }

    /// Copy of exactly `length` bytes, after any sites that it would split
    fn copy_exact(&mut self, length: i64) {
        loop {
            let i = self.moved.partition_point(|&a| a < self.out);
            if i == self.moved.len() || self.moved[i] + 4 > self.out + length {
                break;
            }
            self.copy_to(self.moved[i] + 2);
            self.op(Op::None);
        }
        self.copy(length);
        self.op(Op::None);
    }

    fn literal(&mut self, length: i64, shift: i64) {
        let data = self.original[self.out as usize..(self.out + length) as usize].to_vec();
        self.op(if shift != 0 {
            Op::LiteralShift(data, shift)
        } else {
            Op::Literal(data)
        });
        self.out += length;
        self.old += length + shift;
    }

    /// Output the original at `x` by adding a delta to the original at `y`
    fn addition(&mut self, x: i64, y: i64, index: Option<usize>, delta: u16) {
        self.copy_to(x);
        if self.old != y {
            self.shift(y - self.old);
        }
        self.op(match index {
            Some(i) => Op::Add(i as u8),
            None => Op::AddExplicit(delta),
        });
        self.history.use_delta(index, delta);
        self.out = x + 2;
        self.old = y + 2;
    }
}

/// Preamble and elements that run every operation and relocation type, reconstructing
/// `original`. Sites are relocated by copying them to other sites that they reproduce when
/// relocated, with the copies that keep every other relocated site in place splitting it.
pub fn validation(original: &[u8]) -> Result<(Preamble, Vec<Element>), String> {
    let n = original.len() as i64;
    let missing = || "Input file does not contain the values required for element stream validation".to_string();
    if n >= 1 << 24 {
        return Err("Input file too large for element stream validation".into());
    }
    let val16 = |o: i64| u16_at(original, o as usize);
    let val32 = |o: i64| u32_at(original, o as usize) as i64;
    let fits = |shift: i64| shift != 0 && (-(1 << 23)..1 << 23).contains(&shift);

    // Phase 1, every operation, is output before `n / 2`. Relocated sites are output after it.
    let branch_preamble = Preamble {
        flags: FLAG_BRANCH,
        ..Default::default()
    };
    let branches = Relocator::new(original, &branch_preamble);
    let branch_sites: Vec<i64> = (0..n - 3)
        .step_by(2)
        .filter(|&a| branches.branch_site(a).is_some())
        .collect();
    let branch_target = |a: i64| a + 4 + branches.branch_site(a).unwrap() as i64;
    let word_site = |a: i64| [-2, 0, 2].iter().all(|i| branches.branch_site(a + i).is_none());

    // A branch copied to another branch of the same type, by the shift of its target
    let (b_src, b_dst, b_target, b_shift) = branch_sites
        .iter()
        .filter(|&&dst| dst >= n / 2)
        .find_map(|&dst| {
            branch_sites.iter().find_map(|&src| {
                let (t_src, t_dst) = (branch_target(src), branch_target(dst));
                (src != dst
                    && (0..n).contains(&t_src)
                    && fits(t_dst - t_src)
                    && val16(src + 2) & 0xD000 == val16(dst + 2) & 0xD000)
                    .then_some((src, dst, t_src, t_dst - t_src))
            })
        })
        .ok_or_else(missing)?;

    // Source and destination words, where the destination is at or after `start`
    let word_pair = |start: i64, accept: &dyn Fn(i64) -> bool| -> Result<(i64, i64), String> {
        for dst in (((start + 3) & !3)..n - 3).step_by(4) {
            for src in ((dst - 1024).max(0)..(dst + 1024).min(n - 3)).step_by(4) {
                if src != dst && word_site(src) && fits(val32(dst) - val32(src)) && accept(src) {
                    return Ok((src, dst));
                }
            }
        }
        Err(missing())
    };

    // Original image offset to point `value` at, such that the image base is valid
    let pointer_target = |value: i64| {
        let (lo, hi) = ((value - (0xFFFF_FFFF - n)).max(0), (n - 1).min(value));
        [n / 2, lo, hi, lo + 2, hi - 2]
            .into_iter()
            .find(|&t| lo <= t && t <= hi && (t - b_target).abs() >= 2)
    };

    // A pointer into the original image, with the base chosen so that it points at `p_target`
    let (p_src, p_dst) = word_pair(b_dst + 4, &|src| pointer_target(val32(src)).is_some())?;
    let p_target = pointer_target(val32(p_src)).unwrap();
    let base = val32(p_src) - p_target;
    let p_shift = val32(p_dst) - val32(p_src);

    // A pointer into a region outside of the original image
    let (r_src, r_dst) = word_pair(p_dst + 4, &|src| src != p_src && (val32(src) - base) & 0xFFFF_FFFF >= n)?;
    let r_value = val32(r_src);

    let mut map: Vec<(u32, i32)> = [
        (b_target, b_shift),
        (b_target + 1, 0),
        (p_target, p_shift),
        (p_target + 1, 0),
    ]
    .into_iter()
    .filter(|e| e.0 < n)
    .map(|(t, shift)| (t as u32, shift as i32))
    .collect();
    map.sort_unstable();
    let region = |base: i64, map: Vec<(u32, i32)>| Region {
        base: base as u32,
        length: 1,
        map,
    };
    let preamble = Preamble {
        flags: FLAG_BRANCH | FLAG_POINTER,
        base: base as u32,
        map,
        regions: vec![
            region(r_value, vec![(0, (val32(r_dst) - r_value) as i32)]),
            // The first matching region is used
            region(r_value, Vec::new()),
            // Pointers into the original image use the image map
            region(base + p_target, Vec::new()),
        ],
    };
    let reloc = Relocator::new(original, &preamble);
    let moved = (0..n - 3)
        .step_by(2)
        .filter(|&a| {
            reloc
                .relocate(a, a)
                .is_some_and(|b| b[..] != original[a as usize..a as usize + 4])
        })
        .collect();

    let mut b = ValidationBuilder {
        original,
        moved,
        elements: Vec::new(),
        history: History::default(),
        pending: 0,
        out: 0,
        old: 0,
    };

    // Every copy length encoding
    for length in (1..16).chain([142, 143]) {
        b.copy_exact(length);
    }
    // Every literal length encoding, and shifts in both directions, including outside of the
    // original file (offsets are only checked on reads)
    for length in [1, 2, 200] {
        b.copy(3);
        b.literal(length, 0);
    }
    b.copy(4);
    b.shift(2 * n + 100_000);
    b.shift(-(2 * n + 100_000));
    b.copy(4);
    b.literal(3, 70);
    b.literal(130, -70);

    // Additions of each history entry, read from a different offset in the original such
    // that the output still matches the original
    let mut positions: HashMap<u16, Vec<i64>> = HashMap::new();
    for o in 0..n - 1 {
        positions.entry(val16(o)).or_default().push(o);
    }
    let history_addition = |b: &mut ValidationBuilder, accept: &dyn Fn(usize, u16, i64) -> bool| {
        for x in b.out..n / 2 - 2 {
            for (index, delta) in b.history.deltas.into_iter().enumerate() {
                for &y in positions.get(&val16(x).wrapping_sub(delta)).into_iter().flatten() {
                    if accept(index, delta, y) {
                        b.addition(x, y, Some(index), 0);
                        return Ok(());
                    }
                }
            }
        }
        Err(missing())
    };
    for target in (0..HISTORY_SIZE).rev() {
        history_addition(&mut b, &|index, _, _| index == target)?;
    }
    // An addition carrying out of the low byte
    history_addition(&mut b, &|_, delta, y| (val16(y) & 0xFF) + (delta & 0xFF) > 0xFF)?;
    // An explicit delta that is not in the history
    let x = (b.out..n / 2 - 3)
        .find(|&x| b.history.find(val16(x).wrapping_sub(val16(x + 1))).is_none())
        .ok_or_else(missing)?;
    b.addition(x, x + 1, None, val16(x).wrapping_sub(val16(x + 1)));

    // Sites copied to the sites they reproduce when relocated
    for (src, dst) in [(b_src, b_dst), (p_src, p_dst), (r_src, r_dst)] {
        b.copy_to(dst);
        b.shift(src - b.old);
        b.pending += 4;
        b.out = dst + 4;
        b.old = src + 4;
    }
    b.copy_to(n);
    if b.pending > 0 {
        b.op(Op::None);
    }
    Ok((preamble, b.elements))
}

/// Element operation usage counts
pub fn op_counts(elements: &[Element]) -> Vec<(&'static str, usize)> {
    let mut counts = [0usize; 7];
    for element in elements {
        let i = match element.op {
            Op::Add(_) => 0,
            Op::AddExplicit(_) => 1,
            Op::Literal(ref d) if d.len() == 1 => 2,
            Op::Literal(_) => 3,
            Op::LiteralShift(..) => 4,
            Op::Shift(_) => 5,
            Op::None => 6,
        };
        counts[i] += 1;
    }
    [
        "ADD",
        "ADD_EXPLICIT",
        "LITERAL_1",
        "LITERAL",
        "LITERAL_SHIFT",
        "SHIFT",
        "NONE",
    ]
    .into_iter()
    .zip(counts)
    .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn elements_round_trip() {
        let elements = vec![
            Element {
                copy: 0,
                op: Op::Add(0),
            },
            Element {
                copy: 14,
                op: Op::Add(9),
            },
            Element {
                copy: 15,
                op: Op::AddExplicit(0x1234),
            },
            Element {
                copy: 142,
                op: Op::Literal(vec![1]),
            },
            Element {
                copy: 143,
                op: Op::Literal(vec![1, 2]),
            },
            Element {
                copy: 1 << 20,
                op: Op::Literal(vec![7; 300]),
            },
            Element {
                copy: 3,
                op: Op::Shift(-64),
            },
            Element {
                copy: 0,
                op: Op::LiteralShift(vec![5], 63),
            },
            Element {
                copy: 2,
                op: Op::LiteralShift(vec![9; 200], -(1 << 20)),
            },
            Element {
                copy: 0,
                op: Op::Shift(1 << 30),
            },
            Element { copy: 1, op: Op::None },
        ];
        for element in &elements {
            let mut data = Vec::new();
            element.encode(&mut data);
            assert_eq!(data.len(), element.encoded_len());
            let mut offset = 0;
            assert_eq!(&Element::decode(&data, &mut offset).unwrap(), element);
            assert_eq!(offset, data.len());
        }
        let preamble = Preamble {
            flags: FLAG_BRANCH | FLAG_POINTER,
            base: 0x0801_0000,
            map: vec![(0x10, -5), (0x1000, 0x7F_FFFF), (0xFF_FFFF, -0x80_0000)],
            regions: vec![Region {
                base: 0x2000_0000,
                length: 0x4_0000,
                map: vec![(0x100, 8)],
            }],
        };
        let data = encode(&preamble, &elements);
        assert_eq!(decode(&data).unwrap(), (preamble, elements));
    }

    #[test]
    fn malformed_streams_are_rejected() {
        let original = [0u8; 64];
        let preamble = Preamble::default();
        let apply_data = |data: &[u8]| decode(data).and_then(|(p, e)| apply(&original, &p, &e, &mut Vec::new()));
        // Copy and literal lengths that overflow
        let mut huge = vec![0, 0xF0 | NONE];
        huge.extend([0xFF; 9]);
        huge.push(0x01);
        assert!(apply_data(&huge).is_err());
        let mut literal = vec![0, LITERAL];
        literal.extend([0xFF; 9]);
        literal.push(0x01);
        assert!(apply_data(&literal).is_err());
        // Shifts that overflow the original file offset
        let shifts = [
            Element {
                copy: 0,
                op: Op::Shift(i64::MAX),
            },
            Element {
                copy: 0,
                op: Op::Shift(i64::MAX),
            },
        ];
        assert!(apply(&original, &preamble, &shifts, &mut Vec::new()).is_err());
        let read = [
            Element {
                copy: 0,
                op: Op::Shift(i64::MAX - 4),
            },
            Element { copy: 8, op: Op::None },
        ];
        assert!(apply(&original, &preamble, &read, &mut Vec::new()).is_err());
    }

    #[test]
    fn history_move_to_front() {
        let mut history = History::default();
        assert_eq!(history.use_delta(Some(2), 0), 2);
        assert_eq!(history.deltas[..3], [2, 1, 0xFFFF]);
        assert_eq!(history.use_delta(None, 0x1234), 0x1234);
        assert_eq!(history.deltas[0], 0x1234);
        assert_eq!(history.find(6), None);
        assert_eq!(history.use_delta(Some(HISTORY_SIZE - 1), 0), 5);
    }

    #[test]
    fn thumb_branches_round_trip() {
        let mut state = 7u64;
        for _ in 0..100_000 {
            state = state
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1442695040888963407);
            let offset = (((state >> 20) as i64) % (1 << 24)) & !1;
            for h2_original in [0xF800, 0x9000] {
                let (h1, h2) = thumb_branch_encode(h2_original, offset).unwrap();
                assert_eq!(thumb_branch_offset(h1, h2), Some(offset as i32));
            }
        }
        // BL +0
        assert_eq!(thumb_branch_encode(0xF800, 0), Some((0xF000, 0xF800)));
        assert_eq!(thumb_branch_encode(0xF800, 1 << 24), None);
    }

    #[test]
    fn relocation() {
        // BL at 0 targeting 0x100, pointer at 8 to base + 0x100, RAM pointer at 12
        let mut old = vec![0u8; 0x200];
        let (h1, h2) = thumb_branch_encode(0xF800, 0x100 - 4).unwrap();
        old[0..2].copy_from_slice(&h1.to_le_bytes());
        old[2..4].copy_from_slice(&h2.to_le_bytes());
        old[8..12].copy_from_slice(&0x1000_0100u32.to_le_bytes());
        old[12..16].copy_from_slice(&0x2000_0010u32.to_le_bytes());
        let preamble = Preamble {
            flags: FLAG_BRANCH | FLAG_POINTER,
            base: 0x1000_0000,
            map: vec![(0x80, 0x20)],
            regions: vec![Region {
                base: 0x2000_0000,
                length: 0x1000,
                map: vec![(0x8, -4)],
            }],
        };
        let reloc = Relocator::new(&old, &preamble);
        let mut out = Vec::new();
        reloc.copy(0, 16, 0, &mut out);
        let (h1, h2) = thumb_branch_encode(0xF800, 0x120 - 4).unwrap();
        assert_eq!(out[0..4], [h1.to_le_bytes(), h2.to_le_bytes()].concat()[..]);
        assert_eq!(out[8..12], 0x1000_0120u32.to_le_bytes());
        assert_eq!(out[12..16], 0x2000_000Cu32.to_le_bytes());
        // Sites that are not fully copied are not relocated
        let mut out = Vec::new();
        reloc.copy(0, 11, 0, &mut out);
        assert_eq!(out[8..11], old[8..11]);
    }
}
