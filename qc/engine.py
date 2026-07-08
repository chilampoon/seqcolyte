"""QC orchestrator: profile the FASTQ, run the applicable checks, rank + diagnose (LLM or a
deterministic fallback), and (given labels) score the detection. Returns one report dict.

The per-read compute (profile + checks + eval) runs in one of two interchangeable engines:
``"python"`` (the in-repo pure-Python path) or ``"rust"`` (the ``seqcolyte-qc`` binary, a
parity-preserving port — see ``qc/rust_engine.py``). Both produce identical numbers; ``"rust"``
transparently falls back to ``"python"`` when the binary hasn't been built."""

from __future__ import annotations

import sys

from seqcolyte.spec.loader import load_spec
from sim.sanity import load_whitelist
from qc import QC_VERSION
from qc.eval import evaluate
from qc.model import Finding
from qc.profile import profile as build_profile
from qc.registry import registered_checks

__all__ = ["run_qc"]


class _ProfileView:
    """Adapts a Rust-produced profile summary dict to the ``.summary()`` the LLM planner calls."""

    def __init__(self, summary: dict):
        self._summary = summary

    def summary(self) -> dict:
        return self._summary


def _compute_python(spec, r1, r2, *, whitelist, labels, max_reads):
    """Pure-Python compute path.

    Returns ``(profile_for_planner, findings, profile_summary, finding_dicts, eval)`` — the same
    tuple shape as :func:`_compute_rust`, so :func:`run_qc` is engine-agnostic below.
    """
    prof = build_profile(r1, r2, max_reads=max_reads)
    resources = {"whitelist": load_whitelist(whitelist) if whitelist else None}
    findings = []
    for _check_id, fn in registered_checks():
        finding = fn(prof, spec, resources)
        if finding is not None:
            findings.append(finding)
    eval_result = evaluate(prof, spec, labels) if labels else None
    return prof, findings, prof.summary(), [f.to_dict() for f in findings], eval_result


def _compute_rust(spec_path, r1, r2, *, whitelist, labels, max_reads):
    """Rust compute path (the ``seqcolyte-qc`` binary).

    The report keeps the binary's **raw** profile/findings/eval JSON (so nothing is re-rounded);
    the reconstructed ``Finding`` objects are used only to feed ranking + the ``overall`` verdict.
    """
    from qc.rust_engine import run_rust_qc
    data = run_rust_qc(spec_path, r1, r2, whitelist=whitelist, labels=labels, max_reads=max_reads)
    prof_summary = data["profile"]
    finding_dicts = data["findings"]
    eval_result = data.get("eval")
    findings = [Finding(**d) for d in finding_dicts]
    return _ProfileView(prof_summary), findings, prof_summary, finding_dicts, eval_result


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
           use_llm: bool = True, model: str = "claude-opus-4-8", max_reads: int | None = None,
           engine: str = "rust") -> dict:
    spec = load_spec(spec_path)

    if engine == "rust":
        try:
            prof, findings, prof_summary, finding_dicts, eval_result = _compute_rust(
                spec_path, r1, r2, whitelist=whitelist, labels=labels, max_reads=max_reads)
        except Exception as exc:  # binary missing/failed — fall back to the identical Python path
            print(f"[qc] rust engine unavailable ({str(exc)[:160]}); using python", file=sys.stderr)
            engine = "python"

    if engine == "python":
        prof, findings, prof_summary, finding_dicts, eval_result = _compute_python(
            spec, r1, r2, whitelist=whitelist, labels=labels, max_reads=max_reads)

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
        "profile": prof_summary,
        "findings": finding_dicts,
        "plan": plan,
        "overall": "fail" if any(f.verdict == "fail" for f in findings) else
                   "warn" if any(f.verdict == "warn" for f in findings) else "pass",
    }
    if labels:
        report["eval"] = eval_result
    return report
