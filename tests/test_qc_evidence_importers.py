"""Offline tests for the QC evidence importers + registry. No network, no LLM, no JS execution."""

from __future__ import annotations

from pathlib import Path

import pytest

from qc.evidence.loader import dump_evidence_json
from qc.evidence.registry import (
    UnrecognizedReportError,
    detect_importer,
    import_report,
)

FIX = Path(__file__).parent / "fixtures"
CELLRANGER = FIX / "cellranger_summary.min.html"
WF = FIX / "wf_single_cell.min.html"
MALFORMED = FIX / "malformed.html"

# substrings that would indicate real run/sample metadata leaked into a fixture
_PRIVACY_DENYLIST = ["Msi2", "IGO", "/igo/", "PBM60534", "c8ea41cc", "refdata-gex", "20260609"]


def test_registry_detects_each_fixture_by_content():
    imp_sr, c_sr = detect_importer(CELLRANGER)
    imp_lr, c_lr = detect_importer(WF)
    assert imp_sr.name == "short_read_single_cell_html" and c_sr >= 0.6
    assert imp_lr.name == "long_read_single_cell_html" and c_lr >= 0.6


def test_short_read_imports_canonical_ids_with_provenance():
    rep = import_report(CELLRANGER)
    by_id = {o.metric_id: o for o in rep.canonical_observations()}
    assert by_id["cell.called_count"].value == 1234
    # 95.0% must be normalised to a fraction
    assert by_id["barcode.valid_fraction"].value == pytest.approx(0.95)
    assert by_id["mapping.genome_fraction"].value == pytest.approx(0.92)
    assert by_id["complexity.sequencing_saturation"].value == pytest.approx(0.40)
    # original label + locator retained (never discarded)
    o = by_id["barcode.valid_fraction"]
    assert o.original_label == "Valid Barcodes"
    assert o.original_value_text == "95.0%"
    assert o.source_locator.startswith("summary_tab/")
    assert o.source_denominator  # denominator preserved from the catalog


def test_long_read_imports_and_retains_conflicting_observations():
    rep = import_report(WF)
    called = [o for o in rep.observations if o.metric_id == "cell.called_count"]
    # the fixture has two samples with different "Estimated cells" -> both retained, not merged
    assert sorted(o.value for o in called) == [90.0, 120.0]
    by_id = {o.metric_id for o in rep.canonical_observations()}
    assert {"run.reads_total", "cell.called_count", "barcode.valid_fraction", "assignment.gene_fraction"} <= by_id
    # "% full length reads" -> fraction
    fl = next(o for o in rep.observations if o.metric_id == "library.full_length_proxy_fraction")
    assert fl.value == pytest.approx(0.38)


def test_unmapped_labels_are_kept_as_warnings_not_dropped():
    rep = import_report(WF)
    # adapter-configuration rows have no canonical metric -> warnings, but observations still recorded
    assert any("unmapped label" in w for w in rep.warnings)
    labels = {o.original_label for o in rep.observations}
    assert "full_length" in labels  # kept as an observation with metric_id=None
    assert any(o.original_label == "full_length" and o.metric_id is None for o in rep.observations)


def test_importer_does_not_execute_report_javascript():
    rep = import_report(WF)
    blob = dump_evidence_json(rep)
    # nothing sourced from the <script> block should appear as data
    assert "__should_not_run__" not in blob
    assert "docs_json" not in blob
    assert not hasattr(globals().get("__builtins__", object()), "__should_not_run__")


def test_malformed_report_fails_safe():
    rep = import_report(MALFORMED)  # must not raise
    assert rep.warnings, "a malformed report should record a warning"
    assert rep.canonical_observations() == []


def test_unrecognized_report_raises(tmp_path):
    plain = tmp_path / "unknown.html"
    plain.write_text("<html><body><p>not a QC report</p></body></html>")
    with pytest.raises(UnrecognizedReportError):
        import_report(plain)


def test_evidence_report_matches_schema():
    for path in (CELLRANGER, WF, MALFORMED):
        dump_evidence_json(import_report(path))  # validates against schema.json internally


def test_fixtures_contain_no_real_sample_metadata():
    for path in (CELLRANGER, WF, MALFORMED):
        text = path.read_text()
        for bad in _PRIVACY_DENYLIST:
            assert bad not in text, f"fixture {path.name} contains disallowed token {bad!r}"


def test_short_read_never_imports_sample_metadata():
    rep = import_report(CELLRANGER)
    blob = dump_evidence_json(rep)
    for bad in ["synthetic_sample", "/synthetic/reference/path"]:
        assert bad not in blob, "run/sample metadata must never become an observation"
    assert any("pipeline_info_table" in s for s in rep.unparsed_sections)
