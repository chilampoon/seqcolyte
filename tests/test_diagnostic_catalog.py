"""Offline tests for the diagnostic catalog: schema, cross-references, invariants, deterministic docs."""

from __future__ import annotations

from pathlib import Path

import pytest

from qc.catalog.loader import load_catalog
from qc.catalog.render_docs import REPO_ROOT, render_artifacts
from qc.catalog.validate import CatalogError, validate_catalog, validate_or_raise


def test_catalog_validates_schema_and_cross_references():
    assert validate_catalog(load_catalog()) == []
    validate_or_raise()  # must not raise


def test_ids_are_unique_within_each_section():
    cat = load_catalog()
    for section in ("metrics", "signals", "issues", "root_causes", "diagnostic_tests", "references"):
        ids = [next(iter(v for k, v in item.items() if k.endswith("_id") or k == "recovery_class"))
               for item in cat.section(section)]
        assert len(ids) == len(set(ids)), f"duplicate id in {section}"


def test_every_issue_has_a_signal_or_required_evidence():
    for issue in load_catalog().section("issues"):
        assert issue.get("supporting_signals") or issue.get("required_evidence"), issue["issue_id"]


def test_every_cause_declares_cell_recovery_and_recoverability():
    for cause in load_catalog().section("root_causes"):
        rel = cause["cell_recovery_relationship"]
        assert rel["relationship"] in {"direct", "indirect", "unlikely", "context_dependent"}
        assert rel["note"]
        assert cause["recoverability"]


def test_every_reference_used_resolves():
    cat = load_catalog()
    ref_ids = cat.ids("references")
    for section in ("metrics", "signals", "issues", "root_causes", "diagnostic_tests"):
        for item in cat.section(section):
            for r in item.get("references", []):
                assert r in ref_ids, f"{section}: dangling reference {r}"


def test_poly_g_is_a_signal_not_a_root_cause():
    """Modelling rule: poly-G is a supporting signal, never an independent root cause."""
    cat = load_catalog()
    cause_ids = cat.ids("root_causes")
    assert not any("polyg" in c or "poly_g" in c for c in cause_ids)
    polyg = cat.index("signals").get("signal.polyg_tail_elevated")
    assert polyg is not None and polyg.get("is_root_cause") is False


def test_render_is_deterministic():
    a = render_artifacts()
    b = render_artifacts()
    assert a == b


@pytest.mark.parametrize("relpath", ["spec/diagnostics/catalog.json", "docs/qc/diagnostics.md", "docs/qc/metric-glossary.md"])
def test_generated_artifacts_match_checked_in(relpath):
    content = render_artifacts()[relpath]
    dst = REPO_ROOT / relpath
    assert dst.exists(), f"missing generated artifact {relpath} (run `python -m qc.catalog render`)"
    assert dst.read_text() == content, f"{relpath} is stale (run `python -m qc.catalog render`)"


def test_invalid_catalog_is_rejected():
    from qc.catalog.loader import Catalog

    broken = load_catalog().raw
    # inject an unresolved reference
    broken = {**broken, "issues": [{**broken["issues"][0], "candidate_root_causes": ["cause.does_not_exist"]}] + broken["issues"][1:]}
    errors = validate_catalog(Catalog(broken))
    assert any("cause.does_not_exist" in e for e in errors)
    with pytest.raises(CatalogError):
        validate_or_raise(Catalog(broken))
