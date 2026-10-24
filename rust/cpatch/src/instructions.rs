//! Patch file instructions (mirrors `infuse_iot.cpatch.instructions`)

use std::fmt;

pub const COPY_LEN_U4: u8 = 0 << 4;
pub const COPY_LEN_U12: u8 = 1 << 4;
pub const COPY_LEN_U20: u8 = 2 << 4;
pub const COPY_LEN_U32: u8 = 3 << 4;
pub const WRITE_LEN_U4: u8 = 4 << 4;
pub const WRITE_LEN_U12: u8 = 5 << 4;
pub const WRITE_LEN_U20: u8 = 6 << 4;
pub const WRITE_LEN_U32: u8 = 7 << 4;
pub const ADDR_SHIFT_S8: u8 = 8 << 4;
pub const ADDR_SHIFT_S16: u8 = 9 << 4;
pub const ADDR_SET_U32: u8 = 10 << 4;
pub const PATCH: u8 = 11 << 4;
pub const PATCH_DELTA: u8 = 12 << 4;
const OPCODE_MASK: u8 = 0xF0;
const DATA_MASK: u8 = 0x0F;

pub fn opcode_name(op: u8) -> &'static str {
    match op {
        COPY_LEN_U4 => "COPY_LEN_U4",
        COPY_LEN_U12 => "COPY_LEN_U12",
        COPY_LEN_U20 => "COPY_LEN_U20",
        COPY_LEN_U32 => "COPY_LEN_U32",
        WRITE_LEN_U4 => "WRITE_LEN_U4",
        WRITE_LEN_U12 => "WRITE_LEN_U12",
        WRITE_LEN_U20 => "WRITE_LEN_U20",
        WRITE_LEN_U32 => "WRITE_LEN_U32",
        ADDR_SHIFT_S8 => "ADDR_SHIFT_S8",
        ADDR_SHIFT_S16 => "ADDR_SHIFT_S16",
        ADDR_SET_U32 => "ADDR_SET_U32",
        PATCH => "PATCH",
        PATCH_DELTA => "PATCH_DELTA",
        _ => "UNKNOWN",
    }
}

/// Size class of a COPY or WRITE length
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LenSize {
    U4,
    U12,
    U20,
    U32,
}

impl LenSize {
    pub fn for_length(length: usize) -> LenSize {
        if length < 16 {
            LenSize::U4
        } else if length < 4096 {
            LenSize::U12
        } else if length < 1_048_576 {
            LenSize::U20
        } else {
            LenSize::U32
        }
    }

    fn header_len(self) -> usize {
        match self {
            LenSize::U4 => 1,
            LenSize::U12 => 2,
            LenSize::U20 => 3,
            LenSize::U32 => 5,
        }
    }

    fn opcode_offset(self) -> u8 {
        match self {
            LenSize::U4 => 0,
            LenSize::U12 => 1 << 4,
            LenSize::U20 => 2 << 4,
            LenSize::U32 => 3 << 4,
        }
    }

    /// Append the opcode and length, `base` is the U4 opcode of the instruction family
    fn encode(self, base: u8, length: usize, out: &mut Vec<u8>) {
        let op = base + self.opcode_offset();
        match self {
            LenSize::U4 => out.push(op | length as u8),
            LenSize::U12 => out.extend_from_slice(&[op | (length >> 8) as u8, (length & 0xFF) as u8]),
            LenSize::U20 => {
                out.push(op | (length >> 16) as u8);
                out.extend_from_slice(&((length & 0xFFFF) as u16).to_le_bytes());
            }
            LenSize::U32 => {
                out.push(op);
                out.extend_from_slice(&(length as u32).to_le_bytes());
            }
        }
    }
}

/// Size class of an address change
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AddrSize {
    S8,
    S16,
    U32,
}

impl AddrSize {
    pub fn for_shift(shift: i64) -> AddrSize {
        if (-128..=127).contains(&shift) {
            AddrSize::S8
        } else if (-32768..=32767).contains(&shift) {
            AddrSize::S16
        } else {
            AddrSize::U32
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum PatchOp {
    Copy(usize),
    Write(Vec<u8>),
}

/// PATCH_DELTA element: (COPY length, addition, explicit delta)
pub type Element = (usize, u8, u16);

pub const DELTA_EXPLICIT: u8 = 14;
pub const DELTA_NONE: u8 = 15;
pub const DELTA_MAX_COPY: usize = 15 + 255;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Instr {
    Copy { length: usize, size: LenSize },
    Write { data: Vec<u8>, size: LenSize },
    SetAddr { old: i64, new: i64, size: AddrSize },
    Patch(Vec<PatchOp>),
    PatchDelta(Vec<Element>),
}

impl Instr {
    pub fn copy(length: usize) -> Instr {
        Instr::Copy {
            length,
            size: LenSize::for_length(length),
        }
    }

    pub fn write(data: &[u8]) -> Instr {
        Instr::Write {
            data: data.to_vec(),
            size: LenSize::for_length(data.len()),
        }
    }

    pub fn set_addr(old: i64, new: i64) -> Instr {
        Instr::SetAddr {
            old,
            new,
            size: AddrSize::for_shift(new - old),
        }
    }

    pub fn opcode(&self) -> u8 {
        match self {
            Instr::Copy { size, .. } => COPY_LEN_U4 + size.opcode_offset(),
            Instr::Write { size, .. } => WRITE_LEN_U4 + size.opcode_offset(),
            Instr::SetAddr { size, .. } => match size {
                AddrSize::S8 => ADDR_SHIFT_S8,
                AddrSize::S16 => ADDR_SHIFT_S16,
                AddrSize::U32 => ADDR_SET_U32,
            },
            Instr::Patch(_) => PATCH,
            Instr::PatchDelta(_) => PATCH_DELTA,
        }
    }

    pub fn encode(&self, out: &mut Vec<u8>) {
        match self {
            Instr::Copy { length, size } => size.encode(COPY_LEN_U4, *length, out),
            Instr::Write { data, size } => {
                size.encode(WRITE_LEN_U4, data.len(), out);
                out.extend_from_slice(data);
            }
            Instr::SetAddr { old, new, size } => match size {
                AddrSize::S8 => out.extend_from_slice(&[ADDR_SHIFT_S8, (new - old) as i8 as u8]),
                AddrSize::S16 => {
                    out.push(ADDR_SHIFT_S16);
                    out.extend_from_slice(&((new - old) as i16).to_le_bytes());
                }
                AddrSize::U32 => {
                    out.push(ADDR_SET_U32);
                    out.extend_from_slice(&(*new as u32).to_le_bytes());
                }
            },
            Instr::Patch(ops) => {
                out.push(PATCH);
                let mut iter = ops.iter();
                loop {
                    let copy = match iter.next() {
                        Some(PatchOp::Copy(c)) => *c,
                        Some(PatchOp::Write(_)) => panic!("PATCH must alternate COPY and WRITE"),
                        None => break,
                    };
                    assert!(copy < 128 && copy != 0);
                    match iter.next() {
                        Some(PatchOp::Write(data)) => {
                            assert!(!data.is_empty() && data.len() < 256);
                            if data.len() == 1 {
                                out.push(0x80 | copy as u8);
                            } else {
                                out.push(copy as u8);
                                out.push(data.len() as u8);
                            }
                            out.extend_from_slice(data);
                        }
                        Some(PatchOp::Copy(_)) => panic!("PATCH must alternate COPY and WRITE"),
                        None => {
                            out.push(copy as u8);
                            break;
                        }
                    }
                }
                out.push(0);
            }
            Instr::PatchDelta(elements) => {
                out.push(PATCH_DELTA);
                for &(copy, addition, delta) in elements {
                    assert!(copy <= DELTA_MAX_COPY);
                    assert!(copy != 0 || addition != DELTA_NONE);
                    out.push(((copy.min(15) as u8) << 4) | addition);
                    if copy >= 15 {
                        out.push((copy - 15) as u8);
                    }
                    if addition == DELTA_EXPLICIT {
                        out.extend_from_slice(&delta.to_le_bytes());
                    }
                }
                out.push(DELTA_NONE);
            }
        }
    }

    pub fn encoded_len(&self) -> usize {
        match self {
            Instr::Copy { size, .. } => size.header_len(),
            Instr::Write { data, size } => size.header_len() + data.len(),
            Instr::SetAddr { size, .. } => match size {
                AddrSize::S8 => 2,
                AddrSize::S16 => 3,
                AddrSize::U32 => 5,
            },
            Instr::Patch(ops) => {
                2 + ops
                    .iter()
                    .map(|op| match op {
                        PatchOp::Copy(_) => 1,
                        PatchOp::Write(d) => d.len() + usize::from(d.len() > 1),
                    })
                    .sum::<usize>()
            }
            Instr::PatchDelta(elements) => {
                2 + elements
                    .iter()
                    .map(|&(c, a, _)| 1 + usize::from(c >= 15) + if a == DELTA_EXPLICIT { 2 } else { 0 })
                    .sum::<usize>()
            }
        }
    }

    /// Decode the instruction at `offset`, returning it, its encoded length and the
    /// updated original file offset.
    pub fn decode(b: &[u8], offset: usize, original_offset: i64) -> Result<(Instr, usize, i64), String> {
        let get =
            |i: usize| -> Result<u8, String> { b.get(i).copied().ok_or_else(|| "Truncated patch data".to_string()) };
        let slice = |start: usize, len: usize| -> Result<&[u8], String> {
            b.get(start..start + len)
                .ok_or_else(|| "Truncated patch data".to_string())
        };
        let byte = get(offset)?;
        let op = byte & OPCODE_MASK;
        let data = (byte & DATA_MASK) as usize;
        let decode_len = |size: LenSize| -> Result<(usize, usize), String> {
            Ok(match size {
                LenSize::U4 => (data, 1),
                LenSize::U12 => ((data << 8) | get(offset + 1)? as usize, 2),
                LenSize::U20 => {
                    let low = u16::from_le_bytes(slice(offset + 1, 2)?.try_into().unwrap()) as usize;
                    ((data << 16) | low, 3)
                }
                LenSize::U32 => (
                    u32::from_le_bytes(slice(offset + 1, 4)?.try_into().unwrap()) as usize,
                    5,
                ),
            })
        };
        let len_size = |base: u8| match op - base {
            0x00 => LenSize::U4,
            0x10 => LenSize::U12,
            0x20 => LenSize::U20,
            _ => LenSize::U32,
        };
        match op {
            COPY_LEN_U4..=COPY_LEN_U32 => {
                let size = len_size(COPY_LEN_U4);
                let (length, hdr) = decode_len(size)?;
                Ok((Instr::Copy { length, size }, hdr, original_offset + length as i64))
            }
            WRITE_LEN_U4..=WRITE_LEN_U32 => {
                let size = len_size(WRITE_LEN_U4);
                let (length, hdr) = decode_len(size)?;
                let data = slice(offset + hdr, length)?.to_vec();
                Ok((
                    Instr::Write { data, size },
                    hdr + length,
                    original_offset + length as i64,
                ))
            }
            ADDR_SHIFT_S8 => {
                let new = original_offset + get(offset + 1)? as i8 as i64;
                Ok((
                    Instr::SetAddr {
                        old: original_offset,
                        new,
                        size: AddrSize::S8,
                    },
                    2,
                    new,
                ))
            }
            ADDR_SHIFT_S16 => {
                let shift = i16::from_le_bytes(slice(offset + 1, 2)?.try_into().unwrap()) as i64;
                let new = original_offset + shift;
                Ok((
                    Instr::SetAddr {
                        old: original_offset,
                        new,
                        size: AddrSize::S16,
                    },
                    3,
                    new,
                ))
            }
            ADDR_SET_U32 => {
                let new = u32::from_le_bytes(slice(offset + 1, 4)?.try_into().unwrap()) as i64;
                Ok((
                    Instr::SetAddr {
                        old: original_offset,
                        new,
                        size: AddrSize::U32,
                    },
                    5,
                    new,
                ))
            }
            PATCH => {
                let mut ops = Vec::new();
                let mut length = 1;
                let mut orig = original_offset;
                loop {
                    let copy = get(offset + length)?;
                    length += 1;
                    if copy == 0 {
                        break;
                    }
                    let actual = (copy & 0x7F) as usize;
                    orig += actual as i64;
                    ops.push(PatchOp::Copy(actual));
                    let write_len = if copy & 0x80 != 0 {
                        1
                    } else {
                        let w = get(offset + length)? as usize;
                        length += 1;
                        w
                    };
                    if write_len == 0 {
                        break;
                    }
                    orig += write_len as i64;
                    ops.push(PatchOp::Write(slice(offset + length, write_len)?.to_vec()));
                    length += write_len;
                }
                Ok((Instr::Patch(ops), length, orig))
            }
            PATCH_DELTA => {
                let mut elements = Vec::new();
                let mut length = 1;
                let mut orig = original_offset;
                loop {
                    let header = get(offset + length)?;
                    length += 1;
                    if header == DELTA_NONE {
                        break;
                    }
                    let mut copy = (header >> 4) as usize;
                    let addition = header & 0x0F;
                    if copy == 15 {
                        copy += get(offset + length)? as usize;
                        length += 1;
                    }
                    let mut delta = 0;
                    if addition == DELTA_EXPLICIT {
                        delta = u16::from_le_bytes(slice(offset + length, 2)?.try_into().unwrap());
                        length += 2;
                    }
                    orig += copy as i64 + if addition != DELTA_NONE { 2 } else { 0 };
                    elements.push((copy, addition, delta));
                }
                Ok((Instr::PatchDelta(elements), length, orig))
            }
            _ => Err(format!("Unknown opcode 0x{byte:02x}")),
        }
    }
}

impl fmt::Display for Instr {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        fn hex(data: &[u8]) -> String {
            let shown: String = data.iter().take(64).map(|b| format!("{b:02x}")).collect();
            if data.len() > 64 { format!("{shown}...") } else { shown }
        }
        match self {
            Instr::Copy { length, .. } => write!(f, " COPY: {length:6} bytes"),
            Instr::Write { data, .. } => write!(f, "WRITE: {:6} bytes ({})", data.len(), hex(data)),
            Instr::SetAddr { old, new, .. } => {
                let shift = new - old;
                if (-32768..=32767).contains(&shift) {
                    write!(f, " ADDR: shifting {shift} (from {old:08x} to {new:08x})")
                } else {
                    write!(f, " ADDR: now {new:08x} (shift of {shift})")
                }
            }
            Instr::Patch(ops) => {
                write!(f, "PATCH:")?;
                for op in ops {
                    match op {
                        PatchOp::Copy(c) => write!(f, "\n\t COPY: {c:6} bytes")?,
                        PatchOp::Write(d) => write!(f, "\n\tWRITE: {:6} bytes ({})", d.len(), hex(d))?,
                    }
                }
                Ok(())
            }
            Instr::PatchDelta(elements) => {
                write!(f, "PATCH_DELTA:")?;
                for &(c, a, d) in elements {
                    match a {
                        DELTA_NONE => write!(f, "\n\t COPY: {c:6} bytes")?,
                        DELTA_EXPLICIT => write!(f, "\n\t COPY: {c:6} bytes, ADD: {d:04x}")?,
                        _ => write!(f, "\n\t COPY: {c:6} bytes, ADD: history[{a}]")?,
                    }
                }
                Ok(())
            }
        }
    }
}

/// Most recently used 16 bit deltas, shared by all PATCH_DELTA instructions in a patch
#[derive(Clone)]
pub struct DeltaHistory {
    pub deltas: Vec<u16>,
}

pub const DELTA_HISTORY_SIZE: usize = 14;
const DELTA_HISTORY_INITIAL: [u16; DELTA_HISTORY_SIZE] = [
    1, 0xFFFF, 2, 0xFFFE, 3, 0xFFFD, 4, 0xFFFC, 5, 0xFFFB, 6, 0xFFFA, 7, 0xFFF9,
];

impl Default for DeltaHistory {
    fn default() -> Self {
        DeltaHistory {
            deltas: DELTA_HISTORY_INITIAL.to_vec(),
        }
    }
}

impl DeltaHistory {
    pub fn find(&self, delta: u16) -> Option<usize> {
        self.deltas.iter().position(|&d| d == delta)
    }

    /// Update the history after a delta has been used, returning the delta
    pub fn use_delta(&mut self, index: Option<usize>, delta: u16) -> u16 {
        let delta = match index {
            None => {
                self.deltas.pop();
                delta
            }
            Some(i) => self.deltas.remove(i),
        };
        self.deltas.insert(0, delta);
        delta
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn round_trip(instr: Instr) {
        let mut data = Vec::new();
        instr.encode(&mut data);
        assert_eq!(data.len(), instr.encoded_len());
        // Relative address shifts decode against the current original offset
        let original_offset = if let Instr::SetAddr { old, .. } = instr { old } else { 0 };
        let (decoded, len, _) = Instr::decode(&data, 0, original_offset).unwrap();
        assert_eq!(len, data.len());
        assert_eq!(decoded, instr);
    }

    #[test]
    fn instructions_round_trip() {
        for length in [1, 15, 16, 4095, 4096, 1_048_575, 1_048_576] {
            round_trip(Instr::copy(length));
            round_trip(Instr::write(&vec![0xA5; length.min(70_000)]));
        }
        round_trip(Instr::set_addr(1000, 900));
        round_trip(Instr::set_addr(1000, 30_000));
        round_trip(Instr::set_addr(1000, 2_000_000));
        round_trip(Instr::Patch(vec![
            PatchOp::Copy(15),
            PatchOp::Write(vec![1]),
            PatchOp::Copy(127),
            PatchOp::Write(vec![1, 2, 3]),
            PatchOp::Copy(3),
        ]));
        round_trip(Instr::PatchDelta(vec![
            (0, DELTA_EXPLICIT, 0x1234),
            (5, 0, 0),
            (14, 13, 0),
            (15, DELTA_NONE, 0),
            (DELTA_MAX_COPY, DELTA_EXPLICIT, 0xFFFF),
        ]));
    }
}
