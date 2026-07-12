"""Offline test that the extraction assembler carries the new spec metadata fields through validation.

No network / no LLM: we feed a mock extraction dict (the shape Claude returns) straight into
``assemble_spec`` and assert the resulting spec carries title/description/reference/publication + a
per-step ``summary`` and still passes jsonschema validation via ``load_spec``.
"""

from __future__ import annotations

import json
import tempfile

from extract.doc_extract import EXTRACTION_SCHEMA, assemble_spec
from seqcolyte.spec.loader import load_spec

WHITELIST_BLOCK = {
    "cell_barcode_3M_feb2018": {
        "name": "3M-february-2018", "path": "whitelists/3M-february-2018.txt.gz",
        "count": 6794880, "length": 16,
    }
}

MOCK_EXTRACTION = {
    "title": "10x 3' scRNA-seq (v3.1)",
    "description": "Droplet single-cell 3' gene expression on Illumina. Cells are partitioned into GEMs, "
                   "barcoded during reverse transcription, and the amplified cDNA is made into a P5/P7 library.",
    "oligos": [
        {"oligo_id": "oligo_beads_oligo_dt", "name": "Beads-oligo-dT", "role": "capture primer",
         "kind": "single",
         "sequence": "CTACACGACGCTCTTCCGATCT[CELL_BARCODE:16][UMI:12]TTTTTTTTTTTTTTTTTTTTTTTTTTTTTTVN",
         "components": []},
    ],
    "final_library": {
        "source_label": "Final library structure",
        "annotated_library_sequence": ("AATGATACGGCGACCACCGAGATCTACACTCTTTCCCTACACGACGCTCTTCCGATCT"
                                       "[CELL_BARCODE:16][UMI:12][CDNA]AGATCGGAAGAGCACACGTCTGAACTCCAGTCAC"
                                       "[SAMPLE_INDEX:8]ATCTCGTATGCCGTCTTCTGCTTG"),
        "strands": [{"direction": "5_to_3", "source_sequence": "AATGATACGG..."}],
        "annotation_lines": [],
    },
    "library_generation": [
        {"step": 1, "title": "GEM-RT", "summary": "Barcode mRNA during reverse transcription in droplets.",
         "note": "A much longer verbose note about the GEM-RT chemistry that should not be the default view."},
        {"step": 2, "title": "cDNA amplification", "summary": "PCR-amplify full-length cDNA to build mass."},
    ],
    "publication": {
        "year": 2017,
        "original_publication": {"title": "Massively parallel digital transcriptional profiling of single cells",
                                 "journal": "Nature Communications", "doi": "10.1038/ncomms14049", "url": None},
        "authors": [
            {"name": "Grace X. Y. Zheng", "corresponding": False},
            {"name": "Jason H. Bielas", "corresponding": True, "email": "jbielas@fredhutch.org"},
        ],
        "throughput": {"summary": "up to ~10,000 cells per channel", "cells": "500–10,000"},
        "statistical_model": "Negative binomial / Poisson for UMI counts",
        "other": [{"label": "Partitioning", "value": "GEMs (Gel Beads-in-emulsion)"}],
    },
}


def _assemble(doc_path="/uploads/protocol.pdf"):
    return assemble_spec(
        MOCK_EXTRACTION, spec_id="mock_10x_3p", assay="10x Chromium Single Cell 3' Gene Expression",
        chemistry_version="v3.1", source_doc_path=doc_path, model="test", whitelist_block=WHITELIST_BLOCK,
    )


def test_extraction_schema_declares_new_fields():
    props = EXTRACTION_SCHEMA["properties"]
    assert {"title", "description", "publication"} <= set(props)
    assert "summary" in props["library_generation"]["items"]["properties"]


def test_assemble_spec_carries_metadata():
    spec = _assemble()
    assert spec["title"] == "10x 3' scRNA-seq (v3.1)"
    assert spec["description"].startswith("Droplet single-cell")
    assert spec["publication"]["year"] == 2017
    corr = [a for a in spec["publication"]["authors"] if a.get("corresponding")]
    assert corr and corr[0]["email"] == "jbielas@fredhutch.org"
    assert spec["publication"]["statistical_model"]
    # per-step summary flows through
    assert spec["library_generation"][0]["summary"].startswith("Barcode mRNA")


def test_reference_points_at_source():
    spec = _assemble("/uploads/my protocol.pdf")
    ref = spec["reference"]
    assert ref["kind"] == "uploaded_file"
    assert ref["path"] == "/uploads/my protocol.pdf"
    assert ref["label"] == "my protocol.pdf"
    assert ref["doi"] == "10.1038/ncomms14049"  # pulled from publication.original_publication


def test_assembled_spec_passes_jsonschema():
    spec = _assemble()
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(spec, f)
        path = f.name
    loaded = load_spec(path)  # raises if jsonschema validation fails
    assert loaded.data["title"] == "10x 3' scRNA-seq (v3.1)"


def test_no_publication_still_valid():
    """A protocol with no publication info must still assemble + validate (fields simply absent)."""
    extraction = {k: v for k, v in MOCK_EXTRACTION.items() if k not in ("title", "description", "publication")}
    spec = assemble_spec(
        extraction, spec_id="mock", assay="assay", chemistry_version="v3.1",
        source_doc_path="/x.pdf", model="test", whitelist_block=WHITELIST_BLOCK,
    )
    assert "publication" not in spec and "title" not in spec
    assert spec["reference"]["path"] == "/x.pdf"
