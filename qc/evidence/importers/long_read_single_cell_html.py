"""Importer for long-read single-cell analysis HTML reports (ONT wf-single-cell-style).

Metrics live in DataTables ``<tr><th>label</th><td>value</td></tr>`` rows. We scrape them with
BeautifulSoup (never execute the report's JavaScript / Bokeh) and map each label to a canonical catalog id
while preserving the original label/value/locator. Multi-sample reports repeat labels; each repeat is kept
as a separate observation so conflicting values are never silently merged.
"""

from __future__ import annotations

from pathlib import Path

from qc.evidence import base
from qc.evidence.model import EvidenceReport, MetricObservation

_SOURCE_SCOPES = [
    "sequencing_run",
    "read_processing",
    "library_structure",
    "alignment_assignment",
    "cell_analysis",
]


class LongReadSingleCellHtmlImporter(base.Importer):
    name = "long_read_single_cell_html"

    def probe(self, path: str | Path) -> float:
        try:
            text = base.read_text_capped(path)
        except OSError:
            return 0.0
        low = text.lower()
        score = 0.0
        if "wf-single-cell" in low:
            score += 0.6
        if "epi2me" in low or "oxford nanopore" in low:
            score += 0.2
        if "<table" in low and ("estimated cells" in low or "full length" in low):
            score += 0.3
        # de-prioritise the short-read report, which stores metrics in a `data` blob, not tables
        if "summary_tab" in text:
            score -= 0.5
        return max(0.0, min(1.0, score))

    def parse(self, path: str | Path) -> EvidenceReport:
        text = base.read_text_capped(path)
        checksum = base.sha256_file(path)
        report = EvidenceReport(
            evidence_report_id=f"evidence-{checksum[:12]}",
            source_file=Path(path).name,
            source_checksum=checksum,
            source_scopes=list(_SOURCE_SCOPES),
            producer="long_read_single_cell_html",
            extraction_method="html_table",
            provenance={"importer": self.name, "producer_family": "wf-single-cell-like"},
        )

        rows = base.scrape_kv_tables(text)
        if not rows:
            report.warnings.append("no key/value tables found; no metrics imported")
            report.unparsed_sections.append("tables")
            return report

        for row in rows:
            mapped = base.map_label(row.label)
            raw, is_pct = base.parse_number(row.value_text)
            # long-read reports label some fractions with a leading '%' on the label, not the value
            is_pct = is_pct or row.label.strip().startswith("%") or "full length" in row.label.lower()
            unit = mapped["unit"] if mapped else None
            value, note = base.normalize_value(raw, is_pct, unit)
            if mapped is None:
                report.warnings.append(f"unmapped label: {row.label!r} (kept as an observation without a canonical id)")
            report.observations.append(
                MetricObservation(
                    original_label=row.label,
                    original_value_text=row.value_text,
                    source_scope=mapped["domain"] if mapped else "cell_analysis",
                    source_locator=row.locator,
                    value=value,
                    metric_id=mapped["metric_id"] if mapped else None,
                    unit=unit,
                    source_denominator=(mapped["denominator"] or None) if mapped else None,
                    confidence=1.0 if mapped else 0.4,
                    extraction_method="html_table",
                    notes=note,
                )
            )
        return report
