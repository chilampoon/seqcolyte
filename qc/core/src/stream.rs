//! One-pass streaming compute: read the FASTQ pair in lockstep, accumulate length histograms
//! sequentially, and run the four per-read byte scans over rayon-parallel batches.
//!
//! Nothing is collected into a full in-memory read list (unlike `qc/profile.py`); at most one
//! ~50k-pair batch of sequence bytes is resident at a time. `max_reads` caps *before* pulling
//! the next pair, matching Python abandoning its `iter_pairs` generator at `i >= max_reads`
//! (so a truncated run never raises a pairing error).

use anyhow::{bail, Result};
use memchr::memmem::Finder;
use needletail::parse_fastx_file;
use rayon::prelude::*;
use rustc_hash::{FxHashMap, FxHashSet};

use crate::seqops::{has_homopolymer_tail, startswith_fuzzy};
use crate::whitelist::hit as wl_hit;

const BATCH: usize = 50_000;

/// Immutable per-run context shared across rayon workers.
pub struct Ctx<'a> {
    pub tso: Option<&'a [u8]>,
    pub dark: Option<u8>,
    pub stem: Finder<'a>,
    pub wl: Option<&'a FxHashSet<u64>>,
    pub cb_start: usize,
    pub cb_len: usize,
    pub collect_preds: bool,
}

struct Flags {
    tso: bool,
    adapter: bool,
    polyg: bool,
    wl: bool,
}

#[derive(Default)]
pub struct Acc {
    pub n: u64,
    pub tso: u64,
    pub adapter: u64,
    pub polyg: u64,
    pub wl: u64,
    /// `predict_affected` per pair, in read order — only populated when `collect_preds`.
    pub preds: Vec<bool>,
}

/// Insertion-ordered length histogram. `modal()` reproduces
/// `Counter(lens).most_common(1)[0][0]`: highest count, first-encountered on ties.
#[derive(Default)]
pub struct OrderedHist {
    counts: FxHashMap<u32, u64>,
    order: Vec<u32>,
}

impl OrderedHist {
    fn add(&mut self, l: u32) {
        match self.counts.get_mut(&l) {
            Some(c) => *c += 1,
            None => {
                self.counts.insert(l, 1);
                self.order.push(l);
            }
        }
    }
    pub fn min(&self) -> u32 {
        self.order.iter().copied().min().unwrap_or(0)
    }
    pub fn max(&self) -> u32 {
        self.order.iter().copied().max().unwrap_or(0)
    }
    pub fn is_empty(&self) -> bool {
        self.order.is_empty()
    }
    pub fn distinct(&self) -> usize {
        self.order.len()
    }
    pub fn contains(&self, l: u32) -> bool {
        self.counts.contains_key(&l)
    }
    pub fn modal(&self) -> u32 {
        let mut best: Option<(u32, u64)> = None;
        for &l in &self.order {
            let c = self.counts[&l];
            match best {
                Some((_, bc)) if c <= bc => {} // keep the earlier element on ties
                _ => best = Some((l, c)),
            }
        }
        best.map(|(l, _)| l).unwrap_or(0)
    }
}

pub struct StreamResult {
    pub acc: Acc,
    pub h1: OrderedHist,
    pub h2: OrderedHist,
}

pub fn stream(
    r1_path: &str,
    r2_path: &str,
    ctx: &Ctx,
    max_reads: Option<u64>,
) -> Result<StreamResult> {
    let mut r1 = parse_fastx_file(r1_path)?;
    let mut r2 = parse_fastx_file(r2_path)?;
    let mut acc = Acc::default();
    let mut h1 = OrderedHist::default();
    let mut h2 = OrderedHist::default();
    let mut batch: Vec<(Box<[u8]>, Box<[u8]>)> = Vec::with_capacity(BATCH);

    loop {
        if let Some(cap) = max_reads {
            if acc.n >= cap {
                break;
            }
        }
        match (r1.next(), r2.next()) {
            (Some(a), Some(b)) => {
                let a = a?;
                let b = b?;
                let s1 = a.seq();
                let s2 = b.seq();
                h1.add(s1.len() as u32);
                h2.add(s2.len() as u32);
                batch.push((
                    s1.as_ref().to_vec().into_boxed_slice(),
                    s2.as_ref().to_vec().into_boxed_slice(),
                ));
                acc.n += 1;
                if batch.len() == BATCH {
                    flush(&batch, ctx, &mut acc);
                    batch.clear();
                }
            }
            (None, None) => break,
            (Some(_), None) => bail!("R1 has more reads than R2 — files are not paired"),
            (None, Some(_)) => bail!("R2 has more reads than R1 — files are not paired"),
        }
    }
    flush(&batch, ctx, &mut acc);
    Ok(StreamResult { acc, h1, h2 })
}

fn flush(batch: &[(Box<[u8]>, Box<[u8]>)], ctx: &Ctx, acc: &mut Acc) {
    if batch.is_empty() {
        return;
    }
    // Parallel map preserves order; the fold below is order-stable so preds stay in read order.
    let flags: Vec<Flags> = batch
        .par_iter()
        .map(|(r1, r2)| Flags {
            tso: ctx.tso.map_or(false, |t| startswith_fuzzy(r2, t, 2)),
            adapter: ctx.stem.find(r2).is_some(),
            polyg: ctx.dark.map_or(false, |b| has_homopolymer_tail(r2, b)),
            wl: ctx
                .wl
                .map_or(false, |s| wl_hit(r1, ctx.cb_start, ctx.cb_len, s)),
        })
        .collect();

    for f in &flags {
        acc.tso += f.tso as u64;
        acc.adapter += f.adapter as u64;
        acc.polyg += f.polyg as u64;
        acc.wl += f.wl as u64;
        if ctx.collect_preds {
            // predict_affected(r2, tso, dark) = tso_match OR (dark AND polyg_tail)
            acc.preds.push(f.tso || (ctx.dark.is_some() && f.polyg));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn modal_tie_breaks_to_first_seen() {
        let mut h = OrderedHist::default();
        // 91 seen first, then 90; both end with count 2 -> modal is 91 (first seen).
        for l in [91u32, 90, 91, 90] {
            h.add(l);
        }
        assert_eq!(h.modal(), 91);
        assert_eq!(h.min(), 90);
        assert_eq!(h.max(), 91);
        assert_eq!(h.distinct(), 2);
    }

    #[test]
    fn empty_hist() {
        let h = OrderedHist::default();
        assert!(h.is_empty());
        assert_eq!(h.modal(), 0);
        assert_eq!(h.min(), 0);
        assert_eq!(h.max(), 0);
    }
}
