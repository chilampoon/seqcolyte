//! The five deterministic checks — a verbatim port of `qc/checks.py`. Every title / threshold /
//! detail / evidence-note string is copied exactly (including the U+2013 en-dash in the
//! r1_length detail and the U+2014 em-dash in the poly-G note). Check order and skip conditions
//! match the Python registry: r1_length, whitelist_hit_rate (skip w/o whitelist), tso_at_r2_start
//! (skip w/o TSO oligo), r2_adapter_readthrough, r2_polyg_tail (skip w/o dark_base).

use crate::fmt::{pct1, round4};
use crate::model::{Evidence, Finding};
use crate::spec::SpecInfo;
use crate::stream::{Acc, OrderedHist};

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

    // ---- 1. r1_length — spec-driven: gate only when R1 is fully fixed-length, else report ----
    {
        let modal = h1.modal();
        let span = if h1.is_empty() {
            "no reads".to_string()
        } else {
            // U+2013 en-dash
            format!("R1 lengths span {}\u{2013}{} bp", h1.min(), h1.max())
        };
        match spec.expected_r1_len {
            Some(exp) => {
                let ok = h1.distinct() == 1 && h1.contains(exp as u32);
                out.push(Finding {
                    check_id: "r1_length".to_string(),
                    title: "R1 length matches the expected fixed structure".to_string(),
                    verdict: (if ok { "pass" } else { "fail" }).to_string(),
                    value: modal as f64,
                    unit: "bp".to_string(),
                    threshold: format!("== {}", exp),
                    affected_fraction: None,
                    severity: if ok { 0.0 } else { 0.9 },
                    evidence: ev(
                        "read_structure.R1",
                        format!("R1 should be exactly {} bp (sum of its fixed-length segments)", exp),
                    ),
                    detail: span,
                });
            }
            None => {
                // R1 carries a variable-length insert — report the distribution, do not gate.
                out.push(Finding {
                    check_id: "r1_length".to_string(),
                    title: "R1 length distribution".to_string(),
                    verdict: "pass".to_string(),
                    value: modal as f64,
                    unit: "bp".to_string(),
                    threshold: "informational".to_string(),
                    affected_fraction: None,
                    severity: 0.0,
                    evidence: ev(
                        "read_structure.R1",
                        "R1 carries a variable-length insert; length is reported, not gated".to_string(),
                    ),
                    detail: span,
                });
            }
        }
    }

    // ---- 1b. anchor presence — spec-driven: each fixed-offset constant should be carried ----
    for (i, a) in spec.anchors.iter().enumerate() {
        let frac = if acc.n > 0 { acc.anchor_hits[i] as f64 / n } else { 0.0 };
        let seq = String::from_utf8_lossy(&a.seq).to_string();
        let verdict = if frac >= 0.8 {
            "pass"
        } else if frac >= 0.5 {
            "warn"
        } else {
            "fail"
        };
        out.push(Finding {
            check_id: format!("anchor_{}_{}", a.read.to_ascii_lowercase(), i),
            title: format!("{} carries the expected {} anchor", a.read, seq),
            verdict: verdict.to_string(),
            value: round4(frac),
            unit: "fraction".to_string(),
            threshold: ">= 0.8".to_string(),
            affected_fraction: Some(round4((1.0 - frac).max(0.0))),
            severity: round4((0.8 - frac).max(0.0)),
            evidence: ev(
                &format!("read_structure.{}", a.read),
                format!("{} should carry the constant {} at position {}", a.read, seq, a.offset + 1),
            ),
            detail: format!(
                "{} of {} carry {} at position {} (the rest are off-target / mispriming)",
                pct1(frac),
                a.read,
                seq,
                a.offset + 1
            ),
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

    // ---- 4. adapter read-through — spec-driven: the spec's actual 3' adapter, both mates ----
    if !spec.adapters.is_empty() {
        let adapter_str = String::from_utf8_lossy(&spec.adapters[0]).to_string();
        for (id, name, hits) in [("r1", "R1", acc.r1_adapter), ("r2", "R2", acc.r2_adapter)] {
            let frac = if acc.n > 0 { hits as f64 / n } else { 0.0 };
            out.push(Finding {
                check_id: format!("{}_adapter_readthrough", id),
                title: format!("{} read-through into the 3' adapter", name),
                verdict: tri(frac, 0.02, 0.10).to_string(),
                value: round4(frac),
                unit: "fraction".to_string(),
                threshold: "< 0.02".to_string(),
                affected_fraction: Some(round4(frac)),
                severity: round4((frac * 2.0).min(1.0)),
                evidence: ev(
                    "oligos[role=read_through_adapter]",
                    format!(
                        "the {} adapter stem in {} means the insert was shorter than the read length",
                        adapter_str, name
                    ),
                ),
                detail: format!("{} of {} contain the adapter stem {}", pct1(frac), name, adapter_str),
            });
        }
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
