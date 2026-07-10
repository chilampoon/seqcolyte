"""Offline tests for the Nanopore branch — no network, no LLM, no BAM, no vendor PDFs.

Covers the chemistry (TSO_RC derivation, canonical/reverse segment order, VN<->NB), the simulator
(orientations, determinism, quality length, label fidelity, source-motif de-duplication), the QC
(orientation normalization, concatemer detection), and the deterministic validator (hybrid conflict,
unresolved derivations, branch material refs).
"""

from __future__ import annotations

import copy
import gzip
import json
import random
from pathlib import Path

import pytest

from seqcolyte.nanopore import (CB_LEN, POLYT_LEN, R1_HANDLE, TSO, TSO_RC, UMI_LEN,
                                DEFAULT_CHEM, NanoporeChem, complement, reverse_complement)
from seqcolyte.spec.loader import load_spec, validate_spec
from seqcolyte.spec.validate import check_spec
from sim.nanopore import (FAILURE_MODES, OntErrorModel, SourceMol, normalize_source_seq,
                          simulate, synthetic_source)
from qc.nanopore import Stranding, run_nanopore_qc, n50

REPO = Path(__file__).resolve().parents[1]
NANO_SPEC = str(REPO / "spec" / "nanopore_10x_3p.json")
ILLUMINA_SPEC = str(REPO / "spec" / "10x_3p_v3.json")

P5 = "AATGATACGGCGACCACCGAGATCTACAC"
P7 = "CAAGCAGAAGACGGCATACGAGAT"


# ---------------------------------------------------------------- chemistry

def test_tso_rc_is_reverse_complement_of_tso():                      # (1)
    assert TSO_RC == reverse_complement(TSO)
    assert TSO_RC == "CCCATGTACTCTGCGTTGATACCACTGCTT"


def test_canonical_segment_order():                                 # (2)
    chem = DEFAULT_CHEM
    segs = chem.canonical_segments("A" * 16, "C" * 12, "GGG")
    assert [name for name, _ in segs] == ["r1_handle", "cell_barcode", "umi", "polyt", "vn", "cdna", "tso_rc"]
    mol = chem.canonical_molecule("A" * 16, "C" * 12, "GGG")
    assert mol.startswith(R1_HANDLE) and mol.endswith(TSO_RC)


def test_reverse_complement_molecule_segment_order():               # (3)
    chem = DEFAULT_CHEM
    mol = chem.canonical_molecule("A" * 16, "C" * 12, "ACGTACGT")
    rc = reverse_complement(mol)
    assert rc.startswith(TSO)               # reverse read leads with the TSO
    assert rc.endswith(reverse_complement(R1_HANDLE))


def test_cb_umi_lengths():                                          # (4)(5)
    assert CB_LEN == 16 and UMI_LEN == 12 and POLYT_LEN == 30


def test_vn_reverse_complements_to_nb():                            # (6)
    # V (A/C/G) complements to B (T/G/C); N->N. Reversed order -> NB.
    assert reverse_complement("VN") == "NB"
    assert complement("V") == "B" and complement("N") == "N"


def test_full_length_ont_molecule_has_no_illumina():               # (7)
    mol = DEFAULT_CHEM.canonical_molecule("ACGT" * 4, "ACGT" * 3, "ACGT" * 50)
    assert P5 not in mol and P7 not in mol and reverse_complement(P7) not in mol


def test_illumina_branch_still_has_illumina_elements():            # (8)
    ill = load_spec(ILLUMINA_SPEC)
    blob = json.dumps(ill.data)
    assert P5 in blob and reverse_complement(P7) in blob  # P7 end appears as revcomp on the library
    assert ill.platform == "illumina"


# ---------------------------------------------------------------- simulator

def _simulate(tmp, **kw):
    err = OntErrorModel()
    defaults = dict(n=200, seed=42, source="synthetic", source_bam=None, fracs={}, orient_prob=0.5,
                    err=err, input_stage="amplified_cdna")
    defaults.update(kw)
    return simulate(NANO_SPEC, str(tmp), **defaults)


def _read_fastq(path):
    lines = list(gzip.open(path, "rt"))
    return [(lines[i][1:].strip(), lines[i + 1].strip(), lines[i + 3].strip()) for i in range(0, len(lines), 4)]


def _labels(path):
    rows = [ln.rstrip("\n").split("\t") for ln in open(path)]
    h = rows[0]
    return [dict(zip(h, r)) for r in rows[1:]]


def test_both_orientations_generated(tmp_path):                    # (9)
    _simulate(tmp_path, n=400, orient_prob=0.5, seed=1)
    labs = _labels(tmp_path / "labels.tsv")
    orients = {r["raw_orientation"] for r in labs}
    assert orients == {"forward", "reverse"}


def test_quality_length_matches_sequence(tmp_path):                # (10)
    _simulate(tmp_path, n=300, fracs={"tso_concatemer": 0.3, "trunc5": 0.2})
    for _rid, seq, qual in _read_fastq(tmp_path / "reads.fastq.gz"):
        assert len(seq) == len(qual)


def test_fixed_seed_is_byte_deterministic(tmp_path):               # (11)
    a, b = tmp_path / "a", tmp_path / "b"
    _simulate(a, seed=99)
    _simulate(b, seed=99)
    assert (a / "reads.fastq.gz").read_bytes() == (b / "reads.fastq.gz").read_bytes()
    assert (a / "labels.tsv").read_text() == (b / "labels.tsv").read_text()


def test_different_seeds_differ(tmp_path):                         # (12)
    a, b = tmp_path / "a", tmp_path / "b"
    _simulate(a, seed=1)
    _simulate(b, seed=2)
    assert (a / "reads.fastq.gz").read_bytes() != (b / "reads.fastq.gz").read_bytes()


def test_source_motifs_not_duplicated():                           # (13)
    chem = DEFAULT_CHEM
    # a source seq that already carries a leading R1 handle + trailing TSO_RC must be stripped once
    cdna = "ACGT" * 60
    dirty = chem.r1_handle + cdna + chem.tso_rc
    cleaned = normalize_source_seq(dirty, chem)
    assert cleaned == cdna
    # canonical build then has exactly one handle and one TSO_RC
    mol = chem.canonical_molecule("A" * 16, "C" * 12, cleaned)
    assert mol.count(chem.r1_handle) == 1 and mol.count(chem.tso_rc) == 1


def test_healthy_molecules_have_no_internal_tso(tmp_path):         # (14)
    _simulate(tmp_path, n=500, fracs={})  # all clean
    st = Stranding(DEFAULT_CHEM)
    for _rid, seq, _q in _read_fastq(tmp_path / "reads.fastq.gz"):
        assert st.classify(seq)["internal"] == 0


def test_failure_modes_reflected_in_labels(tmp_path):              # (15)
    _simulate(tmp_path, n=600, fracs={"tso_concatemer": 0.3, "reverse": 0.2, "trunc5": 0.1}, seed=5)
    labs = _labels(tmp_path / "labels.tsv")
    conc = [r for r in labs if r["failure_mode"] == "tso_concatemer"]
    assert conc and all(r["n_internal_signatures"] == "2" and r["affected"] == "1" for r in conc)
    assert all(r["raw_orientation"] == "reverse" for r in labs if r["failure_mode"] == "reverse")
    assert all(r["truncated"] == "1" for r in labs if r["failure_mode"] in ("trunc5", "trunc3"))


# ---------------------------------------------------------------- QC

def test_reverse_reads_detected_and_normalized():                 # (16)
    chem = DEFAULT_CHEM
    mol = chem.canonical_molecule("ACGT" * 4, "TTTT" * 3, "ACGTACGTAC" * 20)
    raw = reverse_complement(mol)
    c = Stranding(chem).classify(raw)
    assert c["orientation"] == "reverse"
    assert c["normalized"] == mol


def test_qc_clean_passes_mixed_fails(tmp_path):                    # integration
    clean, mixed = tmp_path / "clean", tmp_path / "mixed"
    _simulate(clean, n=600, fracs={}, seed=11)
    _simulate(mixed, n=600, fracs={"tso_concatemer": 0.25}, seed=11)
    r_clean = run_nanopore_qc(NANO_SPEC, str(clean / "reads.fastq.gz"),
                              labels=str(clean / "labels.tsv"), use_llm=False)
    r_mixed = run_nanopore_qc(NANO_SPEC, str(mixed / "reads.fastq.gz"),
                              labels=str(mixed / "labels.tsv"), use_llm=False)
    assert r_clean["overall"] == "pass"
    assert r_mixed["overall"] == "fail"
    ev = r_mixed["eval"]
    assert ev["recall"] >= 0.7 and ev["precision"] >= 0.7
    # long-read profile fields are present (not paired-end)
    lr = r_mixed["profile"]["long_read"]
    assert {"n_reads", "median_length", "n50", "full_length_fraction", "orientation_fraction"} <= set(lr)


def test_n50():
    assert n50([1, 2, 3, 4, 5, 100]) == 100


# ---------------------------------------------------------------- validator

def test_validator_accepts_corrected_spec():
    assert not [i for i in check_spec(json.load(open(NANO_SPEC))) if i.severity == "error"]


def test_validator_rejects_hybrid_model():                        # (17)
    spec = json.load(open(NANO_SPEC))
    bad = copy.deepcopy(spec)
    bad["final_library"]["annotated_library_sequence"] = (
        P5 + "TCTTTCCC[CELL_BARCODE:16][UMI:12]TTT[CDNA]AGATCGGAAGAGC[SAMPLE_INDEX:8]"
        + reverse_complement(P7))
    errs = [i.code for i in check_spec(bad) if i.severity == "error"]
    assert "hybrid_conflict" in errs or "ont_final_is_illumina" in errs


def test_validator_flags_unresolved_derivation():                 # (18)
    spec = json.load(open(NANO_SPEC))
    bad = copy.deepcopy(spec)
    bad["read_models"][0]["segments"][-1]["derivation"] = "reverse_complement(nonexistent_thing)"
    errs = [i.code for i in check_spec(bad) if i.severity == "error"]
    assert "unresolved_derivation" in errs


def test_validator_checks_branch_material_refs():                 # (19)
    spec = json.load(open(NANO_SPEC))
    bad = copy.deepcopy(spec)
    bad["branches"][1]["from_material"] = "does_not_exist"
    errs = [i.code for i in check_spec(bad) if i.severity == "error"]
    assert "bad_material_ref" in errs


def test_corrected_nanopore_spec_final_library_is_full_length():
    spec = json.load(open(NANO_SPEC))
    fl = spec["final_library"]["annotated_library_sequence"]
    assert P5 not in fl and "SAMPLE_INDEX" not in fl and reverse_complement(P7) not in fl
    assert fl.endswith(TSO_RC)
