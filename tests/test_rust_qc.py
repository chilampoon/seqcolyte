"""Regression gate for the ``qc-core`` Rust compute core.

QC's per-read compute (FASTQ profile + checks + eval) lives only in the Rust binary now, so we
freeze known-good output on the deterministic ``adapter_dimer_f30`` fixture (byte-reproducible
from the simulator) and assert the binary keeps reproducing it. Regenerate the golden with:

    python -c "import json,qc.rust_engine as r; ..."   # see tests/golden/rust_qc_dimer.json

Skips when the binary isn't built (``make rust``) or a fixture is missing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qc.rust_engine import run_rust_qc, rust_binary

REPO = Path(__file__).resolve().parents[1]
SPEC = REPO / "spec" / "tenx_3p_v3.json"
WL = REPO / "whitelists" / "3M-february-2018.txt.gz"
R1 = REPO / "data" / "sim" / "adapter_dimer_f30" / "R1.fastq.gz"
R2 = REPO / "data" / "sim" / "adapter_dimer_f30" / "R2.fastq.gz"
LABELS = REPO / "sim" / "labels" / "adapter_dimer_f30.tsv"
GOLDEN = REPO / "tests" / "golden" / "rust_qc_dimer.json"

pytestmark = pytest.mark.skipif(
    not rust_binary().exists(),
    reason=f"qc-core binary not built at {rust_binary()} (run `make rust`)",
)

# variant name -> kwargs for run_rust_qc
_VARIANTS = {
    "full": dict(whitelist=str(WL), labels=str(LABELS)),
    "no_whitelist": dict(),
    "max_reads_5000": dict(whitelist=str(WL), labels=str(LABELS), max_reads=5000),
}


def _require(*paths: Path) -> None:
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        pytest.skip(f"fixture(s) missing: {', '.join(missing)}")


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(GOLDEN.read_text())


@pytest.mark.parametrize("variant", list(_VARIANTS))
def test_rust_qc_matches_golden(variant, golden):
    _require(SPEC, R1, R2, WL, LABELS, GOLDEN)
    got = run_rust_qc(str(SPEC), str(R1), str(R2), **_VARIANTS[variant])
    assert json.dumps(got, sort_keys=True) == json.dumps(golden[variant], sort_keys=True), (
        f"variant {variant!r} drifted from tests/golden/rust_qc_dimer.json"
    )


def test_whitelist_and_labels_toggle_output(golden):
    """Sanity: omitting the whitelist drops a check; omitting labels drops the eval block."""
    _require(GOLDEN)
    assert len(golden["full"]["findings"]) == 5
    assert len(golden["no_whitelist"]["findings"]) == 4      # whitelist check omitted
    assert golden["full"]["eval"] is not None
    assert golden["no_whitelist"]["eval"] is None            # no labels -> no eval
    assert golden["max_reads_5000"]["profile"]["n_pairs"] == 5000
