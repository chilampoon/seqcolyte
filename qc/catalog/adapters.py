"""Map current Seqcolyte QC check ids onto catalog vocabulary as *candidate* relationships.

These are hints for future ranking, not certainties: a single check does not force a single
root-cause diagnosis. The QC engine is unchanged; this is a read-only lookup used by docs/tooling.
Every target id here is asserted to resolve in the catalog by tests/test_catalog_adapters.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["CheckAdapter", "CHECK_ADAPTERS", "adapter_target_ids"]


@dataclass(frozen=True)
class CheckAdapter:
    """Candidate catalog links for one existing QC check id."""

    check_id: str
    engine: str  # "illumina" (Rust core) | "nanopore"
    metrics: tuple[str, ...] = ()
    signals: tuple[str, ...] = ()
    causes: tuple[str, ...] = ()
    tests: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()
    note: str = ""


CHECK_ADAPTERS: tuple[CheckAdapter, ...] = (
    CheckAdapter(
        check_id="r1_length",
        engine="illumina",
        tests=("test.read_configuration_audit",),
        issues=("issue.barcode_umi_recovery_failure",),
        causes=("cause.read_configuration_mismatch",),
        note="R1 shorter than cell barcode + UMI is a read-configuration mismatch; candidate, not proof.",
    ),
    CheckAdapter(
        check_id="whitelist_hit_rate",
        engine="illumina",
        metrics=("barcode.whitelist_fraction", "barcode.valid_fraction"),
        signals=("signal.low_whitelist_match",),
        causes=("cause.wrong_chemistry_or_whitelist", "cause.barcode_boundary_shift"),
        issues=("issue.barcode_umi_recovery_failure",),
        note="A low whitelist hit rate is consistent with either a wrong whitelist or a barcode boundary shift.",
    ),
    CheckAdapter(
        check_id="tso_at_r2_start",
        engine="illumina",
        metrics=("library.tso_at_rna_read_start_fraction",),
        signals=("signal.tso_at_read_start",),
        causes=("cause.short_or_empty_cdna_products",),
        issues=("issue.abnormal_library_structure",),
        note="Short-read TSO at read start — distinct from long-read internal TSO motifs.",
    ),
    CheckAdapter(
        check_id="r2_adapter_readthrough",
        engine="illumina",
        metrics=("library.short_insert_fraction",),
        signals=("signal.short_insert_elevated",),
        causes=("cause.adapter_dimer_or_short_insert",),
        issues=("issue.low_informative_read_yield",),
    ),
    CheckAdapter(
        check_id="r2_polyg_tail",
        engine="illumina",
        metrics=("library.polyg_tail_fraction",),
        signals=("signal.polyg_tail_elevated",),
        causes=("cause.read_past_end_or_signal_decay",),
        note="Poly-G is a supporting signal of read-past-end / signal decay, not an independent root cause.",
    ),
    CheckAdapter(
        check_id="tso_concatemer",
        engine="nanopore",
        metrics=("library.internal_adapter_fraction",),
        signals=("signal.internal_adapter_elevated",),
        causes=("cause.long_read_tso_concatemer_or_fusion",),
        tests=("test.internal_tso_scan",),
        issues=("issue.abnormal_library_structure",),
        note="Long-read internal TSO/concatemer scan.",
    ),
)


def adapter_target_ids() -> set[str]:
    """Every catalog id referenced by any adapter (for cross-reference tests)."""
    out: set[str] = set()
    for a in CHECK_ADAPTERS:
        out |= set(a.metrics) | set(a.signals) | set(a.causes) | set(a.tests) | set(a.issues)
    return out
