"""Versioned input manifest for a diagnostic investigation.

Declares the optional inputs a future run/investigation can carry (protocol spec, FASTQ, BAM, feature
matrix, QC evidence reports, reference, wet-lab measurements) and — importantly — a *typed* cell target.
The target type governs whether the declared target may be compared to called cells at all, so the
diagnosis engine never compares called cells against an incompatible target (e.g. cells loaded).
No network, no LLM.
"""

from qc.manifest.model import (
    CellTarget,
    InputManifest,
    SCHEMA_VERSION,
    TARGET_TYPES_COMPARABLE_WITH_CALLED,
    target_attainment,
)

__all__ = [
    "CellTarget",
    "InputManifest",
    "SCHEMA_VERSION",
    "TARGET_TYPES_COMPARABLE_WITH_CALLED",
    "target_attainment",
]
