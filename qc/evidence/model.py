"""Typed model for imported QC evidence (seqcolyte.qc_evidence.v1). Pure dataclasses, no I/O."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA_VERSION = "seqcolyte.qc_evidence.v1"

# canonical evidence scopes (mirror the diagnostic catalog's scope enum)
SCOPES = (
    "sequencing_run",
    "read_processing",
    "library_structure",
    "alignment_assignment",
    "cell_analysis",
    "complexity_expression",
    "wet_lab_qc",
)


@dataclass
class MetricObservation:
    """One observed metric value from a source report. The original label/denominator are never dropped."""

    original_label: str
    original_value_text: str
    source_scope: str
    source_locator: str
    value: float | None = None
    metric_id: str | None = None  # canonical id, or None when the label could not be mapped
    unit: str | None = None
    source_denominator: str | None = None
    confidence: float = 1.0
    extraction_method: str = "html"
    producer_metadata: dict[str, Any] | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class EvidenceReport:
    """A parsed, vendor-neutral QC evidence document."""

    evidence_report_id: str
    source_file: str
    source_checksum: str
    source_scopes: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION
    producer: str | None = None
    producer_version: str | None = None
    extraction_method: str = "html"
    extraction_timestamp: str | None = None
    observations: list[MetricObservation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unparsed_sections: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)

    def canonical_observations(self) -> list[MetricObservation]:
        return [o for o in self.observations if o.metric_id]

    def metric_ids(self) -> set[str]:
        return {o.metric_id for o in self.observations if o.metric_id}

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_report_id": self.evidence_report_id,
            "schema_version": self.schema_version,
            "source_scopes": list(self.source_scopes),
            "producer": self.producer,
            "producer_version": self.producer_version,
            "source_file": self.source_file,
            "source_checksum": self.source_checksum,
            "extraction_method": self.extraction_method,
            "extraction_timestamp": self.extraction_timestamp,
            "observations": [o.to_dict() for o in self.observations],
            "warnings": list(self.warnings),
            "unparsed_sections": list(self.unparsed_sections),
            "provenance": dict(self.provenance),
        }
