from seqcolyte.spec.loader import load_spec
from conftest import SPEC_PATH


def test_oligos_carry_placeholder_tokens():
    spec = load_spec(SPEC_PATH)
    beads = spec.oligo("oligo_beads_oligo_dt")["sequence"]
    assert "[CELL_BARCODE:16]" in beads and "[UMI:12]" in beads
    pcr2 = spec.oligo("oligo_library_pcr_primer_2")["sequence"]
    assert "[SAMPLE_INDEX:8]" in pcr2


def test_readthrough_chain_refs_resolve():
    spec = load_spec(SPEC_PATH)
    for entry in spec.readthrough_chain("R2"):
        ref = entry.get("constant_ref")
        if ref is not None:
            assert spec.oligo_sequence(ref), ref  # resolves to a real sequence


def test_final_library_annotated_structure():
    spec = load_spec(SPEC_PATH)
    ann = spec.data["final_library"]["annotated_library_sequence"]
    assert ann.startswith("AATGATACGGCGACCACCGAGATCTACAC")   # P5
    assert "[CELL_BARCODE:16][UMI:12]" in ann
    assert ann.endswith("ATCTCGTATGCCGTCTTCTGCTTG")           # revcomp(P7)
    assert "[CDNA]" in ann


def test_whitelist_block():
    spec = load_spec(SPEC_PATH)
    wl = spec.whitelist("cell_barcode_3M_feb2018")
    assert wl["count"] == 6794880
    assert wl["length"] == 16
    assert wl["size_bytes_gz"] == 18350152


def test_segment_slices():
    spec = load_spec(SPEC_PATH)
    assert spec.segment_slice("R1", "cell_barcode") == slice(0, 16)
    assert spec.segment_slice("R1", "umi") == slice(16, 28)


def test_library_generation_steps():
    spec = load_spec(SPEC_PATH)
    steps = spec.data["library_generation"]
    assert [s["step"] for s in steps] == list(range(1, 9))  # 8 ordered steps
    assert "Final library structure" in steps[-1]["title"]
