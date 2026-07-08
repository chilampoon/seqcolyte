//! Serde output structs. Field order mirrors the Python dicts for readability; the parity
//! test compares with `sort_keys=True`, so wire order is not load-bearing.
//!
//! Every numeric field is a plain scalar: in `qc/checks.py` all `value`/`severity` values
//! are floats (`float(modal)`, `round(frac, 4)`, `0.0/0.9`, `max(0.0, …)`, `min(1.0, …)`),
//! so there is no int-vs-float ambiguity to model. serde_json serializes f64 with the same
//! shortest round-trip representation CPython's `repr`/`json` use.

use serde::Serialize;

#[derive(Serialize)]
pub struct Evidence {
    pub spec_ref: String,
    pub note: String,
}

#[derive(Serialize)]
pub struct Finding {
    pub check_id: String,
    pub title: String,
    pub verdict: String,
    pub value: f64,
    pub unit: String,
    pub threshold: String,
    pub affected_fraction: Option<f64>,
    pub severity: f64,
    pub evidence: Vec<Evidence>,
    pub detail: String,
}

#[derive(Serialize)]
pub struct LenStats {
    pub min: u32,
    pub max: u32,
    pub modal: u32,
}

#[derive(Serialize)]
pub struct Profile {
    pub n_pairs: u64,
    pub r1_len: LenStats,
    pub r2_len: LenStats,
}

#[derive(Serialize)]
pub struct Confusion {
    pub tp: u64,
    pub fp: u64,
    #[serde(rename = "fn")]
    pub fn_: u64,
    pub tn: u64,
}

#[derive(Serialize)]
pub struct Eval {
    pub n: u64,
    pub predicted_affected: u64,
    pub true_affected: u64,
    pub precision: Option<f64>,
    pub recall: Option<f64>,
    pub f1: Option<f64>,
    pub confusion: Confusion,
}

#[derive(Serialize)]
pub struct Output {
    pub profile: Profile,
    pub findings: Vec<Finding>,
    pub eval: Option<Eval>,
}
