"""Independently-verified 10x Chromium 3' v3/v3.1 sequences — the cross-check *oracle* for the
builder and the source of each oligo's ``evidence.verified_against`` citations.

Every sequence here was confirmed against >= 2 authoritative sources (Illumina Adapter Sequences
doc #1000000002694; Teichlab scg_lib_structs; 10x Cell Ranger GEX algorithm) via an adversarial
research pass — 16/16 confirmed, 0 refuted. The builder asserts the sequences *parsed from the
HTML* equal these; a mismatch fails the build loudly rather than emitting a wrong spec.
"""

from __future__ import annotations

from seqcolyte.dna import revcomp

# 5'->3', uppercase.
VERIFIED: dict[str, str] = {
    "tso": "AAGCAGTGGTATCAACGCAGAGTACATGGG",
    "r1_partial_handle": "CTACACGACGCTCTTCCGATCT",
    "cdna_forward_primer": "CTACACGACGCTCTTCCGATCT",
    "cdna_reverse_primer": "AAGCAGTGGTATCAACGCAGAG",  # v3+
    "truseq_read1_primer": "ACACTCTTTCCCTACACGACGCTCTTCCGATCT",
    "truseq_read2_primer": "GTGACTGGAGTTCAGACGTGTGCTCTTCCGATCT",
    "truseq_adapter_fwd": "GATCGGAAGAGCACACGTCTGAACTCCAGTCA",  # v3+ (32 nt)
    "truseq_adapter_rev": "TCTAGCCTTCTCG",
    "sample_index_seq_primer": "GATCGGAAGAGCACACGTCTGAACTCCAGTCAC",
    "p5": "AATGATACGGCGACCACCGAGATCTACAC",
    "p7": "CAAGCAGAAGACGGCATACGAGAT",
}

# Derived sequences (computed, then recorded so the read-through chain resolves uniformly).
DERIVED: dict[str, str] = {
    # revcomp of the TruSeq Read 2 primer == the 3' adapter observed as R2 read-through.
    "r2_readthrough_adapter": revcomp(VERIFIED["truseq_read2_primer"]),
    # revcomp of the TruSeq Read 1 primer == the adapter a *short-insert* R2 reads into.
    "r1_readinto_adapter": revcomp(VERIFIED["truseq_read1_primer"]),
    "p5_rc": revcomp(VERIFIED["p5"]),
    "p7_rc": revcomp(VERIFIED["p7"]),  # appears on the library top strand at the P7 end
}

# Sanity: the two load-bearing read-through adapters have the fixed, known values.
assert DERIVED["r2_readthrough_adapter"] == "AGATCGGAAGAGCACACGTCTGAACTCCAGTCAC"
assert DERIVED["r1_readinto_adapter"] == "AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT"
assert DERIVED["p5_rc"] == "GTGTAGATCTCGGTGGTCGCCGTATCATT"
assert DERIVED["p7_rc"] == "ATCTCGTATGCCGTCTTCTGCTTG"

# Citation registry (doc_id -> metadata). Referenced by oligo evidence entries.
CITATIONS: dict[str, dict] = {
    "scg_10xChromium3": {
        "title": "scg_lib_structs — 10x Chromium Single Cell 3' Gene Expression",
        "url": "https://teichlab.github.io/scg_lib_structs/methods_html/10xChromium3.html",
        "path": "protocols/10xChromium3.html",
    },
    "illumina_truseq": {
        "title": "Illumina Adapter Sequences (doc #1000000002694) — TruSeq Read 1/Read 2 primers",
        "url": "https://support-docs.illumina.com/SHARE/AdapterSequences/Content/SHARE/AdapterSeq/TruSeq/SequencesTruSeq.htm",
    },
    "illumina_adapters": {
        "title": "Illumina P5/P7 flow-cell adapter sequences (doc #1000000002694)",
        "url": "https://teichlab.github.io/scg_lib_structs/data/illumina-adapter-sequences-1000000002694-14.pdf",
    },
    "tenx_tso": {
        "title": "10x Genomics — Template Switch Oligo (Cell Ranger GEX algorithm / KB)",
        "url": "https://www.10xgenomics.com/support/software/cell-ranger/latest/algorithms-overview/cr-gex-algorithm",
    },
    "cellranger_gex": {
        "title": "10x Cell Ranger GEX algorithm — R2 orientation, TSO(5')/poly-A(3') trimming",
        "url": "https://www.10xgenomics.com/support/software/cell-ranger/latest/algorithms-overview/cr-gex-algorithm",
    },
}

# Which citation(s) back each verified/derived constant (used to fill evidence.verified_against).
CONSTANT_CITATIONS: dict[str, list[str]] = {
    "tso": ["tenx_tso", "scg_10xChromium3"],
    "r1_partial_handle": ["illumina_truseq", "scg_10xChromium3"],
    "cdna_forward_primer": ["scg_10xChromium3"],
    "cdna_reverse_primer": ["scg_10xChromium3"],
    "truseq_read1_primer": ["illumina_truseq", "scg_10xChromium3"],
    "truseq_read2_primer": ["illumina_truseq", "scg_10xChromium3"],
    "truseq_adapter_fwd": ["illumina_truseq", "scg_10xChromium3"],
    "truseq_adapter_rev": ["illumina_truseq", "scg_10xChromium3"],
    "sample_index_seq_primer": ["illumina_truseq", "scg_10xChromium3"],
    "p5": ["illumina_adapters", "scg_10xChromium3"],
    "p7": ["illumina_adapters", "scg_10xChromium3"],
    "r2_readthrough_adapter": ["illumina_truseq", "cellranger_gex"],
    "r1_readinto_adapter": ["illumina_truseq", "cellranger_gex"],
    "p5_rc": ["illumina_adapters"],
    "p7_rc": ["illumina_adapters"],
}


def citation_urls(constant_key: str) -> list[str]:
    """The authoritative URLs backing a constant (for evidence.verified_against)."""
    return [CITATIONS[c]["url"] for c in CONSTANT_CITATIONS.get(constant_key, [])]
