//! The five deterministic checks — a verbatim port of `qc/checks.py`. Every title / threshold /
//! detail / evidence-note string is copied exactly (including the U+2013 en-dash in the
//! r1_length detail and the U+2014 em-dash in the poly-G note). Check order and skip conditions
//! match the Python registry: r1_length, whitelist_hit_rate (skip w/o whitelist), tso_at_r2_start
//! (skip w/o TSO oligo), r2_adapter_readthrough, r2_polyg_tail (skip w/o dark_base).

use crate::fmt::{pct1, round4};
use crate::model::{Evidence, Finding};
use crate::spec::SpecInfo;
use crate::stream::{Acc, OrderedHist};

const ADAPTER_STEM: &str = "AGATCGGAAGAGC";

/// `qc.checks._tri`
fn tri(v: f64, warn: f64, fail: f64) -> &'static str {
    if v >= fail {
        "fail"
    } else if v >= warn {
        "warn"
    } else {
        "pass"
    }
}

fn ev(spec_ref: &str, note: String) -> Vec<Evidence> {
    vec![Evidence {
        spec_ref: spec_ref.to_string(),
        note,
    }]
}

pub fn build_findings(spec: &SpecInfo, acc: &Acc, h1: &OrderedHist, have_whitelist: bool) -> Vec<Finding> {
    let mut out: Vec<Finding> = Vec::new();
    let n = acc.n as f64;

    // ---- 1. r1_length ----
    {
        let expected = spec.r1_cycles;
        // ok = {distinct R1 lengths} == {expected}
        let ok = h1.distinct() == 1 && h1.contains(expected as u32);
        let modal = h1.modal();
        let detail = if h1.is_empty() {
            "no reads".to_string()
        } else {
            // U+2013 en-dash, verbatim from Python f"...span {min}–{max} bp"
            format!("R1 lengths span {}\u{2013}{} bp", h1.min(), h1.max())
        };
        out.push(Finding {
            check_id: "r1_length".to_string(),
            title: "R1 length matches barcode + UMI".to_string(),
            verdict: (if ok { "pass" } else { "fail" }).to_string(),
            value: modal as f64,
            unit: "bp".to_string(),
            threshold: format!("== {}", expected),
            affected_fraction: None,
            severity: if ok { 0.0 } else { 0.9 },
            evidence: ev(
                "read_structure.R1",
                format!("R1 should be exactly {} bp (16 bp cell barcode + 12 bp UMI)", expected),
            ),
            detail,
        });
    }

    // ---- 2. whitelist_hit_rate (skip without a whitelist) ----
    if have_whitelist {
        let rate = if acc.n > 0 { acc.wl as f64 / n } else { 0.0 };
        let verdict = if rate >= 0.85 {
            "pass"
        } else if rate >= 0.5 {
            "warn"
        } else {
            "fail"
        };
        out.push(Finding {
            check_id: "whitelist_hit_rate".to_string(),
            title: "Cell barcodes on the 10x whitelist".to_string(),
            verdict: verdict.to_string(),
            value: round4(rate),
            unit: "fraction".to_string(),
            threshold: ">= 0.85".to_string(),
            affected_fraction: None,
            severity: round4((0.85 - rate).max(0.0)),
            evidence: ev(
                "whitelists.cell_barcode_3M_feb2018",
                "R1[0:16] should match the 3M-february-2018 gel-bead barcode whitelist".to_string(),
            ),
            detail: format!("{} of cell barcodes are on the whitelist", pct1(rate)),
        });
    }

    // ---- 3. tso_at_r2_start (skip without the TSO oligo) ----
    if spec.tso.is_some() {
        let frac = if acc.n > 0 { acc.tso as f64 / n } else { 0.0 };
        out.push(Finding {
            check_id: "tso_at_r2_start".to_string(),
            title: "R2 reads beginning with the TSO (adapter-dimer / short insert)".to_string(),
            verdict: tri(frac, 0.05, 0.15).to_string(),
            value: round4(frac),
            unit: "fraction".to_string(),
            threshold: "< 0.05".to_string(),
            affected_fraction: Some(frac),
            severity: round4((frac * 2.0).min(1.0)),
            evidence: ev(
                "read_structure.R2.readthrough_chain[tso_5prime]",
                "R2 should start with cDNA; a leading TSO is the hallmark of empty/short-insert products".to_string(),
            ),
            detail: format!("{} of R2 start with the TSO", pct1(frac)),
        });
    }

    // ---- 4. r2_adapter_readthrough (always) ----
    {
        let frac = if acc.n > 0 { acc.adapter as f64 / n } else { 0.0 };
        out.push(Finding {
            check_id: "r2_adapter_readthrough".to_string(),
            title: "R2 read-through into the Illumina adapter".to_string(),
            verdict: tri(frac, 0.02, 0.10).to_string(),
            value: round4(frac),
            unit: "fraction".to_string(),
            threshold: "< 0.02".to_string(),
            affected_fraction: Some(frac),
            severity: round4((frac * 2.0).min(1.0)),
            evidence: ev(
                "oligos.oligo_r1_readinto_adapter",
                format!("the {} adapter stem in R2 means the insert was shorter than the read length", ADAPTER_STEM),
            ),
            detail: format!("{} of R2 contain the adapter stem {}", pct1(frac), ADAPTER_STEM),
        });
    }

    // ---- 5. r2_polyg_tail (skip without a dark_base) ----
    if let Some(base) = spec.dark_base {
        let base = base as char;
        let frac = if acc.n > 0 { acc.polyg as f64 / n } else { 0.0 };
        out.push(Finding {
            check_id: "r2_polyg_tail".to_string(),
            title: format!("R2 with a poly-{} no-signal tail", base),
            verdict: tri(frac, 0.01, 0.05).to_string(),
            value: round4(frac),
            unit: "fraction".to_string(),
            threshold: "< 0.01".to_string(),
            affected_fraction: Some(frac),
            severity: round4((frac * 3.0).min(1.0)),
            evidence: ev(
                "platform_params.dark_base",
                // U+2014 em-dash, verbatim
                format!("a poly-{} 3' tail on two-color instruments is 'no signal' \u{2014} typical of empty/short fragments", base),
            ),
            detail: format!("{} of R2 have a poly-{} tail", pct1(frac), base),
        });
    }

    out
}
