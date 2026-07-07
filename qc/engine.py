"""QC orchestrator: profile the FASTQ, run the applicable checks, rank + diagnose (LLM or a
deterministic fallback), and (given labels) score the detection. Returns one report dict."""

from __future__ import annotations

from seqcolyte.spec.loader import load_spec
from sim.sanity import load_whitelist
from qc import QC_VERSION
from qc.eval import evaluate
from qc.profile import profile as build_profile
from qc.registry import registered_checks

__all__ = ["run_qc"]


def _severity_label(s: float) -> str:
    return "high" if s >= 0.5 else "medium" if s >= 0.2 else "low" if s > 0 else "none"


def _deterministic_rank(findings) -> dict:
    ordered = sorted(findings, key=lambda f: f.severity, reverse=True)
    ranked = [{"check_id": f.check_id, "severity": _severity_label(f.severity), "why": f.detail} for f in ordered]
    fails = [f for f in ordered if f.verdict == "fail"]
    if fails:
        root = fails[0].title
        diagnosis = "; ".join(f"{f.title.lower()} ({f.detail})" for f in fails[:2]) + "."
    else:
        root = "no failure detected"
        diagnosis = "All checks passed — the reads are consistent with the expected library structure."
    return {"ranked": ranked, "root_cause": root, "diagnosis": diagnosis, "method": "deterministic"}


def run_qc(spec_path: str, r1: str, r2: str, *, whitelist: str | None = None, labels: str | None = None,
           use_llm: bool = True, model: str = "claude-opus-4-8", max_reads: int | None = None) -> dict:
    spec = load_spec(spec_path)
    prof = build_profile(r1, r2, max_reads=max_reads)
    resources = {"whitelist": load_whitelist(whitelist) if whitelist else None}

    findings = []
    for _check_id, fn in registered_checks():
        finding = fn(prof, spec, resources)
        if finding is not None:
            findings.append(finding)

    if use_llm:
        try:
            from qc.planner import rank_with_llm
            plan = rank_with_llm(spec, prof, findings, model=model)
            plan["method"] = "llm"
        except Exception as exc:  # LLM unavailable/errored — fall back deterministically
            plan = _deterministic_rank(findings)
            plan["llm_error"] = str(exc)[:200]
    else:
        plan = _deterministic_rank(findings)

    report = {
        "qc_version": QC_VERSION, "spec_id": spec.spec_id, "assay": spec.assay, "platform": spec.platform,
        "profile": prof.summary(),
        "findings": [f.to_dict() for f in findings],
        "plan": plan,
        "overall": "fail" if any(f.verdict == "fail" for f in findings) else
                   "warn" if any(f.verdict == "warn" for f in findings) else "pass",
    }
    if labels:
        report["eval"] = evaluate(prof, spec, labels)
    return report
