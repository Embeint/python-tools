//! Shortest path encoder extended with PATCH_DELTA instructions
//! (same algorithm as `infuse_iot.cpatch.encoder_shortest_path_delta`)

use std::collections::{HashMap, HashSet};

use crate::instructions::{
    DELTA_EXPLICIT, DELTA_HISTORY_SIZE, DELTA_MAX_COPY, DELTA_NONE, DeltaHistory, Element, Instr,
};
use crate::matching::{Gap, Run};
use crate::shortest_path::{
    Candidates, INF, InstrBuilder, Nodes, addr_size, bisect_right, len_hdr_size, patch_copy_size, refined_runs,
    shortest_path_encode,
};

/// Largest gap between COPY runs that is considered for filling with additions
const MAX_DELTA_GAP: i64 = 24;

// DP states after a COPY run
const OUT: usize = 0;
const IN_PATCH: usize = 1;
const IN_DELTA: usize = 2;

/// Construction actions
#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Debug)]
enum Action {
    EndPatch = 0,
    EndDelta = 1,
    StartPatch = 2,
    StartDelta = 3,
    Write = 4,
    Add = 5,
    Flush = 6,
}
use Action::*;

type Actions = &'static [Action];

/// Additional encoded size of a COPY pending in a PATCH_DELTA, beyond the next element header
fn delta_copy_size(length: i64) -> f64 {
    let max = DELTA_MAX_COPY as i64;
    if length < 15 {
        return 0.0;
    }
    if length <= max {
        return 1.0;
    }
    let extra = 0.max(-((-(length - max)).div_euclid(max)));
    let length = length - extra * max;
    (2 * extra + i64::from(length >= 15)) as f64
}

fn val16(data: &[u8], offset: usize) -> u16 {
    data[offset] as u16 | (data[offset + 1] as u16) << 8
}

/// Predicted encoded size of an addition, from the delta history of a previous encoding
struct DeltaPredictor {
    offsets: Vec<i64>,
    snapshots: Vec<[u16; DELTA_HISTORY_SIZE]>,
}

impl DeltaPredictor {
    fn new(additions: &[(i64, u16)]) -> Self {
        let mut history = DeltaHistory::default();
        let snapshot = |h: &DeltaHistory| -> [u16; DELTA_HISTORY_SIZE] { h.deltas.as_slice().try_into().unwrap() };
        let mut offsets = Vec::with_capacity(additions.len());
        let mut snapshots = vec![snapshot(&history)];
        for &(offset, delta) in additions {
            let index = history.find(delta);
            history.use_delta(index, delta);
            offsets.push(offset);
            snapshots.push(snapshot(&history));
        }
        DeltaPredictor { offsets, snapshots }
    }

    fn size(&self, offset: i64, delta: u16) -> f64 {
        let snapshot = &self.snapshots[self.offsets.partition_point(|&o| o < offset)];
        if snapshot.contains(&delta) { 1.0 } else { 3.0 }
    }
}

struct DeltaInstrBuilder<'a> {
    base: InstrBuilder<'a>,
    old: &'a [u8],
    history: DeltaHistory,
    delta: Option<Vec<Element>>,
    pending: usize,
    /// (new offset, delta) of each addition
    additions: Vec<(i64, u16)>,
}

impl<'a> DeltaInstrBuilder<'a> {
    fn new(old: &'a [u8], new: &'a [u8]) -> Self {
        DeltaInstrBuilder {
            base: InstrBuilder::new(new),
            old,
            history: DeltaHistory::default(),
            delta: None,
            pending: 0,
            additions: Vec::new(),
        }
    }

    fn element(&mut self, addition: u8, delta: u16) {
        let elements = self.delta.as_mut().expect("PATCH_DELTA not open");
        while self.pending > DELTA_MAX_COPY {
            elements.push((DELTA_MAX_COPY, DELTA_NONE, 0));
            self.pending -= DELTA_MAX_COPY;
        }
        elements.push((self.pending, addition, delta));
        self.pending = 0;
    }

    fn delta_start(&mut self) {
        assert!(self.base.patch.is_none() && self.delta.is_none());
        self.delta = Some(Vec::new());
        self.pending = 0;
    }

    fn delta_flush(&mut self) {
        if self.pending != 0 {
            self.element(DELTA_NONE, 0);
        }
    }

    fn delta_end(&mut self) {
        self.delta_flush();
        let elements = self.delta.take().expect("PATCH_DELTA not open");
        self.base.instructions.push(Instr::PatchDelta(elements));
    }

    fn add(&mut self) {
        let n = self.base.new_offset as usize;
        let o = self.base.old_offset as usize;
        let delta = val16(self.base.new, n).wrapping_sub(val16(self.old, o));
        let index = self.history.find(delta);
        self.element(index.map_or(DELTA_EXPLICIT, |i| i as u8), delta);
        self.history.use_delta(index, delta);
        self.additions.push((n as i64, delta));
        self.base.new_offset += 2;
        self.base.old_offset += 2;
    }

    fn set_addr(&mut self, addr: i64) {
        assert!(self.delta.is_none());
        self.base.set_addr(addr);
    }

    fn write(&mut self, length: i64) {
        assert!(self.delta.is_none());
        self.base.write(length);
    }

    fn copy(&mut self, length: i64) {
        if length <= 0 {
            return;
        }
        if self.delta.is_none() {
            self.base.copy(length);
            return;
        }
        self.pending += length as usize;
        self.base.new_offset += length;
        self.base.old_offset += length;
    }
}

/// Back pointer: (previous node, previous state, gap actions, copy actions)
type Back = (usize, usize, Actions, Actions);

/// Minimum size encoding as per `shortest_path_encode`, with PATCH_DELTA as an option
fn delta_encode(
    old: &[u8],
    new: &[u8],
    runs: &HashSet<Run>,
    predictor: &DeltaPredictor,
) -> (Vec<Instr>, Vec<(i64, u16)>) {
    let big_n = new.len() as i64;
    let n = Nodes::new(big_n, runs);
    let (ts, te, td, end_node) = (&n.ts, &n.te, &n.td, n.end_node);

    let mut add_cache: HashMap<(i64, i64, i64), f64> = HashMap::new();
    let mut additions_size = |start: i64, end: i64, diag: i64| -> f64 {
        *add_cache.entry((start, end, diag)).or_insert_with(|| {
            let mut size = 0.0;
            let mut pos = start;
            while pos < end {
                let o = pos + diag;
                if o < 0 || o + 2 > old.len() as i64 || pos + 2 > big_n {
                    return INF;
                }
                let delta = val16(new, pos as usize).wrapping_sub(val16(old, o as usize));
                size += predictor.size(pos, delta);
                pos += 2;
            }
            size
        })
    };

    let mut cost = vec![[INF, INF, INF]; ts.len()];
    let empty: Actions = &[];
    let mut back: Vec<[Back; 3]> = vec![[(0, 0, empty, empty); 3]; ts.len()];
    cost[0][OUT] = 0.0;
    let mut relay_offset: Vec<i64> = Vec::new();
    let mut relay_node: Vec<usize> = Vec::new();
    let mut relay_val = INF;
    let mut candidates = Candidates::new();
    let mut cands = Vec::new();

    // Cheapest way to write G bytes after node j, ending outside of any PATCH
    let exit_best = |cost: &Vec<[f64; 3]>,
                     additions_size: &mut dyn FnMut(i64, i64, i64) -> f64,
                     j: usize,
                     g: i64|
     -> (f64, usize, Actions) {
        let [c_out, c_in, c_dl] = cost[j];
        let write = if g != 0 { len_hdr_size(g) + g as f64 } else { 0.0 };
        let mut best: (f64, usize, Actions) = (c_out + write, OUT, &[Write]);
        if c_in + 1.0 + write < best.0 {
            best = (c_in + 1.0 + write, IN_PATCH, &[EndPatch, Write]);
        }
        let g_gt1 = if g > 1 { 1.0 } else { 0.0 };
        if 0 < g && g <= 255 && c_in + g as f64 + g_gt1 + 1.0 < best.0 {
            best = (c_in + g as f64 + g_gt1 + 1.0, IN_PATCH, &[Write, EndPatch]);
        }
        if c_dl + 2.0 + write < best.0 {
            best = (c_dl + 2.0 + write, IN_DELTA, &[EndDelta, Write]);
        }
        // Each addition is at least 1 byte, skip when that can't be cheaper
        if 0 < g && g <= MAX_DELTA_GAP && c_dl + 1.0 + (((g + 1) / 2) as f64) < best.0 {
            let c = c_dl + additions_size(te[j], te[j] + g, td[j]) + 1.0;
            if c < best.0 {
                best = (c, IN_DELTA, &[Add, EndDelta]);
            }
        }
        best
    };

    for j in 0..end_node {
        if j > 0 {
            // Enter from the best prior node, writing everything in between
            let x = ts[j];
            let i = relay_node[bisect_right(&relay_offset, x) - 1];
            let g = x - te[i];
            let (mut c, si, actions) = exit_best(&cost, &mut additions_size, i, g);
            c += addr_size(td[j] - td[i]);
            let l = te[j] - x;
            let options: [(usize, f64, Actions); 3] = [
                (OUT, len_hdr_size(l), &[]),
                (IN_PATCH, 1.0 + patch_copy_size(l), &[StartPatch]),
                (IN_DELTA, 1.0 + delta_copy_size(l), &[StartDelta]),
            ];
            for (state, size, copy_actions) in options {
                if c + size < cost[j][state] {
                    cost[j][state] = c + size;
                    back[j][state] = (i, si, actions, copy_actions);
                }
            }
        }

        let [c_out, c_in, c_dl] = cost[j];
        let p = te[j];
        let dj = td[j];
        let v = c_out.min(c_in + 1.0).min(c_dl + 2.0) - p as f64;
        if v < relay_val {
            relay_val = v;
            relay_offset.push(p);
            relay_node.push(j);
        }

        candidates.get(&n, j, p, &mut cands);
        let mut exit_cache: HashMap<i64, (f64, usize, Actions)> = HashMap::new();
        for &k in &cands {
            let s = ts[k].max(p);
            let g = s - p;
            let l = te[k] - s;
            if l <= 0 {
                continue;
            }
            let shift = td[k] - dj;

            // Ready for the COPY outside of any PATCH
            let (mut pre_out, mut out_state, mut out_actions) = *exit_cache
                .entry(g)
                .or_insert_with(|| exit_best(&cost, &mut additions_size, j, g));
            // Ready for the COPY inside a PATCH, after a WRITE
            let mut pre_patch = if 0 < g && g <= 255 {
                c_in + g as f64 + if g > 1 { 1.0 } else { 0.0 }
            } else {
                INF
            };
            // Ready for the COPY inside a PATCH_DELTA, nothing pending
            let (mut pre_delta, mut delta_state, mut delta_actions): (f64, usize, Actions) = (INF, OUT, &[]);
            // Odd gaps are covered by additions extending into this run
            let l_delta = l - (g & 1);
            if shift != 0 {
                // PATCH_DELTA can't change the offset
            } else if g == 0 {
                (pre_delta, delta_state, delta_actions) = (c_dl + 1.0, IN_DELTA, &[Flush]);
            } else if g <= MAX_DELTA_GAP
                && c_dl.min(c_out + 1.0).min(c_in + 2.0) + (((g + 1) / 2) as f64)
                    < (cost[k][IN_DELTA] - delta_copy_size(l_delta)).max(cost[k][OUT] - 1.0 - len_hdr_size(l_delta))
            {
                let size = additions_size(p, s, dj);
                let options: [(f64, usize, Actions); 3] = [
                    (c_dl + size, IN_DELTA, &[Add]),
                    (c_out + 1.0 + size, OUT, &[StartDelta, Add]),
                    (c_in + 2.0 + size, IN_PATCH, &[EndPatch, StartDelta, Add]),
                ];
                (pre_delta, delta_state, delta_actions) =
                    options.into_iter().min_by(|a, b| a.0.total_cmp(&b.0)).unwrap();
            }
            if shift != 0 {
                if pre_patch + 1.0 < pre_out {
                    (pre_out, out_state, out_actions) = (pre_patch + 1.0, IN_PATCH, &[Write, EndPatch]);
                }
                pre_out += addr_size(shift);
                pre_patch = INF;
            }

            let hdr_l = len_hdr_size(l);
            let patch_l = patch_copy_size(l);
            let ck = &mut cost[k];
            let bk = &mut back[k];
            let mut update = |state: usize, c: f64, entry: Back| {
                if c < ck[state] {
                    ck[state] = c;
                    bk[state] = entry;
                }
            };
            update(IN_PATCH, pre_patch + patch_l, (j, IN_PATCH, &[Write], &[]));
            update(OUT, pre_patch + 1.0 + hdr_l, (j, IN_PATCH, &[Write], &[EndPatch]));
            update(OUT, pre_out + hdr_l, (j, out_state, out_actions, &[]));
            update(
                IN_PATCH,
                pre_out + 1.0 + patch_l,
                (j, out_state, out_actions, &[StartPatch]),
            );
            update(
                IN_DELTA,
                pre_out + 1.0 + delta_copy_size(l),
                (j, out_state, out_actions, &[StartDelta]),
            );
            if pre_delta != INF {
                update(
                    IN_DELTA,
                    pre_delta + delta_copy_size(l_delta),
                    (j, delta_state, delta_actions, &[]),
                );
                update(
                    OUT,
                    pre_delta + 1.0 + len_hdr_size(l_delta),
                    (j, delta_state, delta_actions, &[EndDelta]),
                );
            }
        }

        let g = big_n - p;
        let (c, sj, actions) = *exit_cache
            .entry(g)
            .or_insert_with(|| exit_best(&cost, &mut additions_size, j, g));
        if c < cost[end_node][OUT] {
            cost[end_node][OUT] = c;
            back[end_node][OUT] = (j, sj, actions, empty);
        }
    }

    // Recover the path
    let mut path = Vec::new();
    let (mut node, mut state) = (end_node, OUT);
    while node != 0 {
        let (j, sj, gap_actions, copy_actions) = back[node][state];
        path.push((j, node, gap_actions, copy_actions));
        node = j;
        state = sj;
    }

    let mut builder = DeltaInstrBuilder::new(old, new);
    for &(j, k, gap_actions, copy_actions) in path.iter().rev() {
        let s = ts[k].max(te[j]);
        for &action in gap_actions {
            match action {
                EndPatch => builder.base.patch_end(),
                EndDelta => builder.delta_end(),
                StartDelta => builder.delta_start(),
                Flush => builder.delta_flush(),
                Write => {
                    if s > builder.base.new_offset {
                        builder.write(s - builder.base.new_offset);
                    }
                }
                Add => {
                    while builder.base.new_offset < s {
                        builder.add();
                    }
                }
                StartPatch => unreachable!(),
            }
        }
        if k == end_node {
            break;
        }
        let target = builder.base.new_offset + td[k];
        if builder.base.old_offset != target {
            builder.set_addr(target);
        }
        for &action in copy_actions {
            match action {
                EndPatch => builder.base.patch_end(),
                EndDelta => builder.delta_end(),
                StartPatch => builder.base.patch_start(),
                StartDelta => builder.delta_start(),
                _ => unreachable!(),
            }
        }
        builder.copy(te[k] - builder.base.new_offset);
    }
    assert!(builder.base.patch.is_none() && builder.delta.is_none());
    assert_eq!(builder.base.new_offset, big_n);
    (builder.base.instructions, builder.additions)
}

fn encoded_len(instructions: &[Instr]) -> usize {
    instructions.iter().map(Instr::encoded_len).sum()
}

/// Predicted additions from the gaps of an encoding without additions
pub fn initial_additions(old: &[u8], new: &[u8], gaps: &[Gap]) -> Vec<(i64, u16)> {
    let mut additions = Vec::new();
    for &(start, end, diag_before, diag_after) in gaps {
        if diag_before == diag_after && end - start <= MAX_DELTA_GAP {
            let mut pos = start;
            while pos < end {
                let o = pos + diag_before;
                if o >= 0 && o + 2 <= old.len() as i64 && pos + 2 <= new.len() as i64 {
                    additions.push((pos, val16(new, pos as usize).wrapping_sub(val16(old, o as usize))));
                }
                pos += 2;
            }
        }
    }
    additions
}

/// Encode the new file as instructions applied to the original file
pub fn encode(old: &[u8], new: &[u8]) -> Vec<Instr> {
    let runs = refined_runs(old, new);
    let (mut best, gaps) = shortest_path_encode(new, &runs);
    let mut best_size = encoded_len(&best);

    // Initial prediction from the gaps of the encoding without additions
    let mut additions = initial_additions(old, new, &gaps);

    // Refine the prediction with the additions actually used
    for _ in 0..2 {
        let (instructions, used) = delta_encode(old, new, &runs, &DeltaPredictor::new(&additions));
        additions = used;
        let size = encoded_len(&instructions);
        if size < best_size {
            best = instructions;
            best_size = size;
        }
    }
    best
}
