"""QC orchestrator: run the ``qc-core`` Rust compute core (FASTQ profile + the deterministic
checks + the label eval), then rank + diagnose the findings (Claude, or a deterministic fallback),
and assemble one report dict.

The per-read compute lives entirely in the Rust binary (`qc/core`, invoked via
``qc/rust_engine.py``); Python only orchestrates: load the spec for metadata, shell out, rank the
findings, and score. Build the binary with ``make rust`` — without it, QC raises
``RustEngineUnavailable``.
"""

from __future__ import annotations

from seqcolyte.spec.loader import load_spec
from qc import QC_VERSION
from qc.rust_engine import run_rust_qc

__all__ = ["run_qc"]


def _severity_label(s: float) -> str:
    return "high" if s >= 0.5 else "medium" if s >= 0.2 else "low" if s > 0 else "none"


def _deterministic_rank(findings: list[dict]) -> dict:
    ordered = sorted(findings, key=lambda f: f["severity"], reverse=True)
    ranked = [{"check_id": f["check_id"], "severity": _severity_label(f["severity"]), "why": f["detail"]}
              for f in ordered]
    fails = [f for f in ordered if f["verdict"] == "fail"]
    if fails:
        root = fails[0]["title"]
        diagnosis = "; ".join(f'{f["title"].lower()} ({f["detail"]})' for f in fails[:2]) + "."
    else:
        root = "no failure detected"
        diagnosis = "All checks passed — the reads are consistent with the expected library structure."
    return {"ranked": ranked, "root_cause": root, "diagnosis": diagnosis, "method": "deterministic"}


def run_qc(spec_path: str, r1: str, r2: str, *, whitelist: str | None = None, labels: str | None = None,
           use_llm: bool = True, model: str = "claude-opus-4-8", max_reads: int | None = None) -> dict:
    spec = load_spec(spec_path)
    data = run_rust_qc(spec_path, r1, r2, whitelist=whitelist, labels=labels, max_reads=max_reads)
    profile = data["profile"]
    findings = data["findings"]
    eval_result = data.get("eval")

    if use_llm:
        try:
            from qc.planner import rank_with_llm
            plan = rank_with_llm(spec, profile, findings, model=model)
            plan["method"] = "llm"
        except Exception as exc:  # LLM unavailable/errored — fall back deterministically
            plan = _deterministic_rank(findings)
            plan["llm_error"] = str(exc)[:200]
    else:
        plan = _deterministic_rank(findings)

    report = {
        "qc_version": QC_VERSION, "spec_id": spec.spec_id, "assay": spec.assay, "platform": spec.platform,
        "profile": profile,
        "findings": findings,
        "plan": plan,
        "overall": "fail" if any(f["verdict"] == "fail" for f in findings) else
                   "warn" if any(f["verdict"] == "warn" for f in findings) else "pass",
    }
    if labels:
        report["eval"] = eval_result
    return report
