from seqcolyte.dna import complement, homopolymer, is_dna, revcomp
from extract.verified_constants import DERIVED, VERIFIED


def test_revcomp_known_vectors():
    assert revcomp("AAGC") == "GCTT"
    assert revcomp("ACGTN") == "NACGT"
    assert revcomp("") == ""


def test_revcomp_is_involution():
    for seq in ("A", "ACGT", "AAGCAGTGGTATCAACGCAGAGTACATGGG", "NNNACGTN"):
        assert revcomp(revcomp(seq)) == seq


def test_complement():
    assert complement("ACGTN") == "TGCAN"


def test_spec_revcomp_relationships():
    # the load-bearing read-through adapters are exact reverse complements
    assert revcomp(VERIFIED["truseq_read2_primer"]) == DERIVED["r2_readthrough_adapter"]
    assert revcomp(VERIFIED["truseq_read1_primer"]) == DERIVED["r1_readinto_adapter"]
    assert revcomp(VERIFIED["p5"]) == DERIVED["p5_rc"]
    assert DERIVED["r2_readthrough_adapter"] == "AGATCGGAAGAGCACACGTCTGAACTCCAGTCAC"
    assert DERIVED["r1_readinto_adapter"] == "AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT"


def test_is_dna():
    assert is_dna("ACGT")
    assert is_dna("ACGTN")
    assert not is_dna("ACGTN", allow_n=False)
    assert not is_dna("")
    assert not is_dna("ACGX")


def test_homopolymer():
    assert homopolymer("A", 5) == "AAAAA"
    assert homopolymer("G", 0) == ""
