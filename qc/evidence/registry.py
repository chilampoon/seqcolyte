"""Importer registry: detect a report's type from its *content* (not filename) and parse it safely."""

from __future__ import annotations

from pathlib import Path

from qc.evidence.base import Importer
from qc.evidence.importers import LongReadSingleCellHtmlImporter, ShortReadSingleCellHtmlImporter
from qc.evidence.model import EvidenceReport

__all__ = ["IMPORTERS", "detect_importer", "import_report", "UnrecognizedReportError"]

# order is irrelevant; selection is by probe confidence
IMPORTERS: tuple[Importer, ...] = (
    ShortReadSingleCellHtmlImporter(),
    LongReadSingleCellHtmlImporter(),
)

_MIN_CONFIDENCE = 0.3


class UnrecognizedReportError(ValueError):
    """No importer recognised the report content with sufficient confidence."""


def detect_importer(path: str | Path) -> tuple[Importer | None, float]:
    """Return the highest-confidence importer for ``path`` (by content), or (None, 0.0)."""
    best: Importer | None = None
    best_conf = 0.0
    for imp in IMPORTERS:
        try:
            conf = imp.probe(path)
        except Exception:  # a probe must never crash detection
            conf = 0.0
        if conf > best_conf:
            best, best_conf = imp, conf
    return best, best_conf


def import_report(path: str | Path, *, min_confidence: float = _MIN_CONFIDENCE) -> EvidenceReport:
    """Detect and parse ``path`` into an :class:`EvidenceReport`. Raises :class:`UnrecognizedReportError`
    when no importer matches; a *detected* but malformed report parses to a report carrying warnings rather
    than crashing."""
    importer, conf = detect_importer(path)
    if importer is None or conf < min_confidence:
        raise UnrecognizedReportError(
            f"no importer recognised {Path(path).name!r} (best confidence {conf:.2f} < {min_confidence})"
        )
    try:
        report = importer.parse(path)
    except Exception as exc:  # fail safe: never crash on a detected-but-broken report
        from qc.evidence.base import sha256_file

        checksum = sha256_file(path)
        report = EvidenceReport(
            evidence_report_id=f"evidence-{checksum[:12]}",
            source_file=Path(path).name,
            source_checksum=checksum,
            producer=importer.name,
            warnings=[f"parser error ({type(exc).__name__}): {exc}"],
        )
    report.provenance.setdefault("detected_confidence", round(conf, 3))
    return report
