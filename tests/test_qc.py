"""Offline tests for the QC checks + eval (no FASTQ, no LLM)."""

from seqcolyte.spec.loader import load_spec
from qc.checks import (
    check_r1_length, check_r2_polyg_tail, check_tso_at_r2_start, check_whitelist_hit_rate,
)
from qc.eval import evaluate
from qc.model import DataProfile, has_homopolymer_tail, startswith_fuzzy
from conftest import SPEC_PATH

TSO = "AAGCAGTGGTATCAACGCAGAGTACATGGG"


def _spec():
    return load_spec(SPEC_PATH)


def test_pattern_helpers():
    assert startswith_fuzzy(TSO + "AAAA", TSO, 0)
    assert startswith_fuzzy("XX" + TSO[2:] + "AAAA", TSO, 2)      # 2 mismatches ok
    assert not startswith_fuzzy("XXX" + TSO[3:] + "AAAA", TSO, 2)  # 3 mismatches too many
    assert has_homopolymer_tail("A" * 70 + "G" * 21, "G")
    assert not has_homopolymer_tail("A" * 91, "G")


def test_r1_length_check():
    spec = _spec()
    assert check_r1_length(DataProfile.from_reads(["A" * 28] * 8, ["C" * 91] * 8), spec, {}).verdict == "pass"
    bad = DataProfile.from_reads(["A" * 28] * 7 + ["A" * 27], ["C" * 91] * 8)
    assert check_r1_length(bad, spec, {}).verdict == "fail"


def test_tso_check_flags_dimers():
    spec = _spec()
    r2 = ["GATCGATCGT" * 9 + "A" for _ in range(4)] + [TSO + "A" * 61 for _ in range(6)]  # 60% TSO-led
    f = check_tso_at_r2_start(DataProfile.from_reads(["A" * 28] * 10, r2), spec, {})
    assert abs(f.affected_fraction - 0.6) < 1e-9 and f.verdict == "fail"
    assert f.evidence and "readthrough_chain" in f.evidence[0]["spec_ref"]


def test_polyg_check():
    spec = _spec()
    r2 = ["A" * 91] * 8 + ["A" * 70 + "G" * 21] * 2  # 20% poly-G tail
    f = check_r2_polyg_tail(DataProfile.from_reads(["A" * 28] * 10, r2), spec, {})
    assert f.affected_fraction == 0.2 and f.verdict == "fail"


def test_polyg_skipped_when_no_dark_base():
    spec = _spec()
    spec.data["platform_params"]["dark_base"] = None  # e.g. a non-two-color platform
    assert check_r2_polyg_tail(DataProfile.from_reads(["A" * 28] * 4, ["A" * 91] * 4), spec, {}) is None


def test_whitelist_check_and_skip():
    spec = _spec()
    r1 = [("ACGT" * 4 + "A" * 12), ("TTTT" * 4 + "A" * 12), ("GGGG" * 4 + "A" * 12)]  # 3 barcodes
    prof = DataProfile.from_reads(r1, ["C" * 91] * 3)
    assert check_whitelist_hit_rate(prof, spec, {"whitelist": None}) is None
    wl = {r1[0][:16].encode("ascii"), r1[1][:16].encode("ascii")}  # 2 of 3 on-list
    f = check_whitelist_hit_rate(prof, spec, {"whitelist": wl})
    assert abs(f.value - 2 / 3) < 1e-3  # Finding rounds value to 4 decimals


def test_eval_against_labels(tmp_path):
    spec = _spec()
    r2 = [TSO + "A" * 61, "GATCGATCGT" * 9 + "A", "A" * 70 + "G" * 21]  # affected, clean, affected(polyG)
    prof = DataProfile.from_reads(["A" * 28] * 3, r2)
    labels = tmp_path / "labels.tsv"
    labels.write_text("read_id\taffected\nr0\t1\nr1\t0\nr2\t1\n")
    ev = evaluate(prof, spec, str(labels))
    assert ev["recall"] == 1.0 and ev["confusion"]["fn"] == 0 and ev["true_affected"] == 2
