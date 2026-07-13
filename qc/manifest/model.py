"""Typed input-manifest model (seqcolyte.input_manifest.v1). Pure dataclasses, no I/O."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA_VERSION = "seqcolyte.input_manifest.v1"

# All recognised cell-target types, upstream -> downstream.
CELL_TARGET_TYPES = (
    "cells_loaded",
    "viable_cells_loaded",
    "expected_captured_cells",
    "expected_recovered_cells",
    "expected_called_cells",
    "expected_cells_across_samples",
)

# Only these are directly comparable to a per-library called-cell count. Loading/capture targets sit
# upstream of cell calling and must NOT be divided into called cells to form an "attainment".
TARGET_TYPES_COMPARABLE_WITH_CALLED = frozenset(
    {"expected_recovered_cells", "expected_called_cells"}
)


@dataclass
class CellTarget:
    value: float
    target_type: str
    scope: str = "whole_library"  # whole_library | per_sample
    source: str = "experimental_design"
    confidence: str = "unknown"  # high | medium | low | unknown

    def comparable_with_called(self) -> bool:
        return self.target_type in TARGET_TYPES_COMPARABLE_WITH_CALLED

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InputManifest:
    """Optional inputs for an investigation. Everything is optional; missing inputs are valid."""

    schema_version: str = SCHEMA_VERSION
    protocol_spec: str | None = None
    fastq: list[str] = field(default_factory=list)
    bam: str | None = None
    feature_matrix: str | None = None
    qc_evidence_reports: list[str] = field(default_factory=list)
    reference: str | None = None
    cell_target: CellTarget | None = None
    wet_lab: dict[str, Any] = field(default_factory=dict)
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"schema_version": self.schema_version}
        if self.protocol_spec is not None:
            out["protocol_spec"] = self.protocol_spec
        if self.fastq:
            out["fastq"] = list(self.fastq)
        if self.bam is not None:
            out["bam"] = self.bam
        if self.feature_matrix is not None:
            out["feature_matrix"] = self.feature_matrix
        if self.qc_evidence_reports:
            out["qc_evidence_reports"] = list(self.qc_evidence_reports)
        if self.reference is not None:
            out["reference"] = self.reference
        if self.cell_target is not None:
            out["cell_target"] = self.cell_target.to_dict()
        if self.wet_lab:
            out["wet_lab"] = dict(self.wet_lab)
        if self.notes is not None:
            out["notes"] = self.notes
        return out


def target_attainment(called: float | None, target: CellTarget | None) -> tuple[float | None, str | None]:
    """Return (attainment, warning). Attainment (called/target) is only computed when the target type is
    compatible with called cells; otherwise it stays None with an explanatory warning so callers never
    fabricate an attainment from an incompatible target."""
    if target is None:
        return None, None
    if called is None:
        return None, "no called-cell count available to compare against the target"
    if not target.comparable_with_called():
        return None, (
            f"cell target type {target.target_type!r} is not comparable with called cells; "
            "attainment not computed"
        )
    if target.value <= 0:
        return None, "cell target value must be positive to compute attainment"
    return called / target.value, None
