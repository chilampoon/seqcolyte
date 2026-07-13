"""Typed diagnosis result model (seqcolyte.diagnosis.v1). Pure dataclasses, no I/O."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA_VERSION = "seqcolyte.diagnosis.v1"

Status = str  # "ok" | "warn" | "fail" | "unknown"


@dataclass
class MetricAssessment:
    metric_id: str
    value: float | None
    status: Status
    magnitude: float  # 0.0 ok .. 1.0 fail
    basis: str  # how the status was decided (threshold or "relative"/"descriptive"/"no profile")
    source_scope: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FiredSignal:
    signal_id: str
    label: str
    magnitude: float
    driving_metrics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Hypothesis:
    """A ranked candidate root cause with the evidence for/against it."""

    cause_id: str
    title: str
    score: float
    cell_recovery_relationship: str
    recoverability: str
    mechanism: str
    supporting_signals: list[str] = field(default_factory=list)
    contradicting_signals: list[str] = field(default_factory=list)
    confirmatory_tests: list[str] = field(default_factory=list)
    produces_issues: list[str] = field(default_factory=list)
    narrative: str | None = None  # optional LLM explanation

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class RankedIssue:
    issue_id: str
    title: str
    score: float
    fired_signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Diagnosis:
    schema_version: str = SCHEMA_VERSION
    profile_version: str = ""
    title: str | None = None
    inputs_summary: dict[str, Any] = field(default_factory=dict)
    metric_assessments: list[MetricAssessment] = field(default_factory=list)
    fired_signals: list[FiredSignal] = field(default_factory=list)
    issues_ranked: list[RankedIssue] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    summary: str | None = None  # optional LLM narrative for the whole diagnosis

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile_version": self.profile_version,
            "title": self.title,
            "inputs_summary": dict(self.inputs_summary),
            "metric_assessments": [m.to_dict() for m in self.metric_assessments],
            "fired_signals": [s.to_dict() for s in self.fired_signals],
            "issues_ranked": [i.to_dict() for i in self.issues_ranked],
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "warnings": list(self.warnings),
            "missing_evidence": list(self.missing_evidence),
            "summary": self.summary,
        }
