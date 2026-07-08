//! `seqcolyte-qc` — parity-preserving Rust port of the Seqcolyte QC compute core
//! (`qc/profile.py` + `qc/checks.py` + `qc/eval.py`). Reads a FASTQ pair once and prints
//! `{ "profile": {…}, "findings": […], "eval": {…}|null }` to stdout.

mod checks;
mod cli;
mod eval;
mod fmt;
mod model;
mod seqops;
mod spec;
mod stream;
mod whitelist;

use anyhow::{bail, Context, Result};
use clap::Parser;
use memchr::memmem::Finder;

use crate::cli::Args;
use crate::model::{LenStats, Output, Profile};

const ADAPTER_STEM: &[u8] = b"AGATCGGAAGAGC";

fn main() -> Result<()> {
    let args = Args::parse();

    let spec_text = std::fs::read_to_string(&args.spec)
        .with_context(|| format!("reading spec {}", args.spec))?;
    let spec_json: serde_json::Value =
        serde_json::from_str(&spec_text).with_context(|| format!("parsing spec {}", args.spec))?;
    let spec = spec::parse_spec(&spec_json)?;

    // Whitelist (optional) — load once, encoded to u64.
    let wl = match &args.whitelist {
        Some(p) => Some(
            whitelist::load(p, spec.cb_len).with_context(|| format!("loading whitelist {}", p))?,
        ),
        None => None,
    };

    // The Python eval calls spec.oligo_sequence(TSO), which raises if the TSO is absent.
    // Mirror that: labels without a TSO oligo is an error (rather than silently scoring
    // TSO-less predictions).
    if args.labels.is_some() && spec.tso.is_none() {
        bail!("labels given but spec has no TSO oligo (oligo_template_switching_oligo_tso)");
    }

    let ctx = stream::Ctx {
        tso: spec.tso.as_deref().map(str::as_bytes),
        dark: spec.dark_base,
        stem: Finder::new(ADAPTER_STEM),
        wl: wl.as_ref(),
        cb_start: spec.cb_start,
        cb_len: spec.cb_len,
        collect_preds: args.labels.is_some(),
    };

    let res = stream::stream(&args.r1, &args.r2, &ctx, args.max_reads)
        .with_context(|| "streaming FASTQ pair")?;

    let profile = Profile {
        n_pairs: res.acc.n,
        r1_len: LenStats {
            min: res.h1.min(),
            max: res.h1.max(),
            modal: res.h1.modal(),
        },
        r2_len: LenStats {
            min: res.h2.min(),
            max: res.h2.max(),
            modal: res.h2.modal(),
        },
    };

    let findings = checks::build_findings(&spec, &res.acc, &res.h1, wl.is_some());

    let eval = match &args.labels {
        Some(p) => Some(eval::evaluate(&res.acc.preds, p).with_context(|| format!("eval vs {}", p))?),
        None => None,
    };

    let output = Output {
        profile,
        findings,
        eval,
    };
    serde_json::to_writer(std::io::stdout(), &output)?;
    println!();
    Ok(())
}
