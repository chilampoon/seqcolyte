"""Orchestrate a deterministic diagnosis: evidence + typed target -> signals -> ranked hypotheses."""

from __future__ import annotations

from typing import Any

from qc.catalog.adapters import CHECK_ADAPTERS
from qc.catalog.loader import Catalog, load_catalog
from qc.diagnose.model import Diagnosis
from qc.diagnose.profile import Profile, load_profile
from qc.diagnose.rank import rank_hypotheses, rank_issues
from qc.diagnose.signals import evaluate
from qc.manifest.model import InputManifest, target_attainment

__all__ = ["reduce_observations", "diagnose", "diagnose_from_reports"]

_CHECK_METRIC = {a.check_id: a.metrics[0] for a in CHECK_ADAPTERS if a.metrics}


def reduce_observations(reports: list[Any]) -> tuple[dict[str, float], dict[str, str], list[str]]:
    """Collapse evidence observations to one representative value per canonical metric.

    The most-confident observation wins; genuinely different values for the same metric are kept as a
    warning (never silently overwritten). Returns (values, source_scopes, warnings).
    """
    grouped: dict[str, list[Any]] = {}
    for rep in reports:
        for obs in getattr(rep, "observations", []):
            if obs.metric_id and obs.value is not None:
                grouped.setdefault(obs.metric_id, []).append(obs)

    values: dict[str, float] = {}
    scopes: dict[str, str] = {}
    warnings: list[str] = []
    for mid, obs_list in grouped.items():
        distinct = sorted({round(o.value, 6) for o in obs_list})
        best = max(obs_list, key=lambda o: (o.confidence, o.value))
        values[mid] = best.value
        scopes[mid] = best.source_scope
        if len(distinct) > 1:
            warnings.append(f"conflicting observations for {mid}: {distinct} (using {best.value:g})")
    return values, scopes, warnings


def diagnose(
    values: dict[str, float],
    *,
    scopes: dict[str, str] | None = None,
    manifest: InputManifest | None = None,
    qc_findings: list[dict[str, Any]] | None = None,
    catalog: Catalog | None = None,
    profile: Profile | None = None,
    title: str | None = None,
    extra_warnings: list[str] | None = None,
) -> Diagnosis:
    cat = catalog if catalog is not None else load_catalog()
    prof = profile if profile is not None else load_profile()
    values = dict(values)
    scopes = dict(scopes or {})
    warnings = list(extra_warnings or [])

    # fold in current QC findings via the candidate-check adapters (evidence values win over findings)
    for f in qc_findings or []:
        metric = _CHECK_METRIC.get(f.get("check_id"))
        if metric and metric not in values and isinstance(f.get("value"), (int, float)):
            values[metric] = float(f["value"])
            scopes.setdefault(metric, "read_processing")

    # derive target attainment (only for a compatible target type)
    ct = manifest.cell_target if manifest else None
    attainment, warn = target_attainment(values.get("cell.called_count"), ct)
    if warn:
        warnings.append(warn)
    if attainment is not None and "cell.target_attainment" not in values:
        values["cell.target_attainment"] = round(attainment, 6)
        scopes.setdefault("cell.target_attainment", "cell_analysis")

    assessments, fired, missing = evaluate(values, scopes, cat, prof)
    issues_ranked = rank_issues(fired, cat)
    hypotheses = rank_hypotheses(fired, cat)

    inputs_summary: dict[str, Any] = {
        "metrics_supplied": sorted(values),
        "profile_version": prof.version,
        "profile_evidence_strength": prof.evidence_strength,
    }
    if ct is not None:
        inputs_summary["cell_target"] = ct.to_dict()
        inputs_summary["cell_target_comparable"] = ct.comparable_with_called()

    return Diagnosis(
        profile_version=prof.version,
        title=title,
        inputs_summary=inputs_summary,
        metric_assessments=assessments,
        fired_signals=fired,
        issues_ranked=issues_ranked,
        hypotheses=hypotheses,
        warnings=warnings,
        missing_evidence=missing,
    )


def diagnose_from_reports(
    reports: list[Any],
    *,
    manifest: InputManifest | None = None,
    qc_findings: list[dict[str, Any]] | None = None,
    catalog: Catalog | None = None,
    profile: Profile | None = None,
    title: str | None = None,
) -> Diagnosis:
    values, scopes, warnings = reduce_observations(reports)
    return diagnose(
        values,
        scopes=scopes,
        manifest=manifest,
        qc_findings=qc_findings,
        catalog=catalog,
        profile=profile,
        title=title,
        extra_warnings=warnings,
    )
