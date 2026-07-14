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
from extract.pdf_text import extract_text, extract_texts
from extract.verified_constants import VERIFIED
from extract.builder import to_canonical_json

__all__ = ["extract_document", "extract_documents", "assemble_spec", "assemble_generic_spec",
           "cross_check", "evaluate", "EXTRACTION_SCHEMA"]

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
                    "summary": {"type": "string"},
                    "note": {"type": "string"},
                    "product": {"type": "string"},
                },
            },
        },
        "library_sequencing": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["read", "diagram"],
                "properties": {
                    "read": {"type": "string"},
                    "primer": {"type": "string"},
                    "template": {"type": "string"},
                    "cycles": {"type": "integer"},
                    "note": {"type": "string"},
                    "diagram": {"type": "string"},
                },
            },
        },
        "platform": {"type": "string"},
        "read_structure": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "reads": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["read"],
                        "properties": {
                            "read": {"type": "string"},
                            "primer": {"type": "string"},
                            "template": {"type": "string"},
                            "cycles": {"type": "integer"},
                            "segments": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["name", "type"],
                                    "properties": {
                                        "name": {"type": "string"},
                                        "type": {"type": "string"},
                                        "length": {"type": "integer"},
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
        "title": {"type": "string"},
        "description": {"type": "string"},
        "publication": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "year": {"type": "integer"},
                "original_publication": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string"},
                        "journal": {"type": "string"},
                        "doi": {"type": "string"},
                        "url": {"type": "string"},
                    },
                },
                "authors": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["name"],
                        "properties": {
                            "name": {"type": "string"},
                            "corresponding": {"type": "boolean"},
                            "email": {"type": "string"},
                            "affiliation": {"type": "string"},
                        },
                    },
                },
                "throughput": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "summary": {"type": "string"},
                        "cells": {"type": "string"},
                        "rna": {"type": "string"},
                        "dna": {"type": "string"},
                    },
                },
                "statistical_model": {"type": "string"},
                "other": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "label": {"type": "string"},
                            "value": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
}

_PROMPT = """You are an expert at reading single-cell sequencing library-prep protocols and \
extracting their exact oligonucleotide sequences and final library structure.

Below is the extracted text of one protocol document ({protocol_name}). Extract the following into \
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
   library). One entry per step:
   `{step: <1-based int>, title: <short step name>, summary: <ONE concise sentence gist of the step>, note: <optional longer plain-English biology>, product: <ASCII diagram>}`.
   For EACH step, `product` is a monospace ASCII diagram of the molecular product AFTER that step
   (scg_lib_structs style). Diagram conventions (follow EXACTLY, spaces only — never tabs):
     `5'- SEQ -3'` sense strand · `3'- SEQ -5'` antisense · `-------->` / `<--------` polymerase
     extension · `|--5'-` bead-attached 5' end · `[CELL_BARCODE:16]` / `[UMI:12]` / `[SAMPLE_INDEX:8]`
     variable regions · `[CDNA]` the cDNA insert · `(T)30VN` poly-dT anchor · `*A`/`A*` A-tail overhang.
   Write out adapter/primer sequences in full (do NOT truncate). When a primer anneals, put it on its
   own line and align its binding site directly above/below the construct by counting character offsets.
   Example product (10x 3', "Adding TSO for second-strand synthesis"):
     |--5'- CTACACGACGCTCTTCCGATCT[CELL_BARCODE:16][UMI:12](T)30VN[CDNA]------->
                                                       TACATGAGACGCAACTATGGTGACGAA -5'
   The final step's product MUST equal the assembled `final_library.annotated_library_sequence`.
   Omit or leave empty if the document does not describe the build steps.
4. `library_sequencing`: how the FINAL library is sequenced on the instrument — one entry per read
   in sequencing order (Read 1, Index 1 (i7), Index 2 (i5) if dual-indexed, Read 2). Each entry:
   `{read: <"Read 1"|"Index 1 (i7)"|"Read 2">, primer: <sequencing primer name>, template: <"top"|"bottom">,
   cycles: <int bp>, note: <what is read, e.g. "16 bp cell barcode + 12 bp UMI">, diagram: <ASCII>}`.
   `diagram` shows the sequencing primer annealing to the full final-library construct (BOTH strands,
   sequences written out) with a `------->` / `<-------` arrow for the read direction. Use `N` for each
   unknown barcode/index position and `X` for the cDNA insert. Same alignment rules as the step products
   (spaces only, count offsets so the primer sits directly above/below its binding site).
   Example (Read 1 sequencing the cell barcode + UMI off the bottom strand):
                              5'- ACACTCTTTCCCTACACGACGCTCTTCCGATCT------------------------->
     3'- ...GATGTGCTGCGAGAAGGCTAGANNNNNNNNNNNNNNNNNNNNNNNNNN(pA)BXXX...XXXTCTAGCCTTCTCG... -5'
5. `title`: a CONCISE display title for the assay/protocol, shorter than a full formal name
   (e.g. "10x 3' scRNA-seq (v3.1)" or "sc-Nanopore 10x 3' cDNA"). `description`: 2-4 sentences on
   what the protocol does and the experiment it enables (chemistry + purpose).
6. `publication`: fill ONLY from what the document actually states; otherwise omit the field or leave
   parts empty. Capture: `year` (publication year, int); `original_publication` (`title`, `journal`,
   `doi`, `url` of the source paper); `authors` (each `{name, corresponding: true only for the
   corresponding author(s), email, affiliation}` — include `email` ONLY if the document prints it);
   `throughput` (cell/RNA/DNA yield, e.g. `{summary, cells, rna, dna}`); `statistical_model` (the
   statistical method the authors use to model the assay data — e.g. "Poisson" or "negative binomial"
   for droplet UMI counts); `other` (a few neat extra facts as `{label, value}`). DO NOT fabricate
   authors, emails, DOIs, or numbers — if it is not in the text, leave it out.

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


# Technology-agnostic prompt for building the "wiki" spec of ANY single-cell / sequencing assay from its
# paper + protocol + supplementary documents. No 10x-specific oligo checklist or P5/P7 assembly recipe.
_PROMPT_GENERIC = """You are an expert at reading single-cell / sequencing library-prep papers and \
protocols and extracting, exactly, their oligonucleotide sequences, step-by-step library construction, \
final library structure, read structure, and publication metadata.

Below are the concatenated documents for ONE technology ({protocol_name}) — typically the original paper, \
a detailed/vendor protocol, and supplementary PDFs/tables, each delimited by `=== DOCUMENT: <name> ===`. \
Treat the PAPER and PROTOCOL as primary sources; use the SUPPLEMENTARY TABLES for exact barcode / index / \
primer sequences (they are often only listed there). Extract into the required JSON schema:

1. `oligos`: one entry per NAMED oligo in the protocol — every bead/capture oligo, RT primer, template-\
   switch oligo, PCR/library primer, adapter (Tn5/ME, TruSeq, Nextera, custom), sequencing primer, and \
   index/barcode oligo you can find. Be COMPLETE; do not stop early. For each: `oligo_id` \
   (lowercase_snake_case), `name`, `role`, `kind` ("single" | "assembled" -> fill `components` | \
   "double_stranded" -> sequence:"" and put both strands in `components`), `sequence`, optional `notes`.
2. `final_library`: the FINAL sequenceable library structure — its full 5'->3' top strand with placeholder \
   tokens, plus the raw strand text in `strands` and a human-readable `annotation_lines` breakdown.
3. `library_generation`: the ordered wet-lab build steps. One entry per step: \
   `{step: <1-based int>, title: <short step name>, summary: <ONE concise sentence gist>, \
   note: <optional longer plain-English biology>, product: <ASCII diagram of the molecule AFTER this step>}`.
   Diagram conventions (spaces only, never tabs): `5'- SEQ -3'` sense strand · `3'- SEQ -5'` antisense · \
   `-------->`/`<--------` polymerase extension · align an annealing primer directly above/below its \
   binding site by counting character offsets. Write adapter/primer sequences out in full.
4. `library_sequencing`: how the final library is sequenced — one entry per read in sequencing order \
   (`read`, `primer`, `template` "top"/"bottom", `cycles`, `note`, `diagram`).
5. `platform`: the sequencing platform — one of "illumina", "nanopore", "pacbio" (most short-read \
   single-cell assays are "illumina"; infer from the protocol).
6. `read_structure`: `{reads: [{read: <e.g. "R1"|"R2"|"I1"|"L1">, primer, template, cycles, \
   segments: [{name, type, length}]}]}`. `type` should be one of barcode / umi / index / insert / cdna / \
   constant / polyA / spacer — the normalizer maps the rest. Best-effort; omit lengths you cannot determine.
7. `title`: a CONCISE display title (e.g. "Drop-seq", "SMART-seq2", "sci-ATAC-seq"). `description`: 2-4 \
   sentences on what the assay measures and how (chemistry + purpose + what the reads capture).
8. `publication`: fill ONLY from the documents. `year`; `original_publication` (`title`, `journal`, `doi`, \
   `url`); `authors` (each `{name, corresponding: true only for the corresponding author(s), email, \
   affiliation}` — email ONLY if printed); `throughput` (cell/RNA/DNA yield as `{summary, cells, rna, \
   dna}`); `statistical_model` (the statistical method the authors use to model the assay data, e.g. \
   "Poisson"/"negative binomial" for droplet UMI counts); `other` (a few neat facts as `{label, value}`).

CONVENTIONS (follow EXACTLY):
- All sequences 5'->3', uppercase ACGTN only; transcribe the exact characters shown. Fold ribonucleotide \
  notation (rG rG rG -> GGG).
- Replace variable regions with placeholder tokens keeping their bp count: cell barcode -> \
  [CELL_BARCODE:N]; UMI -> [UMI:M]; sample/i7/i5 index -> [SAMPLE_INDEX:K] (or [INDEX:K]); the cDNA/genomic \
  insert -> [CDNA]; a fixed-length spacer/linker -> [SPACER:N]. Combinatorial-index assays (SPLiT-seq, \
  sci-*, SHARE-seq) have MULTIPLE barcode rounds — emit one token per round (e.g. [CELL_BARCODE:8] x3).
- DO NOT fabricate any sequence, author, email, DOI, or number. If it is not in the documents, leave it \
  out (null / omit). Prefer what the paper and protocol state over any single supplementary snippet.

Output ONLY the structured JSON. Do not include commentary.

=== DOCUMENTS START ===
{doc_text}
=== DOCUMENTS END ===
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


# Pushed into the generic prompt when extracting a single, possibly incomplete/novel protocol from the
# studio: infer the read LAYOUT as fully as possible without fabricating exact sequences.
_INFER_ADDENDUM = """INFERENCE (this may be an incomplete, custom, or NOVEL protocol — not a catalog technology):
- Build the MOST COMPLETE read_structure you can from whatever is stated. For EACH sequencing read \
(R1/R2/I1/…), list its segments in 5'->3' order with a `name`, a `type` \
(barcode/umi/index/insert/cdna/constant/spacer/polyA) and a best-effort integer `length`: use the stated \
length; if only a run of Ns is shown (e.g. NNNNNNNN) use its exact count; include any fixed constant \
anchor/linker as a `constant` segment with its literal sequence in the name. State clearly which mate \
carries the UMI/barcode vs the cDNA insert, and record any 3' read-through adapter.
- INFER structure, NEVER sequences: do not invent exact adapter/primer/barcode NUCLEOTIDE strings that \
are not in the source. Omit an oligo's `sequence` (leave null) rather than guessing it."""


def extract_documents(paths, protocol_name: str, *, model: str = DEFAULT_MODEL,
                      char_budget: int = 1_800_000, extra_instructions: str = "") -> dict:
    """Extract one spec from MANY concatenated documents (paper + protocol + supplements) via Claude,
    using the technology-agnostic prompt. Returns the extraction plus a per-doc text budget log."""
    combined, text_log = extract_texts(paths, char_budget=char_budget)
    prompt = _PROMPT_GENERIC.replace("{protocol_name}", protocol_name).replace("{doc_text}", combined)
    if extra_instructions:
        prompt = prompt.replace(
            "Output ONLY the structured JSON.",
            f"{extra_instructions}\n\nOutput ONLY the structured JSON.",
        )
    result = _run_claude(prompt, EXTRACTION_SCHEMA, model=model)
    result["source_chars"] = len(combined)
    result["text_log"] = text_log
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

    # Derived read-through adapters (revcomp of the CONSTANT Read 1 sequencing primer + P5).
    # Pick the constant TruSeq/Nextera Read 1 *sequencing* primer — one whose sequence has NO
    # placeholder tokens; the barcode/UMI belong to the read, not the adapter. Fall back to the
    # verified constant so we never revcomp a barcode/UMI-bearing capture primer.
    def _constant_only(seq: str | None) -> str:
        return re.sub(r"\[[^\]]*\]", "", seq or "")

    r1_primer = next(
        (o["sequence"] for o in oligos
         if "read 1" in o["name"].lower() and "primer" in o["name"].lower()
         and o.get("sequence") and "[" not in o["sequence"]),
        VERIFIED.get("truseq_read1_primer"),
    )
    p5 = next((o["sequence"] for o in oligos if o["name"].lower().strip().endswith("p5 adapter") and o.get("sequence")), None)
    chain = [{"name": "tso_5prime", "type": "constant",
              "constant_ref": _match_oligo_seq(oligos, VERIFIED["tso"]) or "", "notes": "adapter-dimer leads with the TSO"},
             {"name": "cdna_short", "type": "insert"},
             {"name": "polyA", "type": "polyA", "base": "A"},
             {"name": "umi_rc", "type": "umi", "derivation": "revcomp(umi)"},
             {"name": "cbc_rc", "type": "barcode", "derivation": "revcomp(cell_barcode)"}]
    names = {
        "oligo_r1_readinto_adapter": "R1 read-into adapter (revcomp of Read 1 primer)",
        "oligo_p5_rc": "P5 reverse complement",
    }
    for label, seq in (("oligo_r1_readinto_adapter", r1_primer), ("oligo_p5_rc", p5)):
        const = _constant_only(seq)
        if const:
            oligos.append({
                "oligo_id": label, "name": names[label],
                "aliases": [], "role": "read_through_adapter", "kind": "single",
                "sequence": revcomp(const), "direction": "5_to_3", "components": [],
                "provenance": "document", "derivation": f"revcomp({const})",
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
        "library_sequencing": extraction.get("library_sequencing", []),
        "whitelists": whitelist_block,
        "build": {"builder_version": "llm-1.0", "deterministic": False,
                  "source_html_sha256": None, "extraction_method": "claude_llm", "model": model},
    }

    # Optional metadata extracted from the document (title/description/publication) + the reference
    # pointer to the source. Only set string fields when present so nullable-string schema stays happy.
    if extraction.get("title"):
        spec["title"] = extraction["title"]
    if extraction.get("description"):
        spec["description"] = extraction["description"]
    pub = extraction.get("publication") or {}
    orig = pub.get("original_publication") or {}
    spec["reference"] = {
        "kind": "uploaded_file",
        "label": str(source_doc_path).rsplit("/", 1)[-1],
        "path": str(source_doc_path),
        "url": orig.get("url"),
        "doi": orig.get("doi"),
    }
    if pub:
        spec["publication"] = pub

    validate_spec(spec)
    return spec


# ---- enrichment: add modality / method_type / data_processing to an EXISTING wiki spec -----------

ENRICH_SCHEMA: dict = {
    "type": "object", "additionalProperties": False,
    "required": ["modality", "method_type"],
    "properties": {
        "modality": {"type": "string"},
        "method_type": {"type": "string"},
        "data_processing": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "summary": {"type": "string"},
                "steps": {"type": "array", "items": {"type": "string"}},
                "tools": {"type": "array", "items": {"type": "string"}},
                "statistical_model": {"type": "string"},
            },
        },
        "library_sequencing": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False, "required": ["read"],
                "properties": {
                    "read": {"type": "string"}, "primer": {"type": "string"},
                    "template": {"type": "string"}, "cycles": {"type": "integer"},
                    "note": {"type": "string"}, "diagram": {"type": "string"},
                },
            },
        },
        "drop_other_labels": {"type": "array", "items": {"type": "string"}},
    },
}

_ENRICH_PROMPT = """You are refining the wiki entry for ONE sequencing assay ({protocol_name}). Below is \
its CURRENT extracted spec (JSON) and the assay's paper/protocol text. Produce ONLY these refinements as \
JSON — do not re-extract oligos or the library build.

1. `modality`: what the assay measures, in the Teichlab scg_lib_structs style — one of "RNA", "ATAC", \
   "RNA+ATAC (multiome)", "DNA methylation", "gDNA (WGS/CNV)", "CRISPR/gRNA", "protein+RNA (CITE)", \
   "DNA (other)", or a short precise phrase.
2. `method_type`: the cell-isolation / barcoding format — one of "droplet", "plate-based", \
   "microwell/picowell", "combinatorial indexing", "nanowell", "microfluidic (C1)", "FACS", or a short \
   phrase (e.g. "droplet + split-pool").
3. `data_processing`: the COMPUTATIONAL pipeline, only if the paper describes it: \
   `{summary: <1-2 sentences>, steps: [ordered stages, e.g. "demultiplex barcodes", "align (STAR)", \
   "collapse UMIs", "count matrix", "cluster"], tools: [named software], statistical_model: <e.g. \
   "Poisson", "negative binomial", or omit>}`. If the paper gives no pipeline, provide just a brief \
   `summary` and leave steps/tools empty. DO NOT fabricate tools or steps.
4. `library_sequencing`: REGENERATE each sequencing read with a DOUBLE-STRANDED aligned ASCII `diagram` — \
   BOTH strands written out with complementary bases A-T / C-G aligned vertically, `5'- … -3'` over \
   `3'- … -5'`, the sequencing primer on its own line directly above/below its binding site (count \
   character offsets), and a `------->` / `<-------` read-direction arrow — exactly the conventions used \
   in the step-by-step library-generation products. One entry per read: \
   `{read, primer, template: "top"|"bottom", cycles: <read length in bp>, note, diagram}`. `cycles` IS \
   the read length in bp — do NOT also embed the cycle count in the `read` name.
5. `drop_other_labels`: labels from the current `publication.other` that merely REPEAT information already \
   shown in the description / read structure (e.g. "Cell barcode", "UMI", "UMI length", "Barcode design", \
   "Barcode pool", "Assay type", "Bead barcode structure", "Tn5 barcodes", "Chemistry", "Cell Label", \
   "Molecular Index") — list them for removal. KEEP data-availability / GEO accessions and genuinely novel facts.

Output ONLY the structured JSON.

=== CURRENT SPEC (JSON) ===
{spec_json}
=== PAPER / PROTOCOL TEXT ===
{doc_text}
"""

# publication.other labels that always duplicate other sections — dropped regardless of the model's list.
_REDUNDANT_OTHER = {
    "cell barcode", "umi", "umi length", "barcode design", "barcode pool", "assay type",
    "bead barcode structure", "tn5 barcodes", "chemistry", "cell label", "molecular index",
    "indexing", "barcode structure", "cell barcode structure", "cell label (barcode)",
}


def enrich_extraction(spec: dict, doc_paths, protocol_name: str, *, model: str = DEFAULT_MODEL,
                      char_budget: int = 1_200_000) -> dict:
    """Run the enrichment prompt over an existing spec + its papers (returns the enrichment object)."""
    combined, _log = extract_texts(doc_paths, char_budget=char_budget)
    spec_view = json.dumps({k: spec.get(k) for k in
                            ("title", "description", "assay", "platform", "oligos", "final_library",
                             "library_sequencing", "read_structure", "publication")}, indent=1)[:120_000]
    prompt = (_ENRICH_PROMPT.replace("{protocol_name}", protocol_name)
              .replace("{spec_json}", spec_view).replace("{doc_text}", combined))
    return _run_claude(prompt, ENRICH_SCHEMA, model=model)


def merge_enrichment(spec: dict, enr: dict) -> dict:
    """Merge an enrichment object into a spec (keeps oligos/library_generation), then re-validate."""
    if enr.get("modality"):
        spec["modality"] = enr["modality"]
    if enr.get("method_type"):
        spec["method_type"] = enr["method_type"]
    dp = enr.get("data_processing") or {}
    if dp.get("summary") or dp.get("steps") or dp.get("statistical_model"):
        spec["data_processing"] = dp
    if enr.get("library_sequencing"):
        spec["library_sequencing"] = enr["library_sequencing"]
    drop = {l.lower() for l in enr.get("drop_other_labels", [])} | _REDUNDANT_OTHER
    pub = spec.get("publication")
    if pub and pub.get("other"):
        pub["other"] = [o for o in pub["other"] if (o.get("label") or "").lower() not in drop]
    validate_spec(spec)
    return spec


# ---- data-processing DAG (graph, not a flat chain) -----------------------------------------------

DAG_SCHEMA: dict = {
    "type": "object", "additionalProperties": False, "required": ["nodes", "edges"],
    "properties": {
        "stages": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["id", "label"],
            "properties": {"id": {"type": "string"}, "label": {"type": "string"}}}},
        "nodes": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["id", "label"],
            "properties": {"id": {"type": "string"}, "label": {"type": "string"},
                           "tool": {"type": "string"}, "stage": {"type": "string"},
                           "scope": {"type": "string", "enum": ["per_cell", "bulk"]},
                           "terminal": {"type": "boolean"}, "viz_only": {"type": "boolean"}}}},
        "edges": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["from", "to"],
            "properties": {"from": {"type": "string"}, "to": {"type": "string"},
                           "kind": {"type": "string", "enum": ["sequential", "fan_in", "branch"]}}}},
        "statistical_model": {"type": "string"},
    },
}

_DAG_PROMPT = """You convert a computational-methods description into a data-processing DAG. Return JSON \
only, matching the required schema: `stages` (ordered phases {id,label}), `nodes` \
({id,label,tool,stage,scope,terminal,viz_only}), `edges` ({from,to,kind}). `scope` in per_cell|bulk; \
`kind` in sequential|fan_in|branch.

RULES:
1. Dependencies are EDGES, never order. Connect two nodes iff one's output is the other's input. The order \
   of the `nodes` array is meaningless.
2. ONE primitive operation per node. Never bundle tools/actions in a label (no "TF-IDF + SVD"; split into \
   separate nodes joined by an edge).
3. Labels: imperative verb + object, <= 6 words. Put the software in `tool`, not the label. Include a \
   parameter only when it IS the point (e.g. "call peaks (q<0.01)").
4. Scope + fan-in: `scope:"per_cell"` for per-cell steps, `"bulk"` for merged/aggregated steps. The first \
   bulk node consuming per-cell outputs gets `fan_in` edges from them.
5. Branches + terminals: if one node feeds two independent downstream paths, emit an edge to each with \
   `kind:"branch"`. Mark visualization-only endpoints `viz_only:true` and `terminal:true`. NEVER place a \
   `viz_only` node on the path to an analytical step (a t-SNE/UMAP embedding does NOT feed clustering — \
   clustering consumes the LSI/PCA reduction).
6. Stages: assign every node to exactly one stage; stages are ordered phases.

SELF-CHECK before emitting: did I linearize a branch? is any viz_only node on the analysis path? are \
per-cell steps marked and does the first bulk step fan_in from them? did I bundle operations in one node? \
does every edge reflect a real data dependency (not narrative sequence)?

Base the DAG on the pipeline below; expand bundled steps into separate nodes, infer per_cell/bulk scope \
and the fan-in point, and split any branch (e.g. a reduction feeding both a viz embedding and clustering). \
Do NOT fabricate tools not implied by the description — leave `tool` empty if unknown.

=== ASSAY + EXTRACTED PIPELINE (JSON) ===
{context}
"""


def graphify_data_processing(spec: dict, *, model: str = DEFAULT_MODEL) -> dict:
    """Turn a spec's flat data_processing (summary/steps/tools) into a proper DAG (stages/nodes/edges)."""
    dp = spec.get("data_processing") or {}
    context = {
        "assay": spec.get("title") or spec.get("assay"), "modality": spec.get("modality"),
        "description": spec.get("description"),
        "pipeline_summary": dp.get("summary"), "pipeline_steps": dp.get("steps"),
        "tools": dp.get("tools"), "statistical_model": dp.get("statistical_model"),
    }
    prompt = _DAG_PROMPT.replace("{context}", json.dumps(context, indent=1))
    return _run_claude(prompt, DAG_SCHEMA, model=model)


# ---- generic (technology-agnostic) assembly ------------------------------------------------------

_SEG_TYPE_ALLOWED = {"barcode", "umi", "constant", "insert", "polyA", "index", "homopolymer", "anchor"}
_SEG_TYPE_ALIASES = {
    "cell_barcode": "barcode", "cbc": "barcode", "cb": "barcode",
    "cdna": "insert", "genomic": "insert", "dna": "insert", "rna": "insert",
    "poly_a": "polyA", "polya": "polyA", "poly_t": "homopolymer", "polyt": "homopolymer",
    "sample_index": "index", "i7": "index", "i5": "index",
    "spacer": "constant", "linker": "constant", "primer": "constant", "adapter": "constant",
    "me": "constant", "mosaic_end": "constant", "other": "constant",
}


def _norm_seg_type(t: str | None) -> str:
    t = (t or "").strip().lower()
    return t if t in _SEG_TYPE_ALLOWED else _SEG_TYPE_ALIASES.get(t, "constant")


def _oligo_slug(name: str) -> str:
    return "oligo_" + (re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_") or "unnamed")


def _generic_read_structure(extraction: dict) -> dict:
    """Build a schema-valid read_structure from the LLM's best-effort reads (normalize segment types,
    add the schema-required order/scored, drop non-integer lengths). Falls back to a single-read stub."""
    reads_out = []
    for r in (extraction.get("read_structure") or {}).get("reads") or []:
        segs = []
        for i, s in enumerate(r.get("segments") or []):
            st = _norm_seg_type(s.get("type"))
            seg = {"name": s.get("name") or f"seg{i}", "type": st, "order": i,
                   "scored": st in ("barcode", "umi", "insert"),
                   "provenance": None, "whitelist_ref": None, "constant_ref": None, "notes": None}
            if isinstance(s.get("length"), int):
                seg["length"] = s["length"]
            segs.append(seg)
        reads_out.append({"read": r.get("read") or f"R{len(reads_out) + 1}",
                          "primer": r.get("primer"), "template": r.get("template"),
                          "cycles": r.get("cycles") if isinstance(r.get("cycles"), int) else None,
                          "segments": segs})
    if not reads_out:
        reads_out = [{"read": "R1", "primer": None, "template": None, "cycles": None,
                      "segments": [{"name": "insert", "type": "insert", "order": 0, "scored": True,
                                    "provenance": None, "whitelist_ref": None, "constant_ref": None,
                                    "notes": None}]}]
    return {"reads": reads_out}


def assemble_generic_spec(extraction: dict, *, spec_id: str, assay: str, chemistry_version: str,
                          source_docs: list[dict], reference: dict | None = None,
                          model: str = DEFAULT_MODEL) -> dict:
    """Wrap a technology-agnostic LLM extraction into a schema-valid spec — no 10x/Illumina hardcoding.
    Uses the LLM's platform + read_structure, an empty whitelist, and generic platform_params."""
    oligos = []
    for o in extraction.get("oligos", []):
        oligos.append({
            "oligo_id": o.get("oligo_id") or _oligo_slug(o.get("name", "")),
            "name": o.get("name", ""), "aliases": [], "role": o.get("role", "oligo"),
            "kind": o.get("kind", "single"),
            "sequence": (o.get("sequence") or None) if o.get("kind") != "double_stranded" else None,
            "direction": "5_to_3", "components": o.get("components", []),
            "provenance": _provenance_for(o.get("name", "")), "derivation": None,
            "sequence_source": "llm_extracted_from_docs",
            "evidence": [{"source_doc": "protocol_docs", "locator": "oligo / final library",
                          "method": "claude_llm_extraction"}],
            "notes": o.get("notes"),
        })
    if not oligos:  # schema requires oligos minItems 1
        oligos = [{"oligo_id": "oligo_none_extracted", "name": "(none extracted)", "aliases": [],
                   "role": "oligo", "kind": "single", "sequence": None, "direction": "5_to_3",
                   "components": [], "provenance": "document", "derivation": None,
                   "sequence_source": "llm_extracted_from_docs",
                   "evidence": [{"source_doc": "protocol_docs", "locator": "", "method": "claude_llm_extraction"}],
                   "notes": None}]

    platform = (extraction.get("platform") or "illumina").strip().lower()
    if platform not in ("illumina", "nanopore", "pacbio"):
        platform = "illumina"
    fl = extraction.get("final_library") or {}

    spec = {
        "schema_version": "seqcolyte.spec.v1", "spec_id": spec_id, "assay": assay,
        "chemistry_version": chemistry_version or "", "platform": platform,
        "platform_params": {"read_type": "long" if platform in ("nanopore", "pacbio") else "short"},
        "source_docs": source_docs or [{"doc_id": "protocol_docs", "title": assay, "url": None,
                                        "path": None, "retrieved_date": None}],
        "oligos": oligos,
        "final_library": {
            "source_label": fl.get("source_label", "Final library structure"),
            "annotated_library_sequence": fl.get("annotated_library_sequence", ""),
            "library_sequence": fl.get("library_sequence", ""),
            "strands": [{"direction": s.get("direction", "5_to_3"), "source_html": s.get("source_sequence", ""),
                         "source_sequence": s.get("source_sequence", "")} for s in fl.get("strands", [])],
            "annotation_lines": fl.get("annotation_lines", []),
            "evidence": [{"source_doc": "protocol_docs", "locator": fl.get("source_label", ""),
                          "method": "claude_llm_extraction"}],
        },
        "read_structure": _generic_read_structure(extraction),
        "library_generation": extraction.get("library_generation", []),
        "library_sequencing": extraction.get("library_sequencing", []),
        "whitelists": {},
        "build": {"builder_version": "llm-generic-1.0", "deterministic": False,
                  "source_html_sha256": None, "extraction_method": "claude_llm_generic", "model": model},
    }
    if extraction.get("title"):
        spec["title"] = extraction["title"]
    if extraction.get("description"):
        spec["description"] = extraction["description"]
    if reference:
        spec["reference"] = reference
    if extraction.get("publication"):
        spec["publication"] = extraction["publication"]

    validate_spec(spec)
    return spec


# --------------------------------------------------------------------------------------
# Soft cross-check + eval against a checked-in groundtruth
# --------------------------------------------------------------------------------------

def _norm(seq: str) -> str:
    # Fold notation-only chemistry annotations so the SAME DNA compares equal regardless of how it was
    # written: strip IDT-style modifications (/5Biosg/, /5Phos/, /iSp18/, …), phosphorothioate bond marks
    # (`*`), and fold ribonucleotides (rG rG rG -> GGG). None of these change the base sequence.
    s = re.sub(r"/[^/]*/", "", seq or "")           # /5Biosg/ /5Phos/ /3Bio/ /iSpXX/ …
    s = re.sub(r"r([ACGTacgt])", r"\1", s)          # rG -> G
    s = s.replace("*", "")                          # phosphorothioate bond marks
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
