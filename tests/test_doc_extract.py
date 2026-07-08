"""Offline tests for the LLM extractor's pure logic (no `claude` CLI / no billing)."""

import json

import jsonschema

from seqcolyte.dna import revcomp
from extract.doc_extract import EXTRACTION_SCHEMA, _norm, assemble_spec, cross_check, evaluate

_WHITELIST = {
    "cell_barcode_3M_feb2018": {
        "name": "3M-february-2018", "path": "whitelists/3M-february-2018.txt.gz", "md5": None,
        "md5_provenance": "computed_local_no_official_checksum", "source_url": "x", "source_note": "x",
        "size_bytes_gz": 18350152, "count": 6794880, "length": 16, "retrieved_date": None,
    }
}

R1_PRIMER = "ACACTCTTTCCCTACACGACGCTCTTCCGATCT"
P5 = "AATGATACGGCGACCACCGAGATCTACAC"
TSO = "AAGCAGTGGTATCAACGCAGAGTACATGGG"


def _synthetic_extraction():
    ann = (P5 + "TCTTTCCCTACACGACGCTCTTCCGATCT[CELL_BARCODE:16][UMI:12]"
           + "T" * 30 + "VN[CDNA]AGATCGGAAGAGCACACGTCTGAACTCCAGTCAC[SAMPLE_INDEX:8]ATCTCGTATGCCGTCTTCTGCTTG")
    return {
        "oligos": [
            {"oligo_id": "oligo_illumina_p5_adapter", "name": "Illumina P5 adapter", "role": "adapter",
             "kind": "single", "sequence": P5, "components": []},
            {"oligo_id": "oligo_illumina_truseq_read_1_primer", "name": "Illumina TruSeq Read 1 primer",
             "role": "primer", "kind": "single", "sequence": R1_PRIMER, "components": []},
            {"oligo_id": "oligo_template_switching_oligo_tso", "name": "Template Switching Oligo (TSO)",
             "role": "oligo", "kind": "single", "sequence": TSO, "components": []},
        ],
        "final_library": {"source_label": "Final library", "annotated_library_sequence": ann,
                          "strands": [{"direction": "5_to_3", "source_sequence": "5'-...-3'"}]},
    }


def test_extraction_schema_is_valid_json_schema():
    jsonschema.Draft202012Validator.check_schema(EXTRACTION_SCHEMA)


def test_assemble_spec_validates_and_derives_read_structure():
    spec = assemble_spec(_synthetic_extraction(), spec_id="10x_3p_v3",
                         assay="10x Chromium Single Cell 3' Gene Expression", chemistry_version="v3/v3.1",
                         source_doc_path="x.pdf", model="test", whitelist_block=_WHITELIST)
    assert spec["build"]["extraction_method"] == "claude_llm"
    r1 = [r for r in spec["read_structure"]["reads"] if r["read"] == "R1"][0]
    assert sum(s["length"] for s in r1["segments"]) == 28
    i1 = [r for r in spec["read_structure"]["reads"] if r["read"] == "I1"][0]
    assert i1["segments"][0]["length"] == 8
    # derived read-through adapter present (revcomp of the extracted R1 primer)
    derived = {o["oligo_id"]: o["sequence"] for o in spec["oligos"] if o["oligo_id"].endswith("readinto_adapter")}
    assert derived["oligo_r1_readinto_adapter"] == revcomp(R1_PRIMER)


def test_cross_check_matches_verified():
    cc = cross_check(_synthetic_extraction())
    assert cc["detail"]["p5"] and cc["detail"]["tso"] and cc["detail"]["truseq_read1_primer"]


def test_norm_folds_ribonucleotide_notation():
    assert _norm("AAGCAGTGGTATCAACGCAGAGTACATrGrGrG") == _norm(TSO)


def test_evaluate_against_groundtruth(tmp_path):
    ann = _synthetic_extraction()["final_library"]["annotated_library_sequence"]
    (tmp_path / "groundtruth_oligos.json").write_text(json.dumps({"oligos": [
        {"name": "Illumina P5 adapter", "sequence": P5},
        {"name": "TSO", "sequence": "AAGCAGTGGTATCAACGCAGAGTACATrGrGrG"},  # ribo notation
        {"name": "Missing primer", "sequence": "GGGGGGGGGGGGGGGGGGGG"},
    ]}))
    (tmp_path / "groundtruth_final_lib_struct.json").write_text(
        json.dumps({"libraries": [{"annotated_library_sequence": ann}]}))
    ev = evaluate(_synthetic_extraction(), tmp_path)
    assert ev["annotated_library_exact_match"] is True
    assert ev["oligo_seqs_matched"] == 2 and ev["oligo_seqs_total"] == 3  # P5 + ribo-TSO match; missing one doesn't
