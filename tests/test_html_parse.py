from extract.html_parser import parse_protocol
from extract.verified_constants import VERIFIED


def test_parse_matches_verified(html_path):
    p = parse_protocol(html_path)
    o = p.oligos
    for key in ("tso", "cdna_forward_primer", "cdna_reverse_primer", "truseq_read1_primer",
                "truseq_read2_primer", "sample_index_seq_primer", "p5", "p7"):
        assert o[key] == VERIFIED[key], key
    assert o["truseq_adapter"]["fwd"] == VERIFIED["truseq_adapter_fwd"]
    assert o["truseq_adapter"]["rev"] == VERIFIED["truseq_adapter_rev"]


def test_parse_v3_variant_umi_is_12bp(html_path):
    # v3+ beads oligo carries a 12-bp UMI token (v2 would be 10)
    beads = parse_protocol(html_path).oligos["beads_oligo_dt"]
    assert "[UMI:12]" in beads
    assert "[UMI:10]" not in beads
    assert "[CELL_BARCODE:16]" in beads


def test_parse_final_library_and_sequencing(html_path):
    p = parse_protocol(html_path)
    assert "cell barcode" in p.final_library["strand_5to3_html"].lower() or \
           p.final_library["strand_5to3_html"].startswith("5'-")
    assert p.sequencing.get("R1_cycles") == 28
    assert p.sequencing.get("i7_length") == 8
