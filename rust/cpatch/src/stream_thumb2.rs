//! Shortest path encoder for the element stream format (version 3), for Cortex-M Thumb-2 images
//!
//! Uses the candidate COPY runs of `shortest_path`, with the cost model of an element stream:
//! each operation costs its header byte and payload, while the copy before it only costs its
//! length extension. Gaps between runs are filled with any mix of additions and literals.
//!
//! Every copy relocates the sites it contains, so runs are recomputed against the relocated view
//! of the original. The relocation map and pointer base are fitted to where a previous encoding
//! copied code from.

use std::collections::{HashMap, HashSet};

use crate::matching::{Run, true_runs};
use crate::shortest_path::{Candidates, INF, Nodes, bisect_right, refined_runs, shortest_path_encode};
use crate::shortest_path_delta::initial_additions;
use crate::stream::{
    Element, FLAG_BRANCH, FLAG_POINTER, HISTORY_SIZE, History, MAP_ENTRY_LEN, Op, Preamble, Region, Relocator,
    svarint_len, thumb_branch_offset, uvarint_len,
};

/// Largest gap between runs that is considered for filling with additions
const MAX_FILL_GAP: i64 = 24;
/// Minimum length of a run
const MIN_RUN: i64 = 2;
/// Runs on the same diagonal closer than this are recomputed together
const WINDOW_MERGE: i64 = 512;
/// Distance before and after the runs on a diagonal that is searched for relocated runs
const WINDOW_MARGIN: i64 = 64;
/// Approximate bytes saved by each site that the relocation map relocates correctly
const SITE_VALUE: i64 = 2;
/// Minimum number of pointers explained by a base address or region before relocating them
const MIN_POINTERS: i64 = 16;
/// Pointer regions outside of the original image
const MAX_REGIONS: usize = 4;
/// Largest gap between changed pointers in the same region
const REGION_GAP: u32 = 1 << 16;
/// Largest change of a pointer into a region
const MAX_REGION_SHIFT: i64 = 1 << 16;

fn val16(data: &[u8], offset: usize) -> u16 {
    u16::from_le_bytes([data[offset], data[offset + 1]])
}

fn val32(data: &[u8], offset: usize) -> u32 {
    u32::from_le_bytes(data[offset..offset + 4].try_into().unwrap())
}

/// Encoded size of the length extension of a copy
fn ext_cost(length: i64) -> f64 {
    if length < 15 {
        0.0
    } else {
        uvarint_len((length - 15) as u64) as f64
    }
}

fn literal_cost(length: i64) -> f64 {
    match length {
        0 => 0.0,
        1 => 2.0,
        _ => (1 + uvarint_len((length - 2) as u64)) as f64 + length as f64,
    }
}

/// Saving when a shift directly follows a literal, as LITERAL_SHIFT
fn merged_shift(literal: bool, shift: i64) -> f64 {
    if literal && shift != 0 { 1.0 } else { 0.0 }
}

fn shift_cost(shift: i64) -> f64 {
    if shift == 0 {
        0.0
    } else {
        (1 + svarint_len(shift)) as f64
    }
}

/// Predicted encoded size of an addition, from the delta history of a previous encoding
struct Predictor {
    offsets: Vec<i64>,
    snapshots: Vec<[u16; HISTORY_SIZE]>,
}

impl Predictor {
    fn new(additions: &[(i64, u16)]) -> Self {
        let mut history = History::default();
        let mut offsets = Vec::with_capacity(additions.len());
        let mut snapshots = vec![history.deltas];
        for &(offset, delta) in additions {
            history.use_delta(history.find(delta), delta);
            offsets.push(offset);
            snapshots.push(history.deltas);
        }
        Predictor { offsets, snapshots }
    }

    fn size(&self, offset: i64, delta: u16) -> f64 {
        let snapshot = &self.snapshots[self.offsets.partition_point(|&o| o < offset)];
        if snapshot.contains(&delta) { 1.0 } else { 3.0 }
    }
}

// Gap filling DP states: no literal open, literal of 1 byte open, literal of 2+ bytes open
const CLOSED: usize = 0;
const LIT_1: usize = 1;
const LIT_N: usize = 2;
// Back pointer of a state reached by an addition (otherwise reached by a literal byte)
const BY_ADD: usize = 3;

#[derive(Clone, Copy, Debug)]
enum Step {
    Add,
    Literal(i64),
}

// How the gap before a run is filled
const FILL_LITERAL: u8 = 0;
/// Additions on the diagonal of the previous run, then any shift
const FILL_BEFORE: u8 = 1;
/// Shift, then additions on the diagonal of the next run
const FILL_AFTER: u8 = 2;
/// The final addition extends one byte into the next run
const FILL_OVER: u8 = 4;

/// Output of a search
struct Encoding {
    elements: Vec<Element>,
    /// (new offset, delta) of each addition
    additions: Vec<(i64, u16)>,
    /// (new start, new end, diagonal) of the regions produced from the original
    coverage: Vec<Run>,
}

struct Search<'a> {
    old: &'a [u8],
    new: &'a [u8],
    predictor: Predictor,
    fill_cache: HashMap<(i64, i64, i64), (f64, f64, f64)>,
}

impl<'a> Search<'a> {
    fn add_cost(&self, x: i64, d: i64) -> f64 {
        let o = x + d;
        if o < 0 || o + 2 > self.old.len() as i64 || x + 2 > self.new.len() as i64 {
            return INF;
        }
        let delta = val16(self.new, x as usize).wrapping_sub(val16(self.old, o as usize));
        self.predictor.size(x, delta)
    }

    /// Minimum costs of producing `new[p..s]` with additions on diagonal `d` and literals.
    /// Index `s - p + 1` is reached by an addition that extends one byte past `s`.
    fn fill_table(&self, p: i64, s: i64, d: i64) -> Vec<[(f64, usize); 3]> {
        let g = (s - p) as usize;
        let mut t = vec![[(INF, 0usize); 3]; g + 2];
        t[0][CLOSED].0 = 0.0;
        for x in 0..g {
            let add = self.add_cost(p + x as i64, d);
            for state in [CLOSED, LIT_1, LIT_N] {
                let c = t[x][state].0;
                if c == INF {
                    continue;
                }
                let (next, inc) = match state {
                    CLOSED => (LIT_1, 2.0),
                    LIT_1 => (LIT_N, 2.0),
                    _ => (LIT_N, 1.0),
                };
                if c + inc < t[x + 1][next].0 {
                    t[x + 1][next] = (c + inc, state);
                }
                if c + add < t[x + 2][CLOSED].0 {
                    t[x + 2][CLOSED] = (c + add, BY_ADD + state);
                }
            }
        }
        t
    }

    /// Costs of filling `new[p..s]` on diagonal `d`: ending with an addition, ending with a
    /// literal, and ending with an addition one byte past `s`
    fn fill_cost(&mut self, p: i64, s: i64, d: i64) -> (f64, f64, f64) {
        if let Some(&c) = self.fill_cache.get(&(p, s, d)) {
            return c;
        }
        let t = self.fill_table(p, s, d);
        let g = (s - p) as usize;
        let c = (t[g][CLOSED].0, t[g][LIT_1].0.min(t[g][LIT_N].0), t[g + 1][CLOSED].0);
        self.fill_cache.insert((p, s, d), c);
        c
    }

    /// Steps of the cheapest fill, where ending with a literal saves `literal_saving`
    fn fill_plan(&self, p: i64, s: i64, d: i64, over: bool, literal_saving: f64) -> Vec<Step> {
        let t = self.fill_table(p, s, d);
        let g = (s - p) as usize;
        let end_cost = |state: usize| t[g][state].0 - if state == CLOSED { 0.0 } else { literal_saving };
        let (mut x, mut state) = if over {
            (g + 1, CLOSED)
        } else {
            (g, (0..3).min_by(|&a, &b| end_cost(a).total_cmp(&end_cost(b))).unwrap())
        };
        let mut steps = Vec::new();
        while x > 0 {
            let prev = t[x][state].1;
            if prev >= BY_ADD {
                steps.push(Step::Add);
                x -= 2;
                state = prev - BY_ADD;
            } else {
                match steps.last_mut() {
                    Some(Step::Literal(n)) if state != CLOSED => *n += 1,
                    _ => steps.push(Step::Literal(1)),
                }
                x -= 1;
                state = prev;
            }
        }
        steps.reverse();
        steps
    }

    /// Minimum size encoding over the runs of `nodes`
    fn search(&mut self, nodes: &Nodes, atomic: &HashSet<(i64, i64)>) -> Encoding {
        let (ts, te, td, end_node) = (&nodes.ts, &nodes.te, &nodes.td, nodes.end_node);
        let big_n = self.new.len() as i64;
        // A copy may not start inside a site that only matches when relocated in full
        let cuts = |d: i64, x: i64| (1..4).any(|i| atomic.contains(&(d, x - i)));
        // Operation required between two runs: a shift, or splitting consecutive copies
        let op_cost = |i: usize, g: i64, shift: i64| {
            if shift != 0 {
                shift_cost(shift)
            } else if g == 0 && i != 0 {
                1.0
            } else {
                0.0
            }
        };

        let mut cost = vec![INF; ts.len()];
        let mut back = vec![(0usize, FILL_LITERAL); ts.len()];
        cost[0] = 0.0;
        // Running minimum of (cost - new offset), for long range literal transitions
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
                let shift = td[j] - td[i];
                let c =
                    cost[i] + literal_cost(g) + op_cost(i, g, shift) - merged_shift(g > 0, shift) + ext_cost(te[j] - x);
                if c < cost[j] {
                    cost[j] = c;
                    back[j] = (i, FILL_LITERAL);
                }
            }
            let c_j = cost[j];
            let p = te[j];
            let dj = td[j];
            if c_j - (p as f64) < relay_val {
                relay_val = c_j - p as f64;
                relay_offset.push(p);
                relay_node.push(j);
            }

            candidates.get(nodes, j, p, &mut cands);
            for &k in &cands {
                let s = ts[k].max(p);
                let g = s - p;
                let l = te[k] - s;
                if l <= 0 {
                    continue;
                }
                let dk = td[k];
                let shift = dk - dj;
                let mut best = (INF, FILL_LITERAL);
                if g == 0 {
                    if s == ts[k] || !cuts(dk, s) {
                        best = (op_cost(j, g, shift) + ext_cost(l), FILL_LITERAL);
                    }
                } else {
                    let sc = shift_cost(shift);
                    best = (
                        literal_cost(g) + sc - merged_shift(true, shift) + ext_cost(l),
                        FILL_LITERAL,
                    );
                    if g <= MAX_FILL_GAP {
                        for (kind, d) in [(FILL_BEFORE, dj), (FILL_AFTER, dk)] {
                            if kind == FILL_AFTER && shift == 0 {
                                continue;
                            }
                            let (closed, literal, over) = self.fill_cost(p, s, d);
                            let exact = if kind == FILL_BEFORE {
                                closed.min(literal - merged_shift(true, shift))
                            } else {
                                closed.min(literal)
                            };
                            if exact + sc + ext_cost(l) < best.0 {
                                best = (exact + sc + ext_cost(l), kind);
                            }
                            if l >= 2 && !cuts(dk, s + 1) && over + sc + ext_cost(l - 1) < best.0 {
                                best = (over + sc + ext_cost(l - 1), kind | FILL_OVER);
                            }
                        }
                    }
                }
                if c_j + best.0 < cost[k] {
                    cost[k] = c_j + best.0;
                    back[k] = (j, best.1);
                }
            }

            // Write the remainder of the file
            let g = big_n - p;
            let mut best = if g == 0 {
                (if j == 0 { 0.0 } else { 1.0 }, FILL_LITERAL)
            } else {
                (literal_cost(g), FILL_LITERAL)
            };
            if 0 < g && g <= MAX_FILL_GAP {
                let (closed, literal, _) = self.fill_cost(p, big_n, dj);
                let exact = closed.min(literal);
                if exact < best.0 {
                    best = (exact, FILL_BEFORE);
                }
            }
            if c_j + best.0 < cost[end_node] {
                cost[end_node] = c_j + best.0;
                back[end_node] = (j, best.1);
            }
        }

        // Recover the path
        let mut path = Vec::new();
        let mut node = end_node;
        while node != 0 {
            let (j, kind) = back[node];
            path.push((j, node, kind));
            node = j;
        }
        path.reverse();

        let mut builder = Builder::new(self.old, self.new);
        for (j, k, kind) in path {
            let p = te[j];
            let s = if k == end_node { big_n } else { ts[k].max(p) };
            let dk = if k == end_node { td[j] } else { td[k] };
            let shift = dk - td[j];
            let over = kind & FILL_OVER != 0;
            match kind & !FILL_OVER {
                FILL_BEFORE => {
                    let plan = self.fill_plan(p, s, td[j], over, merged_shift(true, shift));
                    builder.fill(&plan, td[j]);
                }
                FILL_AFTER => {
                    builder.shift(shift);
                    builder.fill(&self.fill_plan(p, s, dk, over, 0.0), dk);
                }
                _ if s > p => {
                    builder.literal(s - p);
                    if td[j] == dk {
                        // Replaces bytes of the original on the diagonal
                        builder.cover(p, s, dk);
                    }
                }
                _ => {}
            }
            if k == end_node {
                break;
            }
            if kind & !FILL_OVER != FILL_AFTER && shift != 0 {
                builder.shift(shift);
            } else if s == p && shift == 0 && builder.pending > 0 {
                builder.op(Op::None);
            }
            builder.copy(te[k] - builder.new_offset);
        }
        if builder.pending > 0 {
            builder.op(Op::None);
        }
        assert_eq!(builder.new_offset, big_n);
        Encoding {
            elements: builder.elements,
            additions: builder.additions,
            coverage: builder.coverage,
        }
    }
}

/// Construct an element list from the new file, tracking file offsets
struct Builder<'a> {
    old: &'a [u8],
    new: &'a [u8],
    elements: Vec<Element>,
    history: History,
    /// Copy length to include in the next element
    pending: usize,
    new_offset: i64,
    old_offset: i64,
    additions: Vec<(i64, u16)>,
    coverage: Vec<Run>,
}

impl<'a> Builder<'a> {
    fn new(old: &'a [u8], new: &'a [u8]) -> Self {
        Builder {
            old,
            new,
            elements: Vec::new(),
            history: History::default(),
            pending: 0,
            new_offset: 0,
            old_offset: 0,
            additions: Vec::new(),
            coverage: Vec::new(),
        }
    }

    fn diag(&self) -> i64 {
        self.old_offset - self.new_offset
    }

    /// Record that `new[start..end]` was produced from the original on diagonal `d`
    fn cover(&mut self, start: i64, end: i64, d: i64) {
        let start = start.max(-d);
        let end = end.min(self.old.len() as i64 - d);
        if start >= end {
            return;
        }
        // Merge contiguous regions, so that sites split between operations are still found
        match self.coverage.last_mut() {
            Some(last) if last.2 == d && last.1 == start => last.1 = end,
            _ => self.coverage.push((start, end, d)),
        }
    }

    fn op(&mut self, op: Op) {
        self.elements.push(Element { copy: self.pending, op });
        self.pending = 0;
    }

    fn copy(&mut self, length: i64) {
        assert!(length > 0);
        self.cover(self.new_offset, self.new_offset + length, self.diag());
        self.pending += length as usize;
        self.new_offset += length;
        self.old_offset += length;
    }

    fn shift(&mut self, shift: i64) {
        self.old_offset += shift;
        if self.pending == 0
            && let Some(Element {
                op: Op::Literal(data), ..
            }) = self.elements.last_mut()
        {
            let data = std::mem::take(data);
            self.elements.last_mut().unwrap().op = Op::LiteralShift(data, shift);
            return;
        }
        self.op(Op::Shift(shift));
    }

    fn literal(&mut self, length: i64) {
        let (n, length) = (self.new_offset as usize, length as usize);
        self.op(Op::Literal(self.new[n..n + length].to_vec()));
        self.new_offset += length as i64;
        self.old_offset += length as i64;
    }

    fn fill(&mut self, steps: &[Step], d: i64) {
        assert_eq!(self.diag(), d);
        let start = self.new_offset;
        for &step in steps {
            match step {
                Step::Add => {
                    let (n, o) = (self.new_offset as usize, self.old_offset as usize);
                    let delta = val16(self.new, n).wrapping_sub(val16(self.old, o));
                    let index = self.history.find(delta);
                    self.op(match index {
                        Some(i) => Op::Add(i as u8),
                        None => Op::AddExplicit(delta),
                    });
                    self.history.use_delta(index, delta);
                    self.additions.push((n as i64, delta));
                    self.new_offset += 2;
                    self.old_offset += 2;
                }
                Step::Literal(length) => self.literal(length),
            }
        }
        self.cover(start, self.new_offset, d);
    }
}

/// Sorted original offsets of the relocation sites
fn site_offsets(old: &[u8], reloc: &Relocator) -> Vec<i64> {
    (0..old.len().saturating_sub(3) as i64)
        .step_by(2)
        .filter(|&a| reloc.branch_site(a).is_some() || reloc.pointer_site(a))
        .collect()
}

/// Runs that match the new file when copied with relocation, and the sites inside them that
/// only match when copied in full, as (diagonal, new offset)
fn relocated_runs(
    old: &[u8],
    new: &[u8],
    runs: &HashSet<Run>,
    reloc: &Relocator,
) -> (HashSet<Run>, HashSet<(i64, i64)>) {
    let sites = site_offsets(old, reloc);
    let mut found = HashSet::new();
    let mut atomic = HashSet::new();

    let mut window = |d: i64, start: i64, end: i64| {
        let start = start.max(0).max(-d);
        let end = end.min(new.len() as i64).min(old.len() as i64 - d);
        if end - start < MIN_RUN {
            return;
        }
        let plain = &old[(start + d) as usize..(end + d) as usize];
        let target = &new[start as usize..end as usize];
        let mut mask: Vec<bool> = plain.iter().zip(target).map(|(a, b)| a == b).collect();
        let mut splits = Vec::new();
        let first = sites.partition_point(|&a| a < start + d);
        for &a in &sites[first..] {
            if a + 4 > end + d {
                break;
            }
            let rel = (a - d - start) as usize;
            let bytes = reloc.relocate(a, a - d).unwrap();
            if bytes == plain[rel..rel + 4] {
                continue;
            }
            if bytes == target[rel..rel + 4] {
                mask[rel..rel + 4].fill(true);
                atomic.insert((d, a - d));
            } else if mask[rel..rel + 4].iter().all(|&m| m) {
                // Copying the site in full would relocate it, the original matches when split
                splits.push(rel + 2);
            }
        }
        for (s, e) in true_runs(&mask) {
            let mut s = s;
            let lo = splits.partition_point(|&x| x <= s);
            let hi = splits.partition_point(|&x| x < e);
            for &x in splits[lo..hi].iter().chain(std::iter::once(&e)) {
                if (x - s) as i64 >= MIN_RUN {
                    found.insert((start + s as i64, start + x as i64, d));
                }
                s = x;
            }
        }
    };

    // Windows around the runs on each diagonal, as copied with relocation. Relocation can join
    // and extend the runs.
    let mut by_diag: HashMap<i64, Vec<(i64, i64)>> = HashMap::new();
    for &(start, end, diag) in runs {
        by_diag.entry(diag).or_default().push((start, end));
    }
    let mut diags: Vec<_> = by_diag.into_iter().collect();
    diags.sort_unstable();
    for (d, mut spans) in diags {
        spans.sort_unstable();
        let (mut w_start, mut w_end) = spans[0];
        for &(s, e) in &spans[1..] {
            if s - w_end > WINDOW_MERGE {
                window(d, w_start - WINDOW_MARGIN, w_end + WINDOW_MARGIN);
                w_start = s;
            }
            w_end = w_end.max(e);
        }
        window(d, w_start - WINDOW_MARGIN, w_end + WINDOW_MARGIN);
    }
    (found, atomic)
}

/// Base address that explains the most changed words of the original as relocated pointers
fn pointer_base(old: &[u8], new: &[u8], coverage: &[Run]) -> Option<u32> {
    // Original image regions by the shift they moved with
    let mut by_shift: HashMap<i64, Vec<(i64, i64)>> = HashMap::new();
    for &(s, e, d) in coverage {
        by_shift.entry(-d).or_default().push((s + d, e + d));
    }
    for segments in by_shift.values_mut() {
        segments.sort_unstable();
        let mut merged: Vec<(i64, i64)> = Vec::new();
        for &(s, e) in segments.iter() {
            match merged.last_mut() {
                Some(m) if s <= m.1 + 64 => m.1 = m.1.max(e),
                _ => merged.push((s, e)),
            }
        }
        *segments = merged;
    }

    // Each changed word votes for the base addresses under which it points to a region
    // that moved by the same amount
    let mut events: Vec<(i64, i64)> = Vec::new();
    for &(s, e, d) in coverage {
        let mut a = (s + d + 3) & !3;
        while a + 4 <= e + d {
            let (v_old, v_new) = (val32(old, a as usize) as i64, val32(new, (a - d) as usize) as i64);
            let delta = v_new - v_old;
            if delta != 0
                && delta.abs() < old.len() as i64
                && let Some(segments) = by_shift.get(&delta)
                && segments.len() <= 16
            {
                for &(lo, hi) in segments {
                    events.push((v_old - hi + 1, 1));
                    events.push((v_old - lo + 1, -1));
                }
            }
            a += 4;
        }
    }
    events.sort_unstable();
    // Ranges of base addresses with their vote counts
    let mut ranges = Vec::new();
    let mut count = 0;
    for (i, &(x, inc)) in events.iter().enumerate() {
        count += inc;
        if i + 1 < events.len() && events[i + 1].0 > x {
            ranges.push((x, events[i + 1].0, count));
        }
    }
    let best = ranges.iter().map(|r| r.2).max().unwrap_or(0);
    if best < MIN_POINTERS {
        return None;
    }
    // Images start on flash page boundaries, prefer the most aligned address that explains
    // close to the most words
    let aligned = |lo: i64, hi: i64| {
        (0..32)
            .rev()
            .map(|k| ((hi - 1) & !((1i64 << k) - 1), k))
            .find(|&(b, _)| b >= lo)
            .unwrap()
    };
    let (base, _, _) = ranges
        .iter()
        .filter(|r| r.2 * 50 >= best * 49)
        .map(|&(lo, hi, c)| {
            let (b, k) = aligned(lo, hi);
            (b, k, c)
        })
        .max_by_key(|&(_, k, c)| (k, c))
        .unwrap();
    (0..=(u32::MAX as i64 - old.len() as i64))
        .contains(&base)
        .then_some(base as u32)
}

/// Piecewise constant fit of (offset, shift) samples, dropping entries that save less than
/// they cost
fn fit_map(mut samples: Vec<(i64, i64)>) -> Vec<(u32, i32)> {
    samples.sort_unstable();
    let mut entries: Vec<(i64, i64)> = Vec::new();
    for &(t, shift) in &samples {
        if entries.last().map_or(0, |e| e.1) != shift && entries.last().is_none_or(|e| e.0 != t) {
            entries.push((t, shift));
        }
    }
    loop {
        // Samples matching each entry, beyond those that would match without it
        let mut benefit = vec![0i64; entries.len()];
        let mut idx = 0;
        for &(t, shift) in &samples {
            while idx < entries.len() && entries[idx].0 <= t {
                idx += 1;
            }
            if idx > 0 {
                let e = idx - 1;
                let prev = if e == 0 { 0 } else { entries[e - 1].1 };
                benefit[e] += i64::from(shift == entries[e].1) - i64::from(shift == prev);
            }
        }
        // Never drop neighbours in the same round, their benefits depend on each other
        let mut keep = vec![true; entries.len()];
        let mut dropped = false;
        for i in 0..entries.len() {
            if (i == 0 || keep[i - 1]) && benefit[i] * SITE_VALUE < MAP_ENTRY_LEN as i64 {
                keep[i] = false;
                dropped = true;
            }
        }
        if !dropped {
            break;
        }
        let mut merged: Vec<(i64, i64)> = Vec::new();
        for (e, _) in entries.iter().zip(&keep).filter(|(_, k)| **k) {
            if merged.last().map_or(0, |m| m.1) != e.1 {
                merged.push(*e);
            }
        }
        entries = merged;
    }
    entries
        .into_iter()
        .filter(|&(t, shift)| t < 1 << 24 && (-(1 << 23)..1 << 23).contains(&shift))
        .map(|(t, shift)| (t as u32, shift as i32))
        .collect()
}

/// Address ranges outside of the original image where many words changed by small amounts,
/// such as pointers into RAM
fn pointer_regions(old: &[u8], new: &[u8], coverage: &[Run], base: u32) -> Vec<Region> {
    let branches = Preamble {
        flags: FLAG_BRANCH,
        ..Default::default()
    };
    let branches = Relocator::new(old, &branches);
    let mut values = Vec::new();
    for &(s, e, d) in coverage {
        let mut a = (s + d + 3) & !3;
        while a + 4 <= e + d {
            let (v_old, v_new) = (val32(old, a as usize), val32(new, (a - d) as usize));
            // Small values are more likely to be constants than pointers, and words that
            // overlap branches are instructions
            if v_old != v_new
                && (-2..=2).step_by(2).all(|i| branches.branch_site(a + i).is_none())
                && v_old >= 1 << 16
                && v_old.wrapping_sub(base) as usize >= old.len()
                && (v_new as i64 - v_old as i64).abs() < MAX_REGION_SHIFT
            {
                values.push(v_old);
            }
            a += 4;
        }
    }
    values.sort_unstable();
    let mut clusters = Vec::new();
    let mut i = 0;
    while i < values.len() {
        let mut j = i + 1;
        while j < values.len() && values[j] - values[j - 1] < REGION_GAP {
            j += 1;
        }
        if (j - i) as i64 >= MIN_POINTERS {
            clusters.push((j - i, values[i], values[j - 1] - values[i] + 1));
        }
        i = j;
    }
    // Regions with the most changed pointers
    clusters.sort_unstable_by(|a, b| b.cmp(a));
    clusters.truncate(MAX_REGIONS);
    clusters.sort_unstable_by_key(|c| c.1);
    clusters
        .into_iter()
        .map(|(_, base, length)| Region {
            base,
            length,
            map: Vec::new(),
        })
        .collect()
}

/// Relocation preamble fitted to the regions of an existing encoding
fn build_preamble(old: &[u8], new: &[u8], coverage: &[Run]) -> Preamble {
    let mut preamble = Preamble {
        flags: FLAG_BRANCH,
        ..Default::default()
    };
    if let Some(base) = pointer_base(old, new, coverage) {
        preamble.flags |= FLAG_POINTER;
        preamble.base = base;
        preamble.regions = pointer_regions(old, new, coverage, base);
    }
    let reloc = Relocator::new(old, &preamble);
    let sites = site_offsets(old, &reloc);

    // The shift each site requires to match the new file
    let mut samples = Vec::new();
    let mut region_samples = vec![Vec::new(); preamble.regions.len()];
    for &(s, e, d) in coverage {
        let first = sites.partition_point(|&a| a < s + d);
        for &a in &sites[first..] {
            if a + 4 > e + d {
                break;
            }
            let (a_u, n) = (a as usize, (a - d) as usize);
            if let Some(offset) = reloc.branch_site(a) {
                let target = a + 4 + offset as i64;
                let (h1, h2) = (val16(new, n), val16(new, n + 2));
                if (0..old.len() as i64).contains(&target)
                    && (h2 & 0xD000) == (val16(old, a_u + 2) & 0xD000)
                    && let Some(new_offset) = thumb_branch_offset(h1, h2)
                {
                    samples.push((target, (a - d) + 4 + new_offset as i64 - target));
                }
            } else if let Some((region, target)) = reloc.pointer_target(a) {
                let sample = (target, val32(new, n) as i64 - val32(old, a_u) as i64);
                match region {
                    None => samples.push(sample),
                    Some(i) => region_samples[i].push(sample),
                }
            }
        }
    }
    preamble.map = fit_map(samples);
    let mut regions = Vec::new();
    for (mut region, samples) in std::mem::take(&mut preamble.regions).into_iter().zip(region_samples) {
        region.map = fit_map(samples.clone());
        // Pointers the region relocates, less the unchanged words it breaks
        let gain: i64 = samples
            .iter()
            .map(|&(t, needed)| {
                let i = region.map.partition_point(|e| e.0 as i64 <= t);
                let shift = if i == 0 { 0 } else { region.map[i - 1].1 as i64 };
                i64::from(needed != 0 && shift == needed) - i64::from(needed == 0 && shift != 0)
            })
            .sum();
        if gain * SITE_VALUE > (10 + MAP_ENTRY_LEN * region.map.len()) as i64 {
            regions.push(region);
        }
    }
    preamble.regions = regions;
    preamble
}

fn encoded_len(preamble: &Preamble, elements: &[Element]) -> usize {
    preamble.encoded_len() + elements.iter().map(Element::encoded_len).sum::<usize>()
}

/// Encode the new file as elements applied to the original file
pub fn encode(old: &[u8], new: &[u8]) -> (Preamble, Vec<Element>) {
    let runs = refined_runs(old, new);
    let (_, gaps) = shortest_path_encode(new, &runs);
    // Initial prediction from the gaps of the encoding without additions
    let mut additions = initial_additions(old, new, &gaps);
    let mut best: Option<(usize, Preamble, Vec<Element>)> = None;
    let mut consider = |preamble: Preamble, elements: Vec<Element>| {
        let size = encoded_len(&preamble, &elements);
        if best.as_ref().is_none_or(|b| size < b.0) {
            best = Some((size, preamble, elements));
        }
    };

    let search = |nodes: &Nodes, atomic: &HashSet<(i64, i64)>, additions: &[(i64, u16)]| {
        Search {
            old,
            new,
            predictor: Predictor::new(additions),
            fill_cache: HashMap::new(),
        }
        .search(nodes, atomic)
    };

    // Without relocation, refining the prediction with the additions actually used
    let nodes = Nodes::new(new.len() as i64, &runs);
    let mut coverage = Vec::new();
    for _ in 0..2 {
        let encoding = search(&nodes, &HashSet::new(), &additions);
        additions = encoding.additions;
        coverage = encoding.coverage;
        consider(Preamble::default(), encoding.elements);
    }

    // Relocation fitted to where the previous encoding copied from. The windows searched for
    // relocated runs grow with the runs already found.
    let mut seed = runs;
    for _ in 0..2 {
        let preamble = build_preamble(old, new, &coverage);
        let reloc = Relocator::new(old, &preamble);
        let (reloc_runs, atomic) = relocated_runs(old, new, &seed, &reloc);
        seed.extend(reloc_runs.iter().copied());
        let nodes = Nodes::new(new.len() as i64, &reloc_runs);
        let encoding = search(&nodes, &atomic, &additions);
        additions = encoding.additions;
        coverage = encoding.coverage;
        consider(preamble, encoding.elements);
    }
    let (_, preamble, elements) = best.unwrap();
    (preamble, elements)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::stream::{apply, decode, encode as encode_data, thumb_branch_encode};

    /// Firmware-like image of functions that call each other, with literal pools of pointers to
    /// functions and RAM variables. `inserted` bytes of new code are placed before function 40.
    fn firmware(inserted: usize, ram_shift: u32) -> Vec<u8> {
        const FUNC_LEN: usize = 256;
        const BASE: u32 = 0x1_0000;
        let mut state = 11u64;
        let mut rand = || {
            state = state
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1442695040888963407);
            (state >> 33) as u32
        };
        let bodies: Vec<Vec<u8>> = (0..100)
            .map(|_| (0..FUNC_LEN).map(|_| rand() as u8).collect())
            .collect();
        let start = |f: usize| (f * FUNC_LEN + if f >= 40 { inserted } else { 0 }) as i64;
        let mut image = Vec::new();
        for (f, body) in bodies.iter().enumerate() {
            if f == 40 {
                image.extend(std::iter::repeat_n(0xA5, inserted));
            }
            let mut body = body.clone();
            for i in 0..4usize {
                // Call to another function
                let at = start(f) + 16 + 32 * i as i64;
                let (h1, h2) = thumb_branch_encode(0xF800, start((f * 7 + i) % 100) - (at + 4)).unwrap();
                body[16 + 32 * i..20 + 32 * i].copy_from_slice(&[h1.to_le_bytes(), h2.to_le_bytes()].concat());
                // Pointers to a function and a RAM variable
                let function = BASE + start((f * 3 + i) % 100) as u32 + 1;
                let variable = 0x2000_0000 + ((f * 4 + i) as u32 * 8) + if f >= 50 { ram_shift } else { 0 };
                body[128 + 8 * i..132 + 8 * i].copy_from_slice(&function.to_le_bytes());
                body[132 + 8 * i..136 + 8 * i].copy_from_slice(&variable.to_le_bytes());
            }
            image.extend(body);
        }
        image
    }

    #[test]
    fn validation_runs_every_operation_and_relocation() {
        let original = firmware(0, 0);
        let patch = crate::cpatch::validation(&original, false, false, false, true).unwrap();
        assert_eq!(crate::cpatch::apply(&original, &patch).unwrap(), original);
        assert_eq!(patch[4], 3);
        let (preamble, elements) = decode(&patch[crate::cpatch::HEADER_LEN..]).unwrap();
        assert!(crate::stream::op_counts(&elements).iter().all(|&(_, count)| count > 0));
        let indices: HashSet<u8> = elements
            .iter()
            .filter_map(|e| match e.op {
                Op::Add(i) => Some(i),
                _ => None,
            })
            .collect();
        assert_eq!(indices.len(), crate::stream::HISTORY_SIZE);
        let copies: HashSet<usize> = elements.iter().map(|e| e.copy).collect();
        assert!((1..16).chain([142, 143]).all(|c| copies.contains(&c)));
        assert!(preamble.map.iter().any(|e| e.1 != 0));
        assert!(preamble.regions.iter().flat_map(|r| &r.map).any(|e| e.1 != 0));
        // Sites are relocated by non-zero shifts, so appliers that do not relocate fail
        let mut out = Vec::new();
        apply(&original, &Preamble::default(), &elements, &mut out).unwrap();
        assert_ne!(out, original);
    }

    #[test]
    fn relocates_moved_code() {
        let (old, new) = (firmware(0, 0), firmware(100, 16));
        let (preamble, elements) = encode(&old, &new);
        assert_eq!(preamble.flags, FLAG_BRANCH | FLAG_POINTER);
        assert_eq!(preamble.base, 0x1_0000);
        assert_eq!(preamble.regions.len(), 1);
        let mut out = Vec::new();
        apply(&old, &preamble, &elements, &mut out).unwrap();
        assert_eq!(out, new);
        // Without relocation every moved call and pointer needs an addition
        let data = encode_data(&preamble, &elements);
        assert!(data.len() < 400, "{} bytes", data.len());
        assert_eq!(decode(&data).unwrap(), (preamble, elements));
    }
}
