"""Offline tests for the diagnosis engine: profile assessment, signal firing, ranking, discrimination,
determinism, checked-in example drift, and the offline-safe LLM explain layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from qc.catalog.loader import load_catalog
from qc.diagnose.engine import diagnose
from qc.diagnose.examples import EXAMPLES_DIR, render_examples
from qc.diagnose.profile import load_profile
from qc.diagnose.signals import evaluate
from qc.manifest.model import CellTarget, InputManifest


def test_profile_assessment():
    prof = load_profile()
    assert prof.assess("barcode.valid_fraction", 0.38)[0] == "fail"
    assert prof.assess("barcode.valid_fraction", 0.72)[0] == "warn"
    assert prof.assess("barcode.valid_fraction", 0.95)[0] == "ok"
    assert prof.assess("library.adapter_only_fraction", 0.30)[0] == "fail"
    assert prof.assess("does.not_exist", 0.5)[0] == "unknown"


def test_signals_fire_from_values():
    cat, prof = load_catalog(), load_profile()
    _, fired, _ = evaluate({"barcode.valid_fraction": 0.3, "library.adapter_only_fraction": 0.3}, {}, cat, prof)
    fired_ids = {f.signal_id for f in fired}
    assert "signal.low_whitelist_match" in fired_ids
    assert "signal.elevated_adapter_only" in fired_ids


def _diag(observations, target_type="expected_recovered_cells"):
    m = InputManifest(cell_target=CellTarget(45000, target_type, confidence="high"))
    return diagnose(observations, manifest=m)


def test_ranking_discriminates_barcode_vs_calling():
    degraded = _diag({"cell.called_count": 2000, "barcode.valid_fraction": 0.38,
                      "barcode.whitelist_fraction": 0.40, "barcode.extractable_fraction": 0.55,
                      "cell.reads_in_cells_fraction": 0.35})
    healthy = _diag({"cell.called_count": 2000, "barcode.valid_fraction": 0.95,
                     "barcode.whitelist_fraction": 0.96, "barcode.extractable_fraction": 0.98,
                     "cell.reads_in_cells_fraction": 0.55})
    # same collapse, different top hypothesis depending on barcode health
    assert degraded.hypotheses[0].cause_id == "cause.barcode_boundary_shift"
    assert healthy.hypotheses[0].cause_id != "cause.barcode_boundary_shift"
    # a barcode-only signal fires in the degraded case, not the healthy one
    assert "signal.low_whitelist_match" in {s.signal_id for s in degraded.fired_signals}
    assert "signal.low_whitelist_match" not in {s.signal_id for s in healthy.fired_signals}


def test_incompatible_target_blocks_attainment_signal():
    dx = _diag({"cell.called_count": 2000, "barcode.valid_fraction": 0.95}, target_type="cells_loaded")
    assert any("not comparable" in w for w in dx.warnings)
    assert "cell.target_attainment" not in {a.metric_id for a in dx.metric_assessments if a.value is not None}
    assert "signal.called_cells_below_target" not in {s.signal_id for s in dx.fired_signals}


def test_contradicting_evidence_demotes_a_cause():
    # low whitelist supports read_configuration_mismatch; a firing evidence_against signal penalises it
    supported = diagnose({"barcode.valid_fraction": 0.3})
    with_contra = diagnose({"barcode.valid_fraction": 0.3, "assignment.gene_fraction": 0.3})
    def score(dx, cid):
        return next((h.score for h in dx.hypotheses if h.cause_id == cid), None)
    s0 = score(supported, "cause.read_configuration_mismatch")
    s1 = score(with_contra, "cause.read_configuration_mismatch")
    assert s0 is not None and s1 is not None and s1 < s0


def test_no_signals_no_hypotheses():
    dx = diagnose({"barcode.valid_fraction": 0.99, "mapping.genome_fraction": 0.98})
    assert dx.hypotheses == []


def test_diagnose_is_deterministic():
    a = _diag({"cell.called_count": 2000, "barcode.valid_fraction": 0.38}).to_dict()
    b = _diag({"cell.called_count": 2000, "barcode.valid_fraction": 0.38}).to_dict()
    assert a == b


def test_examples_render_deterministically_and_match_checked_in():
    rendered = render_examples()
    assert rendered == render_examples()  # deterministic
    for rel, content in rendered.items():
        dst = EXAMPLES_DIR / rel
        assert dst.exists(), f"missing example {rel} (run `python -m qc.diagnose render-examples`)"
        assert dst.read_text() == content, f"{rel} is stale (run `python -m qc.diagnose render-examples`)"


def test_explain_is_offline_safe_and_never_reorders(monkeypatch):
    from qc.diagnose import explain as explain_mod

    dx = _diag({"cell.called_count": 2000, "barcode.valid_fraction": 0.38})
    original_order = [h.cause_id for h in dx.hypotheses]

    def fake_run_claude(prompt, schema, *, model):
        return {"extraction": {
            "summary": "canned summary",
            "hypotheses": [
                {"cause_id": original_order[0], "narrative": "canned narrative"},
                {"cause_id": "cause.invented_not_real", "narrative": "ignore me"},
            ],
        }}

    monkeypatch.setattr("extract.doc_extract._run_claude", fake_run_claude)
    out = explain_mod.explain(dx)
    assert out.summary == "canned summary"
    assert out.hypotheses[0].narrative == "canned narrative"
    assert [h.cause_id for h in out.hypotheses] == original_order  # order unchanged
    assert all(h.cause_id != "cause.invented_not_real" for h in out.hypotheses)  # invented id ignored


def test_explain_degrades_when_llm_unavailable(monkeypatch):
    from qc.diagnose import explain as explain_mod

    dx = _diag({"cell.called_count": 2000, "barcode.valid_fraction": 0.38})
    def boom(*a, **k):
        raise RuntimeError("no claude CLI")
    monkeypatch.setattr("extract.doc_extract._run_claude", boom)
    out = explain_mod.explain(dx)
    assert any("LLM explanation unavailable" in w for w in out.warnings)
    assert out.summary is None
