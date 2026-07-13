"""Canonical QC evidence model + safe HTML importers (seqcolyte.qc_evidence.v1).

Third-party QC reports (Cell Ranger web summaries, ONT wf-single-cell reports, ...) are parsed into a
vendor-neutral :class:`~qc.evidence.model.EvidenceReport` of :class:`~qc.evidence.model.MetricObservation`
records. Canonical metric ids come from the diagnostic catalog; the original label + denominator are always
preserved in provenance. Importers never execute report JavaScript, never ``eval``, and never render
imported HTML. Nothing here touches the network or an LLM.
"""

from qc.evidence.model import EvidenceReport, MetricObservation, SCHEMA_VERSION
from qc.evidence.registry import detect_importer, import_report

__all__ = [
    "EvidenceReport",
    "MetricObservation",
    "SCHEMA_VERSION",
    "detect_importer",
    "import_report",
]
