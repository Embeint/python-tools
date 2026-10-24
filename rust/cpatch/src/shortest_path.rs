//! Shortest path encoder (same algorithm as `infuse_iot.cpatch.encoder_shortest_path`)

use std::cmp::Reverse;
use std::collections::{BinaryHeap, HashMap, HashSet};

use crate::instructions::{Instr, PatchOp};
use crate::matching::{Gap, Run, candidate_runs, gap_runs};

pub const INF: f64 = f64::INFINITY;

/// Encoded size of a COPY or WRITE header
pub fn len_hdr_size(length: i64) -> f64 {
    if length < 16 {
        1.0
    } else if length < 4096 {
        2.0
    } else if length < 1_048_576 {
        3.0
    } else {
        5.0
    }
}

/// Encoded size of the address instruction required for a shift
pub fn addr_size(shift: i64) -> f64 {
    if shift == 0 {
        0.0
    } else if (-128..=127).contains(&shift) {
        2.0
    } else if (-32768..=32767).contains(&shift) {
        3.0
    } else {
        5.0
    }
}

/// Encoded size of a COPY inside a PATCH, long copies are split by single byte WRITEs
pub fn patch_copy_size(length: i64) -> f64 {
    let chunks = (length + 128).div_euclid(128);
    if chunks <= 3 { (2 * chunks - 1) as f64 } else { INF }
}

/// Construct an instruction list from the new file, tracking file offsets
pub struct InstrBuilder<'a> {
    pub new: &'a [u8],
    pub instructions: Vec<Instr>,
    pub patch: Option<Vec<PatchOp>>,
    pub new_offset: i64,
    pub old_offset: i64,
}

impl<'a> InstrBuilder<'a> {
    pub fn new(new: &'a [u8]) -> Self {
        InstrBuilder {
            new,
            instructions: Vec::new(),
            patch: None,
            new_offset: 0,
            old_offset: 0,
        }
    }

    pub fn patch_start(&mut self) {
        assert!(self.patch.is_none());
        self.patch = Some(Vec::new());
    }

    pub fn patch_end(&mut self) {
        let ops = self.patch.take().expect("PATCH not open");
        self.instructions.push(Instr::Patch(ops));
    }

    pub fn set_addr(&mut self, addr: i64) {
        assert!(self.patch.is_none());
        self.instructions.push(Instr::set_addr(self.old_offset, addr));
        self.old_offset = addr;
    }

    pub fn write(&mut self, length: i64) {
        let data = &self.new[self.new_offset as usize..(self.new_offset + length) as usize];
        match &mut self.patch {
            None => self.instructions.push(Instr::write(data)),
            Some(ops) => {
                assert!(length < 256 && matches!(ops.last(), Some(PatchOp::Copy(_))));
                ops.push(PatchOp::Write(data.to_vec()));
            }
        }
        self.new_offset += length;
        self.old_offset += length;
    }

    pub fn copy(&mut self, mut length: i64) {
        if self.patch.is_none() {
            self.instructions.push(Instr::copy(length as usize));
            self.new_offset += length;
            self.old_offset += length;
            return;
        }
        loop {
            // Final chunk must not be empty
            let chunk = if length <= 127 {
                length
            } else if length == 128 {
                126
            } else {
                127
            };
            self.patch.as_mut().unwrap().push(PatchOp::Copy(chunk as usize));
            self.new_offset += chunk;
            self.old_offset += chunk;
            length -= chunk;
            if length == 0 {
                return;
            }
            // Separate chunks with a single byte WRITE (data matches the original file)
            self.write(1);
            length -= 1;
        }
    }
}

// How the bytes between two COPY operations are handled
const GAP_NONE: u8 = 0;
const GAP_END: u8 = 1;
const GAP_PATCH: u8 = 2;
const GAP_PATCH_END: u8 = 3;
const GAP_END_WRITE: u8 = 4;
const GAP_WRITE: u8 = 5;
// How a COPY operation is encoded
const COPY_PATCH: u8 = 0;
const COPY_END: u8 = 1;
const COPY: u8 = 2;
const COPY_NEW_PATCH: u8 = 3;
const COPY_NONE: u8 = 255;

/// Node structure shared by the shortest path searches
pub struct Nodes {
    pub ts: Vec<i64>,
    pub te: Vec<i64>,
    pub td: Vec<i64>,
    pub end_node: usize,
    pub by_start: Vec<usize>,
    pub starts: Vec<i64>,
    pub next_same: Vec<Vec<usize>>,
}

impl Nodes {
    pub fn new(new_len: i64, runs: &HashSet<Run>) -> Nodes {
        // Total order, so that the encoding does not depend on set iteration order
        let mut tokens: Vec<Run> = runs.iter().copied().collect();
        tokens.sort_unstable_by_key(|r| (r.1, r.0, r.2));
        // Node 0 is the start of the file, the final node is the end of the file
        let mut ts = vec![0];
        let mut te = vec![0];
        let mut td = vec![0];
        for r in &tokens {
            ts.push(r.0);
            te.push(r.1);
            td.push(r.2);
        }
        ts.push(new_len);
        te.push(new_len);
        td.push(0);
        let end_node = ts.len() - 1;
        let mut by_start: Vec<usize> = (1..end_node).collect();
        by_start.sort_by_key(|&i| ts[i]);
        let starts = by_start.iter().map(|&i| ts[i]).collect();
        // Next few runs on the same diagonal
        let mut diag_runs: HashMap<i64, Vec<usize>> = HashMap::new();
        for &i in &by_start {
            diag_runs.entry(td[i]).or_default().push(i);
        }
        let mut next_same = vec![Vec::new(); ts.len()];
        for lst in diag_runs.values() {
            for (idx, &i) in lst.iter().enumerate() {
                next_same[i] = lst[idx + 1..(idx + 4).min(lst.len())].to_vec();
            }
        }
        next_same[0] = diag_runs.get(&0).map_or(Vec::new(), |l| l[..3.min(l.len())].to_vec());
        Nodes {
            ts,
            te,
            td,
            end_node,
            by_start,
            starts,
            next_same,
        }
    }
}

/// Candidate next runs from offset `p`: runs covering `p`, the next runs on the same
/// diagonal, and runs starting soon after.
pub struct Candidates {
    /// Runs that have started, ordered by end offset
    covering: BinaryHeap<Reverse<(i64, usize)>>,
    next_start: usize,
}

impl Candidates {
    pub fn new() -> Self {
        Candidates {
            covering: BinaryHeap::new(),
            next_start: 0,
        }
    }

    pub fn get(&mut self, nodes: &Nodes, j: usize, p: i64, out: &mut Vec<usize>) {
        while self.next_start < nodes.by_start.len() && nodes.starts[self.next_start] <= p {
            let i = nodes.by_start[self.next_start];
            self.covering.push(Reverse((nodes.te[i], i)));
            self.next_start += 1;
        }
        while matches!(self.covering.peek(), Some(Reverse((end, _))) if *end <= p) {
            self.covering.pop();
        }
        out.clear();
        out.extend(self.covering.iter().map(|Reverse((_, i))| *i));
        out.extend_from_slice(&nodes.next_same[j]);
        let first = nodes.starts.partition_point(|&s| s <= p);
        for idx in first..(first + 8).min(nodes.starts.len()) {
            if nodes.starts[idx] > p + 256 && idx > first {
                break;
            }
            out.push(nodes.by_start[idx]);
        }
    }
}

/// Index after the last element `<= x`
pub fn bisect_right(a: &[i64], x: i64) -> usize {
    a.partition_point(|&v| v <= x)
}

/// Minimum size encoding of the new file from a set of candidate COPY runs
pub fn shortest_path_encode(new: &[u8], runs: &HashSet<Run>) -> (Vec<Instr>, Vec<Gap>) {
    let n = Nodes::new(new.len() as i64, runs);
    let (ts, te, td, end_node) = (&n.ts, &n.te, &n.td, n.end_node);

    // [outside PATCH, inside PATCH] costs and the transitions that achieved them
    let mut cost = vec![[INF, INF]; ts.len()];
    let mut back = vec![[(0usize, 0u8, 0u8, 0u8); 2]; ts.len()];
    cost[0][0] = 0.0;
    // Running minimum of (cost outside a PATCH - new offset), for long range transitions
    let mut relay_offset: Vec<i64> = Vec::new();
    let mut relay_node: Vec<usize> = Vec::new();
    let mut relay_val = INF;
    let mut candidates = Candidates::new();
    let mut cands = Vec::new();

    for j in 0..end_node {
        if j > 0 {
            // Enter from the best prior node, writing everything in between
            let x = ts[j];
            let i = relay_node[bisect_right(&relay_offset, x) - 1];
            let g = x - te[i];
            let (mut c, si, gap_mode) = if cost[i][0] <= cost[i][1] + 1.0 {
                (cost[i][0], 0u8, if g != 0 { GAP_WRITE } else { GAP_NONE })
            } else {
                (cost[i][1] + 1.0, 1u8, if g != 0 { GAP_END_WRITE } else { GAP_END })
            };
            c += (if g != 0 { len_hdr_size(g) + g as f64 } else { 0.0 }) + addr_size(td[j] - td[i]);
            let l = te[j] - x;
            if c + len_hdr_size(l) < cost[j][0] {
                cost[j][0] = c + len_hdr_size(l);
                back[j][0] = (i, si, gap_mode, COPY);
            }
            if c + 1.0 + patch_copy_size(l) < cost[j][1] {
                cost[j][1] = c + 1.0 + patch_copy_size(l);
                back[j][1] = (i, si, gap_mode, COPY_NEW_PATCH);
            }
        }

        let [c_out, c_in] = cost[j];
        let p = te[j];
        let dj = td[j];
        let v = c_out.min(c_in + 1.0) - p as f64;
        if v < relay_val {
            relay_val = v;
            relay_offset.push(p);
            relay_node.push(j);
        }

        candidates.get(&n, j, p, &mut cands);
        for &k in &cands {
            let s = ts[k].max(p);
            let g = s - p;
            let l = te[k] - s;
            if l <= 0 {
                continue;
            }
            let shift = td[k] - dj;
            // Cost to be ready for the COPY, either inside a PATCH after a WRITE, or outside
            let mut pre_patch = INF;
            let (mut pre_out, mut out_state, mut out_gap);
            if g == 0 {
                (pre_out, out_state, out_gap) = (c_out, 0u8, GAP_NONE);
                if c_in + 1.0 < pre_out {
                    (pre_out, out_state, out_gap) = (c_in + 1.0, 1, GAP_END);
                }
            } else {
                let write = len_hdr_size(g) + g as f64;
                (pre_out, out_state, out_gap) = (c_out + write, 0, GAP_WRITE);
                if g <= 255 {
                    pre_patch = c_in + g as f64 + if g > 1 { 1.0 } else { 0.0 };
                }
                if c_in + 1.0 + write < pre_out {
                    (pre_out, out_state, out_gap) = (c_in + 1.0 + write, 1, GAP_END_WRITE);
                }
            }
            if shift != 0 {
                if pre_patch + 1.0 < pre_out {
                    (pre_out, out_state, out_gap) = (pre_patch + 1.0, 1, GAP_PATCH_END);
                }
                pre_patch = INF;
                pre_out += addr_size(shift);
            }

            let hdr_l = len_hdr_size(l);
            let patch_l = patch_copy_size(l);
            let ck = &mut cost[k];
            let bk = &mut back[k];
            if pre_patch + patch_l < ck[1] {
                ck[1] = pre_patch + patch_l;
                bk[1] = (j, 1, GAP_PATCH, COPY_PATCH);
            }
            if pre_patch + 1.0 + hdr_l < ck[0] {
                ck[0] = pre_patch + 1.0 + hdr_l;
                bk[0] = (j, 1, GAP_PATCH, COPY_END);
            }
            if pre_out + hdr_l < ck[0] {
                ck[0] = pre_out + hdr_l;
                bk[0] = (j, out_state, out_gap, COPY);
            }
            if pre_out + 1.0 + patch_l < ck[1] {
                ck[1] = pre_out + 1.0 + patch_l;
                bk[1] = (j, out_state, out_gap, COPY_NEW_PATCH);
            }
        }

        // Write the remainder of the file
        let g = new.len() as i64 - p;
        let mut best = (
            c_out + if g != 0 { len_hdr_size(g) + g as f64 } else { 0.0 },
            0u8,
            if g != 0 { GAP_WRITE } else { GAP_NONE },
        );
        let mut consider = |opt: (f64, u8, u8)| {
            if opt.0 < best.0 {
                best = opt;
            }
        };
        if g == 0 {
            consider((c_in + 1.0, 1, GAP_END));
        } else {
            if g <= 255 {
                consider((c_in + g as f64 + if g > 1 { 1.0 } else { 0.0 } + 1.0, 1, GAP_PATCH_END));
            }
            consider((c_in + 1.0 + len_hdr_size(g) + g as f64, 1, GAP_END_WRITE));
        }
        if best.0 < cost[end_node][0] {
            cost[end_node][0] = best.0;
            back[end_node][0] = (j, best.1, best.2, COPY_NONE);
        }
    }

    // Recover the path
    let mut path = Vec::new();
    let (mut node, mut state) = (end_node, 0usize);
    while node != 0 {
        let (j, sj, gap_mode, copy_mode) = back[node][state];
        path.push((j, node, gap_mode, copy_mode));
        node = j;
        state = sj as usize;
    }

    // Construct the instructions
    let mut builder = InstrBuilder::new(new);
    let mut gaps = Vec::new();
    for &(j, k, gap_mode, copy_mode) in path.iter().rev() {
        let s = ts[k].max(te[j]);
        let g = s - te[j];
        if g != 0 {
            gaps.push((te[j], s, td[j], td[k]));
        }
        if gap_mode == GAP_END || gap_mode == GAP_END_WRITE {
            builder.patch_end();
        }
        if matches!(gap_mode, GAP_PATCH | GAP_PATCH_END | GAP_END_WRITE | GAP_WRITE) {
            builder.write(g);
        }
        if gap_mode == GAP_PATCH_END {
            builder.patch_end();
        }
        if k == end_node {
            break;
        }
        let target = s + td[k];
        if builder.old_offset != target {
            builder.set_addr(target);
        }
        if copy_mode == COPY_END {
            builder.patch_end();
        } else if copy_mode == COPY_NEW_PATCH {
            builder.patch_start();
        }
        builder.copy(te[k] - s);
    }
    assert!(builder.patch.is_none());
    assert_eq!(builder.new_offset, new.len() as i64);
    (builder.instructions, gaps)
}

/// Candidate runs, refined with the short matches inside the regions of a first encoding
pub fn refined_runs(old: &[u8], new: &[u8]) -> HashSet<Run> {
    let mut runs = candidate_runs(old, new);
    let (_, gaps) = shortest_path_encode(new, &runs);
    runs.extend(gap_runs(old, new, &gaps));
    runs
}

/// Encode the new file as instructions applied to the original file
pub fn encode(old: &[u8], new: &[u8]) -> Vec<Instr> {
    let runs = refined_runs(old, new);
    shortest_path_encode(new, &runs).0
}
