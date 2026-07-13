"""Turn metric values into per-metric assessments and the set of firing catalog signals."""

from __future__ import annotations

from qc.catalog.loader import Catalog
from qc.diagnose.model import FiredSignal, MetricAssessment
from qc.diagnose.profile import Profile

__all__ = ["evaluate"]


def evaluate(
    values: dict[str, float],
    scopes: dict[str, str] | None,
    catalog: Catalog,
    profile: Profile,
) -> tuple[list[MetricAssessment], list[FiredSignal], list[str]]:
    """Assess metric values and derive firing signals.

    Returns (metric_assessments, fired_signals, missing_metric_ids). A signal fires when any metric it
    references is warn/fail; its magnitude is the worst metric magnitude. Metrics referenced by signals
    but not supplied are reported as missing evidence.
    """
    scopes = scopes or {}
    signals = catalog.section("signals")

    # every metric referenced by any signal, plus any supplied value
    referenced = {m for s in signals for m in s.get("metrics", [])}
    referenced |= set(values)

    assessments: dict[str, MetricAssessment] = {}
    for mid in sorted(referenced):
        value = values.get(mid)
        status, magnitude, basis = profile.assess(mid, value)
        assessments[mid] = MetricAssessment(
            metric_id=mid,
            value=value,
            status=status,
            magnitude=magnitude,
            basis=basis,
            source_scope=scopes.get(mid),
        )

    fired: list[FiredSignal] = []
    for s in signals:
        metrics = s.get("metrics", [])
        driving = [m for m in metrics if assessments.get(m) and assessments[m].status in ("warn", "fail")]
        if not driving:
            continue
        magnitude = max(assessments[m].magnitude for m in driving)
        fired.append(FiredSignal(signal_id=s["signal_id"], label=s["label"], magnitude=magnitude, driving_metrics=driving))

    missing = sorted(m for m in referenced if m not in values)
    return list(assessments.values()), fired, missing
