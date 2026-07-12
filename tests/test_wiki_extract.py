"""Offline tests for the technology-wiki extraction pipeline (no network / no LLM / no corpus dependency).

Covers: the water-filling document budget, multi-doc concatenation, generic segment-type normalization,
the generic assembler (non-illumina platform + empty whitelist validating against the schema), and the
cross-check conflict detection — the last two on a hermetic temp corpus so nothing depends on the real
73-protocol collection.
"""

from __future__ import annotations

import json

from extract.pdf_text import extract_texts, _fair_caps
from extract.doc_extract import assemble_generic_spec, _generic_read_structure, _norm_seg_type
from extract.cross_check import cross_check_against_groundtruth, render_report
import extract.doc_gather as dg
from seqcolyte.spec.loader import load_spec


# ---------------------------------------------------------------- ingestion / budget

def test_fair_caps_waterfilling():
    caps = _fair_caps([100, 5000, 900000], 200000)
    assert sum(caps) <= 200000
    assert caps[0] == 100                 # small doc kept whole
    assert all(c > 0 for c in caps)       # nothing dropped


def test_extract_texts_concat_and_budget(tmp_path):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("A" * 50)
    b.write_text("B" * 5000)
    combined, log = extract_texts([a, b], char_budget=1000)
    assert "=== DOCUMENT: a.txt ===" in combined and "=== DOCUMENT: b.txt ===" in combined
    assert sum(d["kept"] for d in log) <= 1000
    small = next(d for d in log if d["name"] == "a.txt")
    big = next(d for d in log if d["name"] == "b.txt")
    assert not small["truncated"] and big["truncated"]


# ---------------------------------------------------------------- generic assembly

def test_seg_type_normalization():
    assert _norm_seg_type("cell_barcode") == "barcode"
    assert _norm_seg_type("cdna") == "insert"
    assert _norm_seg_type("spacer") == "constant"
    assert _norm_seg_type("umi") == "umi"
    assert _norm_seg_type("polyA") == "polyA"


def test_generic_read_structure_stub_and_order():
    stub = _generic_read_structure({})
    assert stub["reads"][0]["read"] == "R1" and stub["reads"][0]["segments"][0]["type"] == "insert"
    rs = _generic_read_structure({"read_structure": {"reads": [
        {"read": "L1", "segments": [{"name": "bc", "type": "cell_barcode", "length": 16},
                                    {"name": "x", "type": "cdna"}]}]}})
    segs = rs["reads"][0]["segments"]
    assert [s["type"] for s in segs] == ["barcode", "insert"]
    assert [s["order"] for s in segs] == [0, 1]
    assert "length" not in segs[1]                 # non-integer length dropped


def _mock_extraction(platform="pacbio"):
    return {
        "platform": platform,
        "oligos": [{"oligo_id": "o1", "name": "BC", "role": "barcode", "kind": "single",
                    "sequence": "[CELL_BARCODE:16]", "components": []}],
        "final_library": {"source_label": "L", "annotated_library_sequence": "[CELL_BARCODE:16][UMI:10][CDNA]",
                          "strands": [], "annotation_lines": []},
        "library_generation": [{"step": 1, "title": "lyse", "summary": "lyse cells"}],
        "read_structure": {"reads": [{"read": "L1", "segments": [{"name": "bc", "type": "cell_barcode", "length": 16}]}]},
        "title": "Mock-seq", "description": "A mock assay.",
        "publication": {"year": 2020, "authors": [{"name": "A. Author", "corresponding": True, "email": "a@x.org"}]},
    }


def test_assemble_generic_spec_validates(tmp_path):
    spec = assemble_generic_spec(
        _mock_extraction("pacbio"), spec_id="mock_seq", assay="Mock-seq", chemistry_version="",
        source_docs=[{"doc_id": "d", "title": "t", "url": None, "path": None, "retrieved_date": None}],
        reference={"kind": "paper", "label": "Author 2020", "path": None, "url": None, "doi": "10.1/x"})
    assert spec["platform"] == "pacbio" and spec["whitelists"] == {}
    assert spec["title"] == "Mock-seq" and spec["publication"]["year"] == 2020
    p = tmp_path / "s.json"
    p.write_text(json.dumps(spec))
    load_spec(str(p))  # raises if it doesn't validate against the schema


def test_assemble_generic_spec_defaults_platform_and_oligos(tmp_path):
    ex = {"platform": "weird", "oligos": [], "final_library": {"annotated_library_sequence": "[CDNA]"}}
    spec = assemble_generic_spec(ex, spec_id="x", assay="X", chemistry_version="",
                                 source_docs=[{"doc_id": "d", "title": "t", "url": None, "path": None, "retrieved_date": None}])
    assert spec["platform"] == "illumina"          # unknown platform falls back
    assert len(spec["oligos"]) == 1                 # schema minItems 1 satisfied by a stub
    p = tmp_path / "s.json"
    p.write_text(json.dumps(spec))
    load_spec(str(p))


# ---------------------------------------------------------------- hermetic corpus: doc_gather + cross_check

def _make_corpus(root):
    proto = root / "protocols" / "foo_seq"
    proto.mkdir(parents=True)
    (proto / "foo_paper.pdf").write_bytes(b"%PDF-1.4 fake")
    (proto / "foo_supp.xlsx").write_bytes(b"fake")
    (root / "protocols" / "SOURCE_MANIFEST.tsv").write_text(
        "folder\tlocal_file\tkind\ttitle\tdoi\tlanding_url\tdirect_url\tbytes\tsha256\tnotes\n"
        "foo_seq\tfoo_seq/foo_paper.pdf\tpaper\tFoo paper\t10.1/foo\thttps://x\t\t100\t\t\n")
    (root / "protocol_split.tsv").write_text("Split\tprotocol_name\neval\tFoo-seq\n")
    (proto / "groundtruth_oligos.json").write_text(json.dumps(
        {"oligos": [{"name": "BC", "sequence": "ACGTACGT"}, {"name": "P", "sequence": "TTTTGGGG"}]}))
    (proto / "groundtruth_final_lib_struct.json").write_text(json.dumps(
        {"libraries": [{"annotated_library_sequence": "ACGT[CELL_BARCODE:12][UMI:8]", "source_html_file": "Foo.html"}]}))
    return proto


def test_doc_gather_scans_filesystem(tmp_path, monkeypatch):
    root = tmp_path / "corpus"
    _make_corpus(root)
    monkeypatch.setenv("SEQCOLYTE_PROTOCOLS", str(root))
    assert [t.folder for t in dg.list_technologies()] == ["foo_seq"]
    t = dg.get_technology("foo_seq")
    assert {d.name for d in t.docs} == {"foo_paper.pdf", "foo_supp.xlsx"}
    assert t.split == "eval" and t.doi == "10.1/foo"
    assert t.docs[0].kind == "paper"          # canonical source leads (rank order)


def test_cross_check_flags_recall_and_length(tmp_path, monkeypatch):
    root = tmp_path / "corpus"
    _make_corpus(root)
    monkeypatch.setenv("SEQCOLYTE_PROTOCOLS", str(root))
    t = dg.get_technology("foo_seq")
    # extraction matches 1/2 GT oligos and has a CB length of 11 vs the ground-truth 12
    extraction = {"oligos": [{"name": "BC", "sequence": "ACGTACGT", "components": []}],
                  "final_library": {"annotated_library_sequence": "ACGT[CELL_BARCODE:11][UMI:8]"}}
    cc = cross_check_against_groundtruth(extraction, t.groundtruth_dir)
    assert cc["oligo_seq_recall"] == 0.5 and cc["big_conflict"]
    assert cc["barcode_umi_length_diffs"]["CELL_BARCODE"] == {"extracted": [11], "groundtruth": [12]}
    md = render_report([{"folder": "foo_seq", "title": "Foo-seq", "crosscheck": cc}])
    assert "foo_seq" in md and "length disagreement" in md.lower()


def test_cross_check_no_groundtruth(tmp_path):
    cc = cross_check_against_groundtruth({"oligos": []}, tmp_path)  # empty dir -> no GT files
    assert cc["status"] == "no_groundtruth" and cc["big_conflict"] is False
