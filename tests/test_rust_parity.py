"""THE GATE for the Rust port: the ``seqcolyte-qc`` binary must reproduce the pure-Python QC
compute (profile + findings + eval) field-for-field on the real fixtures.

We compare the **serialized** JSON (``json.dumps(..., sort_keys=True)``) of the ``{profile,
findings, eval}`` subset, not a dict ``==``: a serialized compare catches a Rust ``1`` where
Python emits ``1.0`` (they'd be ``==`` as Python objects but differ on the wire).

Skips when the binary isn't built (``make rust``) or a fixture is missing — so it never yields
a false pass by silently falling back to the Python engine.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qc.engine import run_qc
from qc.rust_engine import rust_binary

REPO = Path(__file__).resolve().parents[1]
SPEC = REPO / "spec" / "tenx_3p_v3.json"
WL = REPO / "whitelists" / "3M-february-2018.txt.gz"
DIMER_R1 = REPO / "data" / "sim" / "adapter_dimer_f30" / "R1.fastq.gz"
DIMER_R2 = REPO / "data" / "sim" / "adapter_dimer_f30" / "R2.fastq.gz"
DIMER_LABELS = REPO / "sim" / "labels" / "adapter_dimer_f30.tsv"
CTRL_R1 = REPO / "data" / "raw" / "pbmc_1k_v3_sub_R1.fastq.gz"
CTRL_R2 = REPO / "data" / "raw" / "pbmc_1k_v3_sub_R2.fastq.gz"

pytestmark = pytest.mark.skipif(
    not rust_binary().exists(),
    reason=f"seqcolyte-qc binary not built at {rust_binary()} (run `make rust`)",
)


def _subset(report: dict) -> dict:
    keys = ("profile", "findings", "eval")
    return {k: report[k] for k in keys if k in report}


def _require(*paths: Path) -> None:
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        pytest.skip(f"fixture(s) missing: {', '.join(missing)}")


def _assert_parity(r1: Path, r2: Path, *, whitelist=None, labels=None, max_reads=None) -> None:
    kw = dict(
        whitelist=str(whitelist) if whitelist else None,
        labels=str(labels) if labels else None,
        max_reads=max_reads,
        use_llm=False,  # offline + deterministic; the LLM plan is out of the compared subset
    )
    py = run_qc(str(SPEC), str(r1), str(r2), engine="python", **kw)
    rs = run_qc(str(SPEC), str(r1), str(r2), engine="rust", **kw)
    py_json = json.dumps(_subset(py), sort_keys=True)
    rs_json = json.dumps(_subset(rs), sort_keys=True)
    assert py_json == rs_json, (
        "Rust/Python QC divergence:\n"
        f"  python: {py_json}\n"
        f"  rust:   {rs_json}"
    )


def test_parity_dimer_full():
    """Failure set with whitelist + labels — exercises every check plus the eval block."""
    _require(DIMER_R1, DIMER_R2, WL, DIMER_LABELS)
    _assert_parity(DIMER_R1, DIMER_R2, whitelist=WL, labels=DIMER_LABELS)


def test_parity_dimer_max_reads():
    """--max-reads truncation must match (Python abandons its generator at the same cap)."""
    _require(DIMER_R1, DIMER_R2, WL, DIMER_LABELS)
    _assert_parity(DIMER_R1, DIMER_R2, whitelist=WL, labels=DIMER_LABELS, max_reads=5000)


def test_parity_dimer_no_whitelist_no_labels():
    """Whitelist + eval checks omitted — the array shrinks identically in both engines."""
    _require(DIMER_R1, DIMER_R2)
    _assert_parity(DIMER_R1, DIMER_R2)


def test_parity_control_with_whitelist():
    """The clean control (high whitelist hit-rate, all-pass) — no labels."""
    _require(CTRL_R1, CTRL_R2, WL)
    _assert_parity(CTRL_R1, CTRL_R2, whitelist=WL)


def test_parity_control_max_reads():
    _require(CTRL_R1, CTRL_R2, WL)
    _assert_parity(CTRL_R1, CTRL_R2, whitelist=WL, max_reads=1000)
