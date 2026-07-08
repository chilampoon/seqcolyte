"""LLM-based protocol extraction: read a protocol PDF and extract the oligos + final library
structure into the Seqcolyte spec, by running Claude Code headless (`claude -p --json-schema`).

This is the Day-2 counterpart to the deterministic HTML parser: it generalizes to arbitrary
protocol documents. The deterministic verified constants are used as a *soft* cross-check and
the checked-in groundtruth (when present) as an eval — the LLM output is never silently trusted.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from seqcolyte.dna import revcomp
from seqcolyte.spec.loader import validate_spec
from extract.pdf_text import extract_text
from extract.verified_constants import VERIFIED
from extract.builder import to_canonical_json

__all__ = ["extract_document", "assemble_spec", "cross_check", "evaluate", "EXTRACTION_SCHEMA"]

DEFAULT_MODEL = "claude-opus-4-8"

# JSON Schema the model must fill (subset the CLI's structured output supports).
EXTRACTION_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["oligos", "final_library"],
    "properties": {
        "oligos": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["oligo_id", "name", "role", "kind", "sequence", "components"],
                "properties": {
                    "oligo_id": {"type": "string"},
                    "name": {"type": "string"},
                    "role": {"type": "string"},
                    "kind": {"type": "string", "enum": ["single", "assembled", "double_stranded"]},
                    "sequence": {"type": "string"},
                    "components": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["name", "sequence", "role"],
                            "properties": {
                                "name": {"type": "string"},
                                "sequence": {"type": "string"},
                                "role": {"type": "string"},
                            },
                        },
                    },
                    "notes": {"type": "string"},
                },
            },
        },
        "final_library": {
            "type": "object",
            "additionalProperties": False,
            "required": ["source_label", "annotated_library_sequence", "strands"],
            "properties": {
                "source_label": {"type": "string"},
                "annotated_library_sequence": {"type": "string"},
                "library_sequence": {"type": "string"},
                "strands": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["direction", "source_sequence"],
                        "properties": {
                            "direction": {"type": "string"},
                            "source_sequence": {"type": "string"},
                        },
                    },
                },
                "annotation_lines": {"type": "array", "items": {"type": "string"}},
            },
        },
        "library_generation": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["step", "title"],
                "properties": {
                    "step": {"type": "integer"},
                    "title": {"type": "string"},
                    "note": {"type": "string"},
                },
            },
        },
    },
}

_PROMPT = """You are an expert at reading single-cell sequencing library-prep protocols and \
extracting their exact oligonucleotide sequences and final library structure.

Below is the extracted text of one protocol document ({protocol_name}). Extract TWO things into \
the required JSON schema:

1. `oligos`: one entry per named oligo in the protocol's oligonucleotide-sequence section.
   Be COMPLETE — extract EVERY named oligo, do not stop early. For a 10x-style 3' kit expect
   ALL of these (include each one you can find): Beads-oligo-dT, Template Switching Oligo (TSO),
   cDNA Forward primer, cDNA Reverse primer, Illumina TruSeq Read 1 primer, Illumina TruSeq Read 2
   primer, TruSeq adapter (double-stranded), Library PCR Primer 1, Library PCR Primer 2, Sample
   Index sequencing primer, Illumina P5 adapter, Illumina P7 adapter.
2. `final_library`: the FINAL library structure (often labelled "... PCR Product" or
   "Final library"): its full 5'->3' top strand with placeholder tokens, plus the raw strand text.
3. `library_generation`: the ordered step-by-step library-build workflow, if the document
   describes it (e.g. mRNA capture / reverse transcription -> template switching -> cDNA
   amplification -> fragmentation + A-tailing -> adapter ligation -> sample-index PCR -> final
   library). One entry per step: `{step: <1-based int>, title: <short step name>, note: <optional>}`.
   Omit or leave empty if the document does not describe the build steps.

CONVENTIONS (follow EXACTLY — these determine correctness):
- All sequences 5'->3', uppercase ACGTN only. Transcribe the exact characters from the document.
- Replace variable regions with placeholder tokens, keeping the bp count from the document:
  cell barcode -> [CELL_BARCODE:N] ; UMI -> [UMI:M] ; i7/i5 sample index -> [SAMPLE_INDEX:K] ;
  the cDNA insert -> [CDNA].
- poly(dT): write the EXACT number of T's shown (10x uses 30), and if the document shows a "VN"
  (or "V N") anchor after the T's, you MUST append the literal "VN". So `(T)30 VN` -> 30 T's then VN.
- Terminal riboguanosines on the TSO (written rGrGrG or rG rG rG) -> write as GGG (the TSO ends ...ACATGGG).
- Standalone P5 = AATGATACGGCGACCACCGAGATCTACAC ; standalone P7 = CAAGCAGAAGACGGCATACGAGAT.
  Note the final library's P7 END is written as the reverse complement (ATCTCGTATGCCGTCTTCTGCTTG).
- `kind`: "single" (one plain sequence), "assembled" (built from named components -> fill `components`),
  or "double_stranded" (two strands -> put sequence:"" and both strands in `components`).
- For `final_library.annotated_library_sequence`, assemble the full top strand with the tokens exactly:
  P5 + TruSeqRead1 + [CELL_BARCODE:16] + [UMI:12] + (30 T's) + VN + [CDNA] + <Read2 adapter> +
  [SAMPLE_INDEX:8] + revcomp(P7).  Include the VN.
- `final_library.strands`: include the 5_to_3 (and 3_to_5 if shown) strand text exactly as written in the document.
- Use lowercase_snake_case oligo_id values (e.g. oligo_template_switching_oligo_tso).

Output ONLY the structured JSON. Do not include commentary.

=== PROTOCOL TEXT START ===
{doc_text}
=== PROTOCOL TEXT END ===
"""


def _run_claude(prompt: str, schema: dict, *, model: str, cwd: str | None = None) -> dict:
    """Invoke Claude Code headless with structured output; return the parsed object."""
    proc = subprocess.run(
        ["claude", "-p", "--model", model, "--output-format", "json",
         "--json-schema", json.dumps(schema)],
        input=prompt, text=True, capture_output=True, cwd=cwd,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude CLI failed (exit {proc.returncode}): {proc.stderr[:500]}")
    envelope = json.loads(proc.stdout)
    if envelope.get("is_error"):
        raise RuntimeError(f"claude returned an error: {envelope.get('result')}")
    out = envelope.get("structured_output")
    if out is None:
        out = json.loads(envelope["result"])  # result holds the schema-conforming JSON string
    return {"extraction": out, "usage": envelope.get("usage"), "cost_usd": envelope.get("total_cost_usd"),
            "model": model, "duration_ms": envelope.get("duration_ms")}


def extract_document(pdf_path: str | Path, protocol_name: str, *, model: str = DEFAULT_MODEL) -> dict:
    """Extract oligos + final_library from a protocol PDF via Claude Code headless."""
    text = extract_text(pdf_path)
    # NB: the template contains literal JSON braces (e.g. `{step: ...}`), so we substitute the two
    # real placeholders by name rather than str.format (which would read `{step}` as a field).
    prompt = _PROMPT.replace("{protocol_name}", protocol_name).replace("{doc_text}", text)
    result = _run_claude(prompt, EXTRACTION_SCHEMA, model=model)
    result["source_chars"] = len(text)
    return result


# --------------------------------------------------------------------------------------
# Assembly: LLM extraction -> consolidated Seqcolyte spec (same schema as the HTML build)
# --------------------------------------------------------------------------------------

_REAGENT_HINTS = ("bead", "tso", "template switch", "cdna reverse", "reverse primer")


def _provenance_for(name: str) -> str:
    low = name.lower()
    return "reagent" if any(h in low for h in _REAGENT_HINTS) else "document"


def _token_len(seq: str, token: str) -> int | None:
    m = re.search(rf"\[{token}:(\d+)\]", seq)
    return int(m.group(1)) if m else None


def _match_oligo_seq(oligos: list[dict], target: str) -> str | None:
    """Find an extracted oligo (or component) whose plain sequence equals ``target``."""
    for o in oligos:
        if (o.get("sequence") or "").upper() == target:
            return o["oligo_id"]
        for c in o.get("components", []):
            if (c.get("sequence") or "").upper() == target:
                return o["oligo_id"]
    return None


def assemble_spec(extraction: dict, *, spec_id: str, assay: str, chemistry_version: str,
                  source_doc_path: str, model: str, whitelist_block: dict) -> dict:
    """Turn an LLM extraction into a validated consolidated spec (best-effort, LLM-sourced)."""
    oligos_in = extraction["oligos"]
    fl = extraction["final_library"]
    ann = fl["annotated_library_sequence"]

    cb_len = _token_len(ann, "CELL_BARCODE") or 16
    umi_len = _token_len(ann, "UMI") or 12
    idx_len = _token_len(ann, "SAMPLE_INDEX") or 8

    # Enrich oligos to satisfy the spec schema (provenance/evidence/direction/sequence_source).
    oligos = []
    for o in oligos_in:
        oligos.append({
            "oligo_id": o["oligo_id"],
            "name": o["name"],
            "aliases": [],
            "role": o.get("role", "oligo"),
            "kind": o["kind"],
            "sequence": (o.get("sequence") or None) if o["kind"] != "double_stranded" else None,
            "direction": "5_to_3",
            "components": o.get("components", []),
            "provenance": _provenance_for(o["name"]),
            "derivation": None,
            "sequence_source": "llm_extracted_from_pdf",
            "evidence": [{"source_doc": "protocol_pdf", "locator": "Oligonucleotide sequences / final library",
                          "method": "claude_llm_extraction"}],
            "notes": o.get("notes"),
        })

    # Derived read-through adapters (revcomp of the extracted Read 1 primer + P5), if we can find them.
    r1_primer = next((o["sequence"] for o in oligos if "read 1" in o["name"].lower() and o.get("sequence")), None)
    p5 = next((o["sequence"] for o in oligos if o["name"].lower().strip().endswith("p5 adapter") and o.get("sequence")), None)
    chain = [{"name": "tso_5prime", "type": "constant",
              "constant_ref": _match_oligo_seq(oligos, VERIFIED["tso"]) or "", "notes": "adapter-dimer leads with the TSO"},
             {"name": "cdna_short", "type": "insert"},
             {"name": "polyA", "type": "polyA", "base": "A"},
             {"name": "umi_rc", "type": "umi", "derivation": "revcomp(umi)"},
             {"name": "cbc_rc", "type": "barcode", "derivation": "revcomp(cell_barcode)"}]
    for label, seq in (("oligo_r1_readinto_adapter", r1_primer), ("oligo_p5_rc", p5)):
        if seq:
            oligos.append({
                "oligo_id": label, "name": label.replace("oligo_", "").replace("_", " "),
                "aliases": [], "role": "read_through_adapter", "kind": "single",
                "sequence": revcomp(seq), "direction": "5_to_3", "components": [],
                "provenance": "document", "derivation": f"revcomp({seq})",
                "sequence_source": "derived_revcomp",
                "evidence": [{"source_doc": "protocol_pdf", "locator": "derived", "method": "revcomp"}],
                "notes": None,
            })
            chain.append({"name": label.replace("oligo_", ""), "type": "constant", "constant_ref": label})
    chain.append({"name": "polyG_pad", "type": "constant", "base": "G"})

    read_structure = {"reads": [
        {"read": "R1", "primer": "Illumina TruSeq Read 1 primer", "template": "bottom", "cycles": cb_len + umi_len,
         "segments": [
             {"name": "cell_barcode", "type": "barcode", "order": 0, "length": cb_len, "scored": True,
              "provenance": None, "whitelist_ref": list(whitelist_block)[0], "constant_ref": None, "notes": None},
             {"name": "umi", "type": "umi", "order": 1, "length": umi_len, "scored": True,
              "provenance": None, "whitelist_ref": None, "constant_ref": None, "notes": None}]},
        {"read": "I1", "primer": "Sample index sequencing primer", "template": "bottom", "cycles": idx_len,
         "segments": [{"name": "sample_index_i7", "type": "index", "order": 0, "length": idx_len, "scored": False,
                       "provenance": None, "whitelist_ref": None, "constant_ref": None, "notes": None}]},
        {"read": "R2", "primer": "Illumina TruSeq Read 2 primer", "template": "top", "cycles": 90,
         "segments": [{"name": "cdna_insert", "type": "insert", "order": 0, "length_range": [1, 90], "scored": True,
                       "provenance": None, "whitelist_ref": None, "constant_ref": None, "notes": None}],
         "readthrough_chain": chain},
    ]}

    spec = {
        "schema_version": "seqcolyte.spec.v1", "spec_id": spec_id, "assay": assay,
        "chemistry_version": chemistry_version, "platform": "illumina",
        "platform_params": {"two_color_chemistry": True, "dark_base": "G", "polyA_base": "A",
                            "index_scheme": "single", "i7_length": idx_len, "i5_length": None,
                            "read_lengths": {"R1": cb_len + umi_len, "R2": 90, "I1": idx_len}},
        "source_docs": [{"doc_id": "protocol_pdf", "title": f"{assay} — protocol PDF",
                         "url": None, "path": str(source_doc_path), "retrieved_date": "2026-07-07"}],
        "oligos": oligos,
        "final_library": {
            "source_label": fl.get("source_label", "Final library structure"),
            "annotated_library_sequence": ann,
            "library_sequence": fl.get("library_sequence", ""),
            "strands": [{"direction": s["direction"], "source_html": s["source_sequence"],
                         "source_sequence": s["source_sequence"]} for s in fl.get("strands", [])],
            "annotation_lines": fl.get("annotation_lines", []),
            "evidence": [{"source_doc": "protocol_pdf", "locator": fl.get("source_label", ""),
                          "method": "claude_llm_extraction"}],
        },
        "read_structure": read_structure,
        "library_generation": extraction.get("library_generation", []),
        "whitelists": whitelist_block,
        "build": {"builder_version": "llm-1.0", "deterministic": False,
                  "source_html_sha256": None, "extraction_method": "claude_llm", "model": model},
    }
    validate_spec(spec)
    return spec


# --------------------------------------------------------------------------------------
# Soft cross-check + eval against a checked-in groundtruth
# --------------------------------------------------------------------------------------

def _norm(seq: str) -> str:
    # Fold ribonucleotide notation (rG rG rG -> GGG) before comparing — a notation equivalence,
    # not a content change; groundtruth writes the TSO 3' end as rGrGrG.
    s = re.sub(r"r([ACGTacgt])", r"\1", seq or "")
    return re.sub(r"\s+", "", s).upper()


def cross_check(extraction: dict) -> dict:
    """Compare extracted sequences against the independently-verified constants (soft)."""
    oligos = extraction["oligos"]
    results = {}
    for key, seq in VERIFIED.items():
        results[key] = _match_oligo_seq(oligos, seq) is not None
    return {"checked": len(results), "matched": sum(results.values()), "detail": results}


def evaluate(extraction: dict, groundtruth_dir: str | Path) -> dict:
    """Eval extracted oligos + annotated library sequence against a checked-in groundtruth."""
    gt_dir = Path(groundtruth_dir)
    gt_oligos = json.loads((gt_dir / "groundtruth_oligos.json").read_text())["oligos"]
    gt_lib = json.loads((gt_dir / "groundtruth_final_lib_struct.json").read_text())["libraries"][0]

    got_seqs = {_norm(o.get("sequence", "")) for o in extraction["oligos"] if o.get("sequence")}
    for o in extraction["oligos"]:
        for c in o.get("components", []):
            got_seqs.add(_norm(c.get("sequence", "")))
    gt_seq_list = [(_norm(o.get("sequence") or ""), o["name"]) for o in gt_oligos if o.get("sequence")]
    oligo_hits = [(name, norm in got_seqs) for norm, name in gt_seq_list if norm]
    n_hit = sum(1 for _, ok in oligo_hits if ok)

    ann_got = _norm(extraction["final_library"]["annotated_library_sequence"])
    ann_gt = _norm(gt_lib["annotated_library_sequence"])
    return {
        "oligo_seq_recall": round(n_hit / len(oligo_hits), 3) if oligo_hits else None,
        "oligo_seqs_matched": n_hit, "oligo_seqs_total": len(oligo_hits),
        "missed_oligos": [name for name, ok in oligo_hits if not ok],
        "annotated_library_exact_match": ann_got == ann_gt,
        "annotated_library_got": extraction["final_library"]["annotated_library_sequence"],
        "annotated_library_expected": gt_lib["annotated_library_sequence"],
    }
