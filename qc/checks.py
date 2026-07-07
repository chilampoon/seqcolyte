"""The deterministic check toolbox. Each check derives its expectation from the spec (so a
different modality's spec drives different behavior) and returns a spec-linked ``Finding``.

The failure-signature checks (TSO-at-R2-start, adapter read-through, poly-G tail) target exactly
the artifacts the simulator injects, so they can be scored against ground-truth labels (`qc/eval.py`).
"""

from __future__ import annotations

from qc.model import Finding, fraction, has_homopolymer_tail, startswith_fuzzy
from qc.registry import register

_ADAPTER_STEM = "AGATCGGAAGAGC"  # universal Illumina adapter stem (start of the R2 read-through adapter)
_TSO_OLIGO = "oligo_template_switching_oligo_tso"


def _tri(value: float, warn: float, fail: float) -> str:
    return "fail" if value >= fail else "warn" if value >= warn else "pass"


@register("r1_length")
def check_r1_length(profile, spec, res) -> Finding | None:
    expected = spec.read("R1").get("cycles", 28)
    lens = {len(s) for s in profile.r1}
    ok = lens == {expected}
    modal = max(lens, key=lambda L: sum(len(s) == L for s in profile.r1)) if lens else 0
    return Finding(
        "r1_length", "R1 length matches barcode + UMI",
        "pass" if ok else "fail", float(modal), "bp", f"== {expected}",
        None, 0.0 if ok else 0.9,
        evidence=[{"spec_ref": "read_structure.R1",
                   "note": f"R1 should be exactly {expected} bp (16 bp cell barcode + 12 bp UMI)"}],
        detail=f"R1 lengths span {min(lens)}–{max(lens)} bp" if lens else "no reads",
    )


@register("whitelist_hit_rate")
def check_whitelist_hit_rate(profile, spec, res) -> Finding | None:
    whitelist = res.get("whitelist")
    if whitelist is None:
        return None
    sl = spec.segment_slice("R1", "cell_barcode")
    rate = fraction(s[sl].encode("ascii") in whitelist for s in profile.r1)
    return Finding(
        "whitelist_hit_rate", "Cell barcodes on the 10x whitelist",
        "pass" if rate >= 0.85 else "warn" if rate >= 0.5 else "fail",
        round(rate, 4), "fraction", ">= 0.85", None, max(0.0, 0.85 - rate),
        evidence=[{"spec_ref": "whitelists.cell_barcode_3M_feb2018",
                   "note": "R1[0:16] should match the 3M-february-2018 gel-bead barcode whitelist"}],
        detail=f"{rate:.1%} of cell barcodes are on the whitelist",
    )


@register("tso_at_r2_start")
def check_tso_at_r2_start(profile, spec, res) -> Finding | None:
    try:
        tso = spec.oligo_sequence(_TSO_OLIGO)
    except (KeyError, ValueError):
        return None
    frac = fraction(startswith_fuzzy(s, tso, 2) for s in profile.r2)
    # real 10x libraries carry a low baseline of TSO-led fragments (~a few %); warn above that.
    return Finding(
        "tso_at_r2_start", "R2 reads beginning with the TSO (adapter-dimer / short insert)",
        _tri(frac, 0.05, 0.15), round(frac, 4), "fraction", "< 0.05", frac, min(1.0, frac * 2),
        evidence=[{"spec_ref": "read_structure.R2.readthrough_chain[tso_5prime]",
                   "note": "R2 should start with cDNA; a leading TSO is the hallmark of empty/short-insert products"}],
        detail=f"{frac:.1%} of R2 start with the TSO",
    )


@register("r2_adapter_readthrough")
def check_r2_adapter_readthrough(profile, spec, res) -> Finding | None:
    frac = fraction(_ADAPTER_STEM in s for s in profile.r2)
    return Finding(
        "r2_adapter_readthrough", "R2 read-through into the Illumina adapter",
        _tri(frac, 0.02, 0.10), round(frac, 4), "fraction", "< 0.02", frac, min(1.0, frac * 2),
        evidence=[{"spec_ref": "oligos.oligo_r1_readinto_adapter",
                   "note": f"the {_ADAPTER_STEM} adapter stem in R2 means the insert was shorter than the read length"}],
        detail=f"{frac:.1%} of R2 contain the adapter stem {_ADAPTER_STEM}",
    )


@register("r2_polyg_tail")
def check_r2_polyg_tail(profile, spec, res) -> Finding | None:
    base = spec.platform_params.get("dark_base")
    if not base:
        return None  # not a two-color platform (e.g. Nanopore) — no no-signal dark base
    frac = fraction(has_homopolymer_tail(s, base) for s in profile.r2)
    return Finding(
        "r2_polyg_tail", f"R2 with a poly-{base} no-signal tail",
        _tri(frac, 0.01, 0.05), round(frac, 4), "fraction", "< 0.01", frac, min(1.0, frac * 3),
        evidence=[{"spec_ref": "platform_params.dark_base",
                   "note": f"a poly-{base} 3' tail on two-color instruments is 'no signal' — typical of empty/short fragments"}],
        detail=f"{frac:.1%} of R2 have a poly-{base} tail",
    )
