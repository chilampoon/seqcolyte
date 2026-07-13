"""Rank candidate issues and root-cause hypotheses from the set of firing signals. Deterministic."""

from __future__ import annotations

from qc.catalog.loader import Catalog
from qc.diagnose.model import FiredSignal, Hypothesis, RankedIssue

__all__ = ["rank_issues", "rank_hypotheses"]

_CONTRA_PENALTY = 0.5


def rank_issues(fired: list[FiredSignal], catalog: Catalog) -> list[RankedIssue]:
    """Score each issue by the summed magnitude of its supporting signals that fired."""
    mag = {f.signal_id: f.magnitude for f in fired}
    out: list[RankedIssue] = []
    for issue in catalog.section("issues"):
        hits = [s for s in issue.get("supporting_signals", []) if s in mag]
        if not hits:
            continue
        score = round(sum(mag[s] for s in hits), 4)
        out.append(RankedIssue(issue_id=issue["issue_id"], title=issue["title"], score=score, fired_signals=hits))
    out.sort(key=lambda r: (-r.score, -len(r.fired_signals), r.issue_id))
    return out


def rank_hypotheses(fired: list[FiredSignal], catalog: Catalog) -> list[Hypothesis]:
    """Score each root cause by (supporting - penalty*contradicting) fired-signal magnitude."""
    mag = {f.signal_id: f.magnitude for f in fired}
    out: list[Hypothesis] = []
    for cause in catalog.section("root_causes"):
        supporting = [s for s in cause.get("observable_signals", []) if s in mag]
        contradicting = [s for s in cause.get("evidence_against", []) if s in mag]
        support_score = sum(mag[s] for s in supporting)
        if support_score <= 0:
            continue
        contra_score = sum(mag[s] for s in contradicting)
        score = round(support_score - _CONTRA_PENALTY * contra_score, 4)
        out.append(
            Hypothesis(
                cause_id=cause["cause_id"],
                title=cause["title"],
                score=score,
                cell_recovery_relationship=cause["cell_recovery_relationship"]["relationship"],
                recoverability=cause["recoverability"],
                mechanism=cause["mechanism"],
                supporting_signals=supporting,
                contradicting_signals=contradicting,
                confirmatory_tests=list(cause.get("diagnostic_tests", [])),
                produces_issues=list(cause.get("produces_issues", [])),
            )
        )
    out.sort(key=lambda h: (-h.score, -len(h.supporting_signals), h.cause_id))
    return out
