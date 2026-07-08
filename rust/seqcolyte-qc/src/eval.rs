//! Label-based detection scoring — a verbatim port of `qc/eval.py`.
//!
//! Predictions come pre-computed from the stream pass (`Acc::preds`, one per pair in read
//! order, `= predict_affected`). Truth is the `affected` column of the labels TSV. We compare
//! the first `n = min(#truth, #preds)` positions.

use anyhow::{anyhow, Result};
use std::fs;

use crate::fmt::round4;
use crate::model::{Confusion, Eval};

pub fn evaluate(preds: &[bool], labels_path: &str) -> Result<Eval> {
    let content = fs::read_to_string(labels_path)?;
    let mut lines = content.lines();
    let header = lines.next().unwrap_or("");
    let ai = header
        .split('\t')
        .position(|h| h == "affected")
        .ok_or_else(|| anyhow!("labels TSV has no 'affected' column"))?;

    let truth: Vec<bool> = lines
        .map(|line| line.split('\t').nth(ai).map_or(false, |c| c == "1"))
        .collect();

    let n = truth.len().min(preds.len());
    let (mut tp, mut fp, mut fn_, mut tn) = (0u64, 0u64, 0u64, 0u64);
    let mut predicted = 0u64;
    let mut true_affected = 0u64;

    for i in 0..n {
        let pred = preds[i];
        let t = truth[i];
        if pred {
            predicted += 1;
        }
        if t {
            true_affected += 1;
        }
        match (pred, t) {
            (true, true) => tp += 1,
            (true, false) => fp += 1,
            (false, true) => fn_ += 1,
            (false, false) => tn += 1,
        }
    }

    let precision = if tp + fp > 0 {
        Some(tp as f64 / (tp + fp) as f64)
    } else {
        None
    };
    let recall = if tp + fn_ > 0 {
        Some(tp as f64 / (tp + fn_) as f64)
    } else {
        None
    };
    // f1 only when both precision and recall are present AND truthy (Python `if (precision and recall)`)
    let f1 = match (precision, recall) {
        (Some(p), Some(r)) if p != 0.0 && r != 0.0 => Some(2.0 * p * r / (p + r)),
        _ => None,
    };

    Ok(Eval {
        n: n as u64,
        predicted_affected: predicted,
        true_affected,
        precision: precision.map(round4),
        recall: recall.map(round4),
        f1: f1.map(round4),
        confusion: Confusion {
            tp,
            fp,
            fn_,
            tn,
        },
    })
}
