//! Patch file generation, validation and application (mirrors `infuse_iot.cpatch.cpatch`)

use std::collections::HashMap;
use std::fmt;

use crate::crc::crc32;
use crate::instructions::{
    AddrSize, DELTA_EXPLICIT, DELTA_HISTORY_SIZE, DELTA_MAX_COPY, DELTA_NONE, DeltaHistory, Instr, LenSize, PatchOp,
    opcode_name,
};
use crate::{shortest_path, shortest_path_delta, stream, stream_thumb2};

const MAGIC: u32 = 0xBA85_4092;
const VERSION_MAJOR: u8 = 1;
const VERSION_MINOR: u8 = 0;
/// Patches containing PATCH_DELTA instructions
const VERSION_MAJOR_DELTA: u8 = 2;
/// Patches containing an element stream for Thumb-2 images, with a relocation preamble
const VERSION_MAJOR_STREAM_THUMB2: u8 = 3;
pub const HEADER_LEN: usize = 34;

#[derive(Debug)]
pub struct ValidationError(pub String);

impl fmt::Display for ValidationError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for ValidationError {}

fn invalid<T>(msg: String) -> Result<T, ValidationError> {
    Err(ValidationError(msg))
}

/// Algorithm used to generate the patch instructions
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Encoder {
    /// Minimum encoded size over candidate matching runs
    ShortestPath,
    /// As ShortestPath, additionally using PATCH_DELTA (requires patch format version 2)
    ShortestPathDelta,
    /// Element stream with relocation of Thumb-2 branches and pointers (requires patch format version 3)
    StreamThumb2,
}

impl Encoder {
    pub fn from_name(name: &str) -> Option<Encoder> {
        match name {
            "shortest-path" => Some(Encoder::ShortestPath),
            "shortest-path-delta" => Some(Encoder::ShortestPathDelta),
            "stream-thumb2" => Some(Encoder::StreamThumb2),
            _ => None,
        }
    }

    /// Patch (major, minor) version, identifying the encoder that generated the patch
    fn version(self) -> (u8, u8) {
        match self {
            Encoder::ShortestPath => (VERSION_MAJOR, 1),
            Encoder::ShortestPathDelta => (VERSION_MAJOR_DELTA, 0),
            Encoder::StreamThumb2 => (VERSION_MAJOR_STREAM_THUMB2, 0),
        }
    }

    fn encode(self, original: &[u8], new: &[u8]) -> Vec<Instr> {
        match self {
            Encoder::ShortestPath => shortest_path::encode(original, new),
            Encoder::ShortestPathDelta => shortest_path_delta::encode(original, new),
            Encoder::StreamThumb2 => unreachable!("element streams are not instructions"),
        }
    }
}

/// (length, CRC) of the original and constructed files
#[derive(Clone, Copy)]
struct Metadata {
    original: (u32, u32),
    new: (u32, u32),
}

impl Metadata {
    fn new(original: &[u8], new: &[u8]) -> Self {
        Metadata {
            original: (original.len() as u32, crc32(original)),
            new: (new.len() as u32, crc32(new)),
        }
    }
}

pub struct Header {
    pub version: (u8, u8),
    pub original: (u32, u32),
    pub constructed: (u32, u32),
    pub patch: (u32, u32),
}

fn encode_header(meta: Metadata, patch_data: &[u8], version: (u8, u8)) -> Vec<u8> {
    let mut hdr = Vec::with_capacity(HEADER_LEN);
    hdr.extend_from_slice(&MAGIC.to_le_bytes());
    hdr.extend_from_slice(&[version.0, version.1]);
    for (len, crc) in [meta.original, meta.new, (patch_data.len() as u32, crc32(patch_data))] {
        hdr.extend_from_slice(&len.to_le_bytes());
        hdr.extend_from_slice(&crc.to_le_bytes());
    }
    let crc = crc32(&hdr);
    hdr.extend_from_slice(&crc.to_le_bytes());
    hdr
}

fn encode_instructions(instructions: &[Instr]) -> Vec<u8> {
    let mut data = Vec::new();
    for instr in instructions {
        instr.encode(&mut data);
    }
    data
}

fn u32_at(b: &[u8], offset: usize) -> u32 {
    u32::from_le_bytes(b[offset..offset + 4].try_into().unwrap())
}

/// Validate a patch file header and data, returning the header and the patch data
fn load_header(patch: &[u8]) -> Result<(Header, &[u8]), ValidationError> {
    if patch.len() < HEADER_LEN {
        return invalid("Patch file too short".into());
    }
    let header = Header {
        version: (patch[4], patch[5]),
        original: (u32_at(patch, 6), u32_at(patch, 10)),
        constructed: (u32_at(patch, 14), u32_at(patch, 18)),
        patch: (u32_at(patch, 22), u32_at(patch, 26)),
    };
    let data = &patch[HEADER_LEN..];
    if crc32(&patch[..HEADER_LEN - 4]) != u32_at(patch, 30) {
        return invalid("Patch header validation failed".into());
    }
    if ![VERSION_MAJOR, VERSION_MAJOR_DELTA, VERSION_MAJOR_STREAM_THUMB2].contains(&header.version.0) {
        return invalid(format!("Unsupported patch version ({})", header.version.0));
    }
    if data.len() != header.patch.0 as usize {
        return invalid(format!(
            "Patch data length does not match header information ({} != {})",
            data.len(),
            header.patch.0
        ));
    }
    let crc_patch = crc32(data);
    if crc_patch != header.patch.1 {
        return invalid(format!(
            "Patch data CRC does not match patch information ({crc_patch:08x} != {:08x})",
            header.patch.1
        ));
    }
    Ok((header, data))
}

/// Validate a patch file and decode its instructions
pub fn load(patch: &[u8]) -> Result<(Header, Vec<Instr>), ValidationError> {
    let (header, data) = load_header(patch)?;
    if header.version.0 == VERSION_MAJOR_STREAM_THUMB2 {
        return invalid("Version 3 patches contain an element stream, not instructions".into());
    }
    let mut instructions = Vec::new();
    let mut offset = 0;
    let mut original_offset = 0;
    while offset < data.len() {
        let (instr, length, orig) = Instr::decode(data, offset, original_offset).map_err(ValidationError)?;
        offset += length;
        original_offset = orig;
        instructions.push(instr);
    }
    Ok((header, instructions))
}

pub struct Generated {
    pub patch: Vec<u8>,
    /// Number of instructions (elements for version 3)
    pub count: usize,
    /// Usage count of each instruction type
    pub counts: Vec<(&'static str, usize)>,
}

/// Generate a patch file that constructs `new` from `original`
pub fn generate(original: &[u8], new: &[u8], encoder: Encoder) -> Result<Generated, ValidationError> {
    let (data, count, counts) = if encoder == Encoder::StreamThumb2 {
        let (preamble, elements) = stream_thumb2::encode(original, new);
        (
            stream::encode(&preamble, &elements),
            elements.len(),
            stream::op_counts(&elements),
        )
    } else {
        let instructions = encoder.encode(original, new);
        (
            encode_instructions(&instructions),
            instructions.len(),
            opcode_counts(&instructions),
        )
    };
    let mut patch = encode_header(Metadata::new(original, new), &data, encoder.version());
    patch.extend_from_slice(&data);

    // Validate that file can be reconstructed
    if apply(original, &patch)? != new {
        return invalid("Generated patch does not reconstruct the new file".into());
    }
    Ok(Generated { patch, count, counts })
}

/// Instructions that run every PATCH_DELTA element type, reconstructing `original[offset..]`
fn validation_delta(original: &[u8], offset: usize) -> Result<Vec<Instr>, String> {
    let val16 = |o: usize| original[o] as u16 | (original[o + 1] as u16) << 8;
    let missing = || "Input file does not contain the values required for PATCH_DELTA validation".to_string();
    let mut instructions = Vec::new();
    let mut history = DeltaHistory::default();

    // Every COPY length encoding on the current offset, where the required delta is 0
    let mut elements = vec![(0, DELTA_EXPLICIT, 0)];
    history.use_delta(None, 0);
    for copy in (1..15).chain([15, 100, DELTA_MAX_COPY]) {
        elements.push((copy, 0, 0));
        history.use_delta(Some(0), 0);
    }
    elements.push((5, DELTA_NONE, 0));
    elements.push((DELTA_MAX_COPY, DELTA_NONE, 0));
    let mut out = (offset
        + elements
            .iter()
            .map(|&(c, a, _)| c + if a != DELTA_NONE { 2 } else { 0 })
            .sum::<usize>()) as i64;
    let mut old = out;
    instructions.push(Instr::PatchDelta(elements));

    // Additions of non-zero deltas read from a different offset in the original, such that
    // the output still matches the original.
    let mut positions: HashMap<u16, Vec<usize>> = HashMap::new();
    for o in 0..original.len().saturating_sub(1) {
        positions.entry(val16(o)).or_default().push(o);
    }

    // Output the original at `x` by adding a delta to the original at `y`
    let addition = |instructions: &mut Vec<Instr>,
                    history: &mut DeltaHistory,
                    out: &mut i64,
                    old: &mut i64,
                    x: i64,
                    y: i64,
                    index: u8,
                    delta: u16| {
        if x > *out {
            if *old != *out {
                instructions.push(Instr::set_addr(*old, *out));
            }
            instructions.push(Instr::copy((x - *out) as usize));
            *old = x;
        }
        if *old != y {
            instructions.push(Instr::set_addr(*old, y));
        }
        instructions.push(Instr::PatchDelta(vec![(0, index, delta)]));
        history.use_delta(
            if index == DELTA_EXPLICIT {
                None
            } else {
                Some(index as usize)
            },
            delta,
        );
        *out = x + 2;
        *old = y + 2;
    };

    let history_addition = |instructions: &mut Vec<Instr>,
                            history: &mut DeltaHistory,
                            out: &mut i64,
                            old: &mut i64,
                            accept: &dyn Fn(usize, u16, usize) -> bool|
     -> Result<(), String> {
        for x in *out as usize..original.len().saturating_sub(1) {
            for (index, &delta) in history.deltas.clone().iter().enumerate() {
                if let Some(ys) = positions.get(&val16(x).wrapping_sub(delta)) {
                    for &y in ys {
                        if accept(index, delta, y) {
                            addition(instructions, history, out, old, x as i64, y as i64, index as u8, 0);
                            return Ok(());
                        }
                    }
                }
            }
        }
        Err(missing())
    };

    // Each history index, and at least one addition carrying out of the low byte
    for target in (1..DELTA_HISTORY_SIZE).rev() {
        history_addition(
            &mut instructions,
            &mut history,
            &mut out,
            &mut old,
            &|index, delta, _| index == target && delta != 0,
        )?;
    }
    history_addition(&mut instructions, &mut history, &mut out, &mut old, &|_, delta, y| {
        (val16(y) & 0xFF) + (delta & 0xFF) > 0xFF
    })?;

    // An explicit delta that is not in the history
    let mut found = false;
    for x in out as usize..original.len().saturating_sub(2) {
        let delta = val16(x).wrapping_sub(val16(x + 1));
        if history.find(delta).is_none() {
            addition(
                &mut instructions,
                &mut history,
                &mut out,
                &mut old,
                x as i64,
                x as i64 + 1,
                DELTA_EXPLICIT,
                delta,
            );
            found = true;
            break;
        }
    }
    if !found {
        return Err(missing());
    }

    // Remainder of the file
    if old != out {
        instructions.push(Instr::set_addr(old, out));
    }
    if (out as usize) < original.len() {
        instructions.push(Instr::copy(original.len() - out as usize));
    }
    Ok(instructions)
}

/// Generate a patch file that runs all instructions, for validating appliers
pub fn validation(
    original: &[u8],
    invalid_length: bool,
    invalid_crc: bool,
    delta: bool,
    stream_thumb2: bool,
) -> Result<Vec<u8>, String> {
    if original.len() <= 1024 {
        return Err("Input file must be larger than 1024 bytes".into());
    }
    if delta && stream_thumb2 {
        return Err("PATCH_DELTA instructions and element streams are exclusive".into());
    }
    let write = |range: std::ops::Range<usize>, size| Instr::Write {
        data: original[range].to_vec(),
        size,
    };
    let mut instructions = vec![
        write(0..8, LenSize::U4),
        write(8..16, LenSize::U12),
        Instr::SetAddr {
            old: 16,
            new: 8,
            size: AddrSize::S8,
        },
        write(16..128, LenSize::U20),
        Instr::SetAddr {
            old: 120,
            new: 200,
            size: AddrSize::S16,
        },
        write(128..256, LenSize::U32),
        Instr::SetAddr {
            old: 328,
            new: 256,
            size: AddrSize::U32,
        },
        Instr::Copy {
            length: 8,
            size: LenSize::U4,
        },
        Instr::Copy {
            length: 8,
            size: LenSize::U12,
        },
        Instr::Copy {
            length: 128 - 16,
            size: LenSize::U20,
        },
        Instr::Copy {
            length: 128,
            size: LenSize::U32,
        },
        Instr::Patch(vec![
            PatchOp::Copy(15),
            PatchOp::Write(original[512 + 15..512 + 16].to_vec()),
            PatchOp::Copy(14),
            PatchOp::Write(original[512 + 30..512 + 32].to_vec()),
        ]),
    ];
    let (data, version) = if stream_thumb2 {
        // Element streams require version 3 appliers, and replace all instructions
        let (preamble, elements) = stream::validation(original)?;
        (stream::encode(&preamble, &elements), (VERSION_MAJOR_STREAM_THUMB2, 0))
    } else if delta {
        // PATCH_DELTA instructions require version 2 appliers
        instructions.extend(validation_delta(original, 544)?);
        (encode_instructions(&instructions), (VERSION_MAJOR_DELTA, 0))
    } else {
        instructions.push(Instr::copy(original.len() - 544));
        (encode_instructions(&instructions), (VERSION_MAJOR, VERSION_MINOR))
    };

    let mut meta = Metadata::new(original, original);
    if invalid_length {
        meta.new.0 = meta.new.0.wrapping_sub(1);
    }
    if invalid_crc {
        meta.new.1 = meta.new.1.wrapping_sub(1);
    }
    let mut patch = encode_header(meta, &data, version);
    patch.extend_from_slice(&data);

    // Validate that file can be reconstructed
    if !invalid_length && !invalid_crc && apply(original, &patch).map_err(|e| e.0)? != original {
        return Err("Validation patch does not reconstruct the input file".into());
    }
    Ok(patch)
}

/// Apply a patch file to the original file
pub fn apply(original: &[u8], patch: &[u8]) -> Result<Vec<u8>, ValidationError> {
    let (header, data) = load_header(patch)?;
    let (len_expected, crc_expected) = header.original;
    if original.len() != len_expected as usize {
        return invalid(format!(
            "Original file length does not match patch information ({} != {len_expected})",
            original.len()
        ));
    }
    let crc_orig = crc32(original);
    if crc_orig != crc_expected {
        return invalid(format!(
            "Original file CRC does not match patch information ({crc_orig:08x} != {crc_expected:08x})"
        ));
    }

    let mut patched = Vec::with_capacity(header.constructed.0 as usize);
    if header.version.0 == VERSION_MAJOR_STREAM_THUMB2 {
        let (preamble, elements) = stream::decode(data).map_err(ValidationError)?;
        stream::apply(original, &preamble, &elements, &mut patched).map_err(ValidationError)?;
        return validate_output(&header, patched);
    }
    let (header, instructions) = load(patch)?;
    let mut offset = 0i64;
    let mut history = DeltaHistory::default();
    let copy = |patched: &mut Vec<u8>, offset: &mut i64, length: usize| -> Result<(), ValidationError> {
        let start = usize::try_from(*offset).map_err(|_| ValidationError("COPY before original file".into()))?;
        let data = original
            .get(start..start + length)
            .ok_or_else(|| ValidationError("COPY beyond original file".into()))?;
        patched.extend_from_slice(data);
        *offset += length as i64;
        Ok(())
    };
    for instr in &instructions {
        match instr {
            Instr::Copy { length, .. } => copy(&mut patched, &mut offset, *length)?,
            Instr::Write { data, .. } => {
                patched.extend_from_slice(data);
                offset += data.len() as i64;
            }
            Instr::SetAddr { new, .. } => offset = *new,
            Instr::Patch(ops) => {
                for op in ops {
                    match op {
                        PatchOp::Copy(c) => copy(&mut patched, &mut offset, *c)?,
                        PatchOp::Write(data) => {
                            patched.extend_from_slice(data);
                            offset += data.len() as i64;
                        }
                    }
                }
            }
            Instr::PatchDelta(elements) => {
                for &(c, addition, delta) in elements {
                    copy(&mut patched, &mut offset, c)?;
                    if addition == DELTA_NONE {
                        continue;
                    }
                    let index = if addition == DELTA_EXPLICIT {
                        None
                    } else {
                        Some(addition as usize)
                    };
                    let delta = history.use_delta(index, delta);
                    let mut value = Vec::with_capacity(2);
                    copy(&mut value, &mut offset, 2)?;
                    let value = u16::from_le_bytes([value[0], value[1]]).wrapping_add(delta);
                    patched.extend_from_slice(&value.to_le_bytes());
                }
            }
        }
    }

    validate_output(&header, patched)
}

/// Validate generated file matches what was expected
fn validate_output(header: &Header, patched: Vec<u8>) -> Result<Vec<u8>, ValidationError> {
    let (len_expected, crc_expected) = header.constructed;
    if patched.len() != len_expected as usize {
        return invalid(format!(
            "Original file length does not match patch information ({} != {len_expected})",
            patched.len()
        ));
    }
    let crc_patched = crc32(&patched);
    if crc_patched != crc_expected {
        return invalid(format!(
            "Original file CRC does not match patch information ({crc_patched:08x} != {crc_expected:08x})"
        ));
    }
    Ok(patched)
}

/// Opcode usage counts, sorted by opcode
pub fn opcode_counts(instructions: &[Instr]) -> Vec<(&'static str, usize)> {
    let mut counts = std::collections::BTreeMap::new();
    for instr in instructions {
        *counts.entry(instr.opcode()).or_insert(0) += 1;
    }
    counts.into_iter().map(|(op, count)| (opcode_name(op), count)).collect()
}

/// Print a summary of a version 3 patch file and its elements
fn dump_stream(patch: &[u8], header: &Header, data: &[u8]) -> Result<(), ValidationError> {
    let (preamble, elements) = stream::decode(data).map_err(ValidationError)?;
    let total_write: usize = elements
        .iter()
        .map(|e| match &e.op {
            stream::Op::Literal(d) | stream::Op::LiteralShift(d, _) => d.len(),
            _ => 0,
        })
        .sum();
    println!("Original File: {:6} bytes", header.original.0);
    println!("     New File: {:6} bytes", header.constructed.0);
    println!("   Patch File: {} bytes ({:5} elements)", patch.len(), elements.len());
    println!("      Version: {}.{}", header.version.0, header.version.1);
    println!(
        "   Relocation: flags {:02x}, base {:08x}",
        preamble.flags, preamble.base
    );
    println!("Relocation Map: {} entries", preamble.map.len());
    for &(start, shift) in &preamble.map {
        println!("\t{start:08x}: {shift:+}");
    }
    for region in &preamble.regions {
        println!(
            "Pointer Region: {:08x}-{:08x}, {} entries",
            region.base,
            region.base as u64 + region.length as u64,
            region.map.len()
        );
        for &(start, shift) in &region.map {
            println!("\t{start:08x}: {shift:+}");
        }
    }
    println!();
    println!("Total WRITE data:");
    println!(
        "\t{total_write} bytes ({:.2}%)",
        100.0 * total_write as f64 / patch.len() as f64
    );
    println!();
    println!("Operation Count:");
    for (name, count) in stream::op_counts(&elements) {
        println!("{name:>16}: {count}");
    }
    println!();
    println!("Element List:");
    for element in &elements {
        println!("{element}");
    }
    Ok(())
}

/// Print a summary of a patch file and its instructions
pub fn dump(patch: &[u8]) -> Result<(), ValidationError> {
    let (header, data) = load_header(patch)?;
    if header.version.0 == VERSION_MAJOR_STREAM_THUMB2 {
        return dump_stream(patch, &header, data);
    }
    let (header, instructions) = load(patch)?;
    let total_write: usize = instructions
        .iter()
        .map(|instr| match instr {
            Instr::Write { data, .. } => data.len(),
            Instr::Patch(ops) => ops
                .iter()
                .map(|op| match op {
                    PatchOp::Write(d) => d.len(),
                    PatchOp::Copy(_) => 0,
                })
                .sum(),
            _ => 0,
        })
        .sum();

    println!("Original File: {:6} bytes", header.original.0);
    println!("     New File: {:6} bytes", header.constructed.0);
    println!(
        "   Patch File: {} bytes ({:5} instructions)",
        patch.len(),
        instructions.len()
    );
    println!("      Version: {}.{}", header.version.0, header.version.1);
    println!();
    println!("Total WRITE data:");
    println!(
        "\t{total_write} bytes ({:.2}%)",
        100.0 * total_write as f64 / patch.len() as f64
    );
    println!();
    println!("Instruction Count:");
    for (name, count) in opcode_counts(&instructions) {
        println!("{name:>16}: {count}");
    }
    println!();
    println!("Instruction List:");
    for instr in &instructions {
        println!("{instr}");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pseudo_random(len: usize, seed: u64) -> Vec<u8> {
        let mut state = seed;
        (0..len)
            .map(|_| {
                state = state
                    .wrapping_mul(6364136223846793005)
                    .wrapping_add(1442695040888963407);
                (state >> 33) as u8
            })
            .collect()
    }

    #[test]
    fn generated_patches_reconstruct() {
        let original = pseudo_random(20_000, 1);
        let mut moved = original[..7000].to_vec();
        moved.extend(pseudo_random(300, 2));
        moved.extend_from_slice(&original[7000..]);
        let mut relocated = original.clone();
        for offset in (0..relocated.len() - 2).step_by(32) {
            relocated[offset] = relocated[offset].wrapping_add(1);
        }
        let cases: Vec<(&[u8], &[u8])> = vec![
            (&original, &original),
            (&original, &moved),
            (&original, &relocated),
            (b"abc", b"abd"),
            (b"", b"hello"),
            (&original[..100], b""),
        ];
        for encoder in [Encoder::ShortestPath, Encoder::ShortestPathDelta, Encoder::StreamThumb2] {
            for (old, new) in &cases {
                let generated = generate(old, new, encoder).unwrap();
                assert_eq!(apply(old, &generated.patch).unwrap(), *new);
            }
        }
    }

    #[test]
    fn validation_patches() {
        let original = pseudo_random(16_384, 3);
        for delta in [false, true] {
            let patch = validation(&original, false, false, delta, false).unwrap();
            assert_eq!(apply(&original, &patch).unwrap(), original);
            assert_eq!(patch[4], if delta { 2 } else { 1 });
            assert!(apply(&original, &validation(&original, true, false, delta, false).unwrap()).is_err());
            assert!(apply(&original, &validation(&original, false, true, delta, false).unwrap()).is_err());
        }
    }

    #[test]
    fn rejects_wrong_original() {
        let original: Vec<u8> = (0..64).collect();
        let mut new = original.clone();
        new[16..21].copy_from_slice(b"HELLO");
        let patch = generate(&original, &new, Encoder::ShortestPath).unwrap().patch;
        let reversed: Vec<u8> = original.iter().rev().copied().collect();
        assert!(apply(&reversed, &patch).unwrap_err().0.contains("Original file CRC"));
    }
}
