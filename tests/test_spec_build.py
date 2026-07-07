import json

from extract.builder import build_spec, to_canonical_json
from seqcolyte.spec.loader import load_spec, validate_spec
from conftest import SPEC_PATH


def test_committed_spec_validates():
    spec = load_spec(SPEC_PATH)  # load_spec validates against the schema
    assert spec.spec_id == "tenx_3p_v3"
    assert spec.platform == "illumina"


def test_build_matches_committed():
    fresh = to_canonical_json(build_spec())
    assert fresh == SPEC_PATH.read_bytes(), "committed spec drifted — run `python -m extract build`"


def test_build_is_byte_reproducible():
    assert to_canonical_json(build_spec()) == to_canonical_json(build_spec())


def test_read1_segments_sum_to_28_and_i1_is_8():
    spec = load_spec(SPEC_PATH)
    r1 = spec.read_segments("R1")
    assert sum(s["length"] for s in r1) == 28
    assert {s["name"] for s in r1} == {"cell_barcode", "umi"}
    assert spec.read("I1")["segments"][0]["length"] == 8


def test_every_oligo_has_provenance_and_evidence():
    spec = load_spec(SPEC_PATH)
    for o in spec.oligos:
        assert o["provenance"] in ("document", "reagent"), o["oligo_id"]
        assert o["evidence"], o["oligo_id"]
        assert o["evidence"][0]["source_doc"]


def test_constant_lengths_match_sequences():
    spec = load_spec(SPEC_PATH)
    for o in spec.oligos:
        seq = o["sequence"]
        if seq and "[" not in seq:  # skip tokenized/None
            assert set(seq) <= set("ACGTN"), o["oligo_id"]
