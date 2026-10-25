//! Candidate COPY runs (same approach as the run finding in `encoder_shortest_path`)
//!
//! A run is (new start, new end, diagonal), where the diagonal is the offset in the
//! original file minus the offset in the new file.

use std::collections::{HashMap, HashSet};

pub type Run = (i64, i64, i64);
/// (new start, new end, diagonal before, diagonal after) of a WRITE region
pub type Gap = (i64, i64, i64, i64);

/// Pack every k byte substring into an integer
fn kgrams(a: &[u8], k: usize) -> Vec<u64> {
    (0..=a.len() - k)
        .map(|i| {
            a[i..i + k]
                .iter()
                .enumerate()
                .fold(0u64, |acc, (t, &b)| acc | (b as u64) << (8 * t))
        })
        .collect()
}

/// Start and end indices of runs of `true` values
pub fn true_runs(mask: &[bool]) -> Vec<(usize, usize)> {
    let mut runs = Vec::new();
    let mut offset = 0;
    for chunk in mask.chunk_by(|a, b| a == b) {
        if chunk[0] {
            runs.push((offset, offset + chunk.len()));
        }
        offset += chunk.len();
    }
    runs
}

/// Runs of at least `min_len` where `new[start..end]` matches the original at offset `diag`
pub fn diagonal_runs(old: &[u8], new: &[u8], diag: i64, start: i64, end: i64, min_len: i64) -> Vec<Run> {
    let start = start.max(0).max(-diag);
    let end = end.min(new.len() as i64).min(old.len() as i64 - diag);
    if end - start < min_len {
        return Vec::new();
    }
    let n = &new[start as usize..end as usize];
    let o = &old[(start + diag) as usize..(end + diag) as usize];
    true_runs(&n.iter().zip(o).map(|(a, b)| a == b).collect::<Vec<_>>())
        .into_iter()
        .filter(|(s, e)| (e - s) as i64 >= min_len)
        .map(|(s, e)| (start + s as i64, start + e as i64, diag))
        .collect()
}

/// Diagonals of k byte matches between the files, clustered along each diagonal.
/// Returns (diagonal, first new offset, last new offset + k) of each cluster.
fn seed_clusters(
    old: &[u8],
    new: &[u8],
    k: usize,
    max_count: usize,
    span: i64,
    positions: Option<&[usize]>,
) -> Vec<(i64, i64, i64)> {
    if old.len() < k || new.len() < k {
        return Vec::new();
    }
    let old_keys = kgrams(old, k);
    let mut order: Vec<usize> = (0..old_keys.len()).collect();
    // Stable, equal keys remain in ascending offset order
    order.sort_by_key(|&i| old_keys[i]);
    let sorted_keys: Vec<u64> = order.iter().map(|&i| old_keys[i]).collect();
    let new_keys = kgrams(new, k);

    let mut seeds: Vec<(i64, i64)> = Vec::new();
    let mut add_seeds = |pos: usize| {
        let key = new_keys[pos];
        let first = sorted_keys.partition_point(|&x| x < key);
        let last = sorted_keys.partition_point(|&x| x <= key);
        // Substrings that are too common in the original carry little information
        if last > first && last - first <= max_count {
            for &o in &order[first..last] {
                seeds.push((o as i64 - pos as i64, pos as i64));
            }
        }
    };
    match positions {
        Some(positions) => positions.iter().for_each(|&p| add_seeds(p)),
        None => (0..new_keys.len()).for_each(&mut add_seeds),
    }
    if seeds.is_empty() {
        return Vec::new();
    }
    seeds.sort_unstable();

    let mut clusters = Vec::new();
    let (mut diag, mut first, mut last) = (seeds[0].0, seeds[0].1, seeds[0].1);
    for &(d, p) in &seeds[1..] {
        if d != diag || p - last > span {
            clusters.push((diag, first, last + k as i64));
            diag = d;
            first = p;
        }
        last = p;
    }
    clusters.push((diag, first, last + k as i64));
    clusters
}

fn count_matching(old: &[u8], new: &[u8], diag: i64, start: i64, end: i64) -> usize {
    new[start as usize..end as usize]
        .iter()
        .zip(&old[(start + diag) as usize..(end + diag) as usize])
        .filter(|(a, b)| a == b)
        .count()
}

/// Value, start and length of runs of at least 16 of a single repeated byte
fn value_runs(a: &[u8]) -> Vec<(u8, i64, i64)> {
    if a.len() < 2 {
        return Vec::new();
    }
    true_runs(&a.windows(2).map(|w| w[0] == w[1]).collect::<Vec<_>>())
        .into_iter()
        .filter(|(s, e)| e - s >= 15)
        .map(|(s, e)| (a[s], s as i64, (e - s + 1) as i64))
        .collect()
}

/// Exact matching runs along diagonals that relate the two files
pub fn candidate_runs(old: &[u8], new: &[u8]) -> HashSet<Run> {
    let mut windows: Vec<(i64, i64, i64, i64)> = Vec::new();
    for (diag, mut start, mut end) in seed_clusters(old, new, 6, 8, 256, None) {
        let lo = 0.max(-diag);
        let hi = (new.len() as i64).min(old.len() as i64 - diag);
        if end - start < 48 {
            windows.push((diag, start - 8, end + 8, 6));
            continue;
        }
        // Regions of firmware that have moved typically still match outside of the
        // relocated pointers. Follow the diagonal while it continues to mostly match.
        while start > lo {
            let s = lo.max(start - 128);
            if (count_matching(old, new, diag, s, start) as f64) < 0.3 * (start - s) as f64 {
                start = lo.max(start - 16);
                break;
            }
            start = s;
        }
        while end < hi {
            let e = hi.min(end + 128);
            if (count_matching(old, new, diag, end, e) as f64) < 0.3 * (e - end) as f64 {
                end = hi.min(end + 16);
                break;
            }
            end = e;
        }
        windows.push((diag, start, end, 2));
    }

    // Long runs of a single value (padding) are too common to seed from k byte matches.
    // Source them from the longest run of the same value in the original.
    let mut longest: HashMap<u8, (i64, i64)> = HashMap::new();
    for (value, start, length) in value_runs(old) {
        if length > longest.get(&value).map_or(0, |l| l.1) {
            longest.insert(value, (start, length));
        }
    }
    for (value, mut start, mut length) in value_runs(new) {
        let Some(&(old_start, old_length)) = longest.get(&value) else {
            continue;
        };
        // Longer runs than exist in the original are constructed from repeated copies
        for _ in 0..1024 {
            let chunk = length.min(old_length);
            windows.push((old_start - start, start, start + chunk, 2));
            start += chunk;
            length -= chunk;
            if length < 16 {
                break;
            }
        }
    }

    // Merge overlapping windows on the same diagonal so that runs are not split
    windows.sort_unstable();
    let mut merged: Vec<(i64, i64, i64, i64)> = Vec::new();
    for (diag, start, end, min_len) in windows {
        match merged.last_mut() {
            Some(m) if m.0 == diag && start <= m.2 => {
                m.2 = m.2.max(end);
                m.3 = m.3.min(min_len);
            }
            _ => merged.push((diag, start, end, min_len)),
        }
    }

    let mut runs = HashSet::new();
    for (diag, start, end, min_len) in merged {
        runs.extend(diagonal_runs(old, new, diag, start, end, min_len));
    }
    runs
}

/// Short matching runs inside the WRITE regions of an encoding
pub fn gap_runs(old: &[u8], new: &[u8], gaps: &[Gap]) -> HashSet<Run> {
    let mut runs = HashSet::new();
    if gaps.is_empty() {
        return runs;
    }
    let mut positions = Vec::new();
    for &(start, end, diag_before, diag_after) in gaps {
        // Continuing on a neighbouring diagonal requires no address change
        runs.extend(diagonal_runs(old, new, diag_before, start, end, 2));
        if diag_after != diag_before {
            runs.extend(diagonal_runs(old, new, diag_after, start, end, 2));
        }
        positions.extend(start as usize..start.max(end - 3) as usize);
    }

    // Other diagonals with short matches, which tend to align similar code
    for (diag, start, end) in seed_clusters(old, new, 4, 4, 64, Some(&positions)) {
        let found = diagonal_runs(old, new, diag, start - 64, end + 64, 2);
        if found.iter().map(|(s, e, _)| e - s).sum::<i64>() >= 4 {
            runs.extend(found);
        }
    }
    runs
}
