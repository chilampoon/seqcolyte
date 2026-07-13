"""Importer for short-read single-cell analysis HTML reports (Cell Ranger-style web summaries).

Metrics live in an embedded ``const data = { ... "summary_tab": {key: {name, metric, threshold}} ... }``
JSON literal. We brace-match and ``json.loads`` it (never execute JS), then map each labelled metric to a
canonical catalog id while preserving the original label/value. Producer name is provenance only.
"""

from __future__ import annotations

from pathlib import Path

from qc.evidence import base
from qc.evidence.model import EvidenceReport, MetricObservation

_SOURCE_SCOPES = ["cell_analysis", "read_processing", "alignment_assignment", "complexity_expression"]
# tabs in the embedded object that hold metric maps ({name, metric, threshold}) and metric tables
_METRIC_TABS = ("summary_tab", "analysis_tab")
# run/sample-metadata tables (sample id, reference paths, ...) are NEVER imported as metrics
_METADATA_KEYS = {"pipeline_info_table"}


class ShortReadSingleCellHtmlImporter(base.Importer):
    name = "short_read_single_cell_html"

    def probe(self, path: str | Path) -> float:
        try:
            text = base.read_text_capped(path)
        except OSError:
            return 0.0
        low = text.lower()
        if "<html" not in low and "<div" not in low:
            return 0.0
        score = 0.0
        if "summary_tab" in text:
            score += 0.6
        if "const data" in text or "var data" in text:
            score += 0.2
        if "cellranger" in low or "10x genomics" in low or "web_summary" in low:
            score += 0.2
        # de-prioritise the long-read report, which is table-based, not a `data` blob
        if "wf-single-cell" in low or "epi2me" in low:
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
            producer="short_read_single_cell_html",
            extraction_method="embedded_json",
            provenance={"importer": self.name, "producer_family": "cellranger-like"},
        )

        data = base.extract_js_object(text, "data")
        if data is None:
            report.warnings.append("could not extract embedded 'data' object; no metrics imported")
            return report

        seen_any = False
        for tab in _METRIC_TABS:
            block = base.find_nested(data, tab)
            if not isinstance(block, dict):
                continue
            for key, entry in block.items():
                if not isinstance(entry, dict):
                    continue
                # never import run/sample metadata (sample ids, reference paths, ...)
                if key in _METADATA_KEYS or (entry.get("header") or []) == ["Sample"]:
                    report.unparsed_sections.append(f"{tab}/{key} (skipped: run/sample metadata)")
                    continue
                if "name" in entry and "metric" in entry:
                    self._observe(report, f"{tab}/{key}", str(entry["name"]), str(entry["metric"]),
                                  threshold=entry.get("threshold"))
                    seen_any = True
                    continue
                table = entry.get("table")
                if isinstance(table, dict) and isinstance(table.get("rows"), list):
                    for ri, row in enumerate(table["rows"]):
                        if isinstance(row, list) and len(row) >= 2 and isinstance(row[0], str) and isinstance(row[1], (str, int, float)):
                            self._observe(report, f"{tab}/{key}/row{ri}", row[0], str(row[1]))
                            seen_any = True
        if not seen_any:
            report.warnings.append("embedded object contained no recognised metrics")
            report.unparsed_sections.append("summary_tab/analysis_tab")
        return report

    @staticmethod
    def _observe(report: EvidenceReport, locator: str, label: str, value_text: str, *, threshold=None) -> None:
        mapped = base.map_label(label)
        raw, is_pct = base.parse_number(value_text)
        unit = mapped["unit"] if mapped else None
        value, note = base.normalize_value(raw, is_pct, unit)
        producer_meta = {"threshold": threshold} if threshold is not None else None
        if mapped is None:
            report.warnings.append(f"unmapped label: {label!r} (kept as an observation without a canonical id)")
        report.observations.append(
            MetricObservation(
                original_label=label,
                original_value_text=value_text,
                source_scope=mapped["domain"] if mapped else "cell_analysis",
                source_locator=locator,
                value=value,
                metric_id=mapped["metric_id"] if mapped else None,
                unit=unit,
                source_denominator=(mapped["denominator"] or None) if mapped else None,
                confidence=1.0 if mapped else 0.4,
                extraction_method="embedded_json",
                producer_metadata=producer_meta,
                notes=note,
            )
        )
