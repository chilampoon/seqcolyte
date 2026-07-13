"""The current-check -> catalog adapter map must reference only ids that exist in the catalog."""

from __future__ import annotations

from qc.catalog.adapters import CHECK_ADAPTERS, adapter_target_ids
from qc.catalog.loader import load_catalog


def test_adapter_targets_resolve_in_catalog():
    missing = adapter_target_ids() - load_catalog().all_ids
    assert not missing, f"adapters reference unknown catalog ids: {sorted(missing)}"


def test_adapters_cover_the_current_check_ids():
    # the five Rust/Illumina checks + the nanopore internal-TSO check
    covered = {a.check_id for a in CHECK_ADAPTERS}
    expected = {
        "r1_length",
        "whitelist_hit_rate",
        "tso_at_r2_start",
        "r2_adapter_readthrough",
        "r2_polyg_tail",
        "tso_concatemer",
    }
    assert expected <= covered


def test_adapters_are_candidate_links_not_single_diagnoses():
    # whitelist_hit_rate is deliberately consistent with more than one cause (not a single diagnosis)
    wl = next(a for a in CHECK_ADAPTERS if a.check_id == "whitelist_hit_rate")
    assert len(wl.causes) >= 2
