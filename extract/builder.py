"""Assemble the consolidated ``spec/tenx_3p_v3.json`` from a parsed protocol.

Flow: parse HTML -> cross-check every parsed sequence against ``verified_constants`` (fail loudly
on mismatch) -> assemble oligos + final_library + read_structure with an honest evidence chain ->
schema-validate -> emit canonical (byte-reproducible) JSON.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from seqcolyte.dna import homopolymer, revcomp
from seqcolyte.spec.loader import validate_spec
from extract.html_parser import ParsedProtocol, parse_protocol
from extract.verified_constants import CITATIONS, DERIVED, VERIFIED, citation_urls

__all__ = ["build_spec", "to_canonical_json", "BUILDER_VERSION", "DEFAULT_HTML", "DEFAULT_OUT"]

BUILDER_VERSION = "1.0"
SPEC_ID = "tenx_3p_v3"
RETRIEVED_DATE = "2026-07-07"
_REPO = Path(__file__).resolve().parents[1]
DEFAULT_HTML = _REPO / "protocols" / "10xChromium3.html"
DEFAULT_OUT = _REPO / "spec" / "tenx_3p_v3.json"
POLYT_LEN = 30  # (T)30 on the bead oligo, per the source diagram

# key -> (oligo_id, name, role, kind, provenance, xcheck_constant_key, aliases, notes)
_OLIGO_BUILD = [
    ("beads_oligo_dt", "oligo_beads_oligo_dt", "Beads-oligo-dT", "oligo", "assembled", "reagent",
     "r1_partial_handle", [], None),
    ("tso", "oligo_template_switching_oligo_tso", "Template Switching Oligo (TSO)", "oligo",
     "assembled", "reagent", "tso", [], "Terminal rGrGrG (riboguanosines); parsed as GGG."),
    ("cdna_forward_primer", "oligo_cdna_forward_primer", "cDNA Forward primer", "primer", "single",
     "document", "cdna_forward_primer", [], None),
    ("cdna_reverse_primer", "oligo_cdna_reverse_primer", "cDNA Reverse primer", "primer", "single",
     "reagent", "cdna_reverse_primer", [], "v3/v3.1/v4 variant."),
    ("truseq_read1_primer", "oligo_illumina_truseq_read_1_primer", "Illumina TruSeq Read 1 primer",
     "primer", "assembled", "document", "truseq_read1_primer", [], None),
    ("truseq_read2_primer", "oligo_illumina_truseq_read_2_primer", "Illumina TruSeq Read 2 primer",
     "primer", "single", "document", "truseq_read2_primer", [], None),
    ("truseq_adapter", "oligo_truseq_adapter", "TruSeq adapter", "adapter", "double_stranded",
     "document", None, ["TruSeq adapter forward", "TruSeq adapter reverse"],
     "Double-stranded with a T overhang; v3/v3.1/v4 variant."),
    ("library_pcr_primer_1", "oligo_library_pcr_primer_1", "Library PCR primer 1", "primer",
     "assembled", "document", "p5", [], None),
    ("library_pcr_primer_2", "oligo_library_pcr_primer_2", "Library PCR primer 2", "primer",
     "assembled", "document", "p7", [], None),
    ("sample_index_seq_primer", "oligo_sample_index_sequencing_primer",
     "Sample index sequencing primer", "primer", "single", "document",
     "sample_index_seq_primer", [], None),
    ("p5", "oligo_illumina_p5_adapter", "Illumina P5 adapter", "adapter", "single", "document",
     "p5", [], None),
    ("p7", "oligo_illumina_p7_adapter", "Illumina P7 adapter", "adapter", "single", "document",
     "p7", [], None),
]

# derived oligos (revcomp) — added so the read-through chain resolves from `oligos` uniformly.
# (oligo_id, name, role, derived_key, derivation, notes)
_DERIVED_BUILD = [
    ("oligo_r2_readthrough_adapter", "Read 2 read-through adapter", "read_through_adapter",
     "r2_readthrough_adapter", "revcomp(oligo_illumina_truseq_read_2_primer)",
     "3' adapter observed as R2 read-through when the insert is shorter than the read."),
    ("oligo_r1_readinto_adapter", "Short-insert R2 read-into adapter", "read_through_adapter",
     "r1_readinto_adapter", "revcomp(oligo_illumina_truseq_read_1_primer)",
     "Adapter a short-insert R2 reads into, past poly(A) + reverse-complemented barcode/UMI."),
    ("oligo_p5_rc", "Illumina P5 adapter (reverse complement)", "adapter_rc", "p5_rc",
     "revcomp(oligo_illumina_p5_adapter)", "Terminal 3' segment of a fully read-through R2."),
]

_ADAPTER_SECTION = "Adapter and primer sequences"
_FINAL_SECTION = "Step-by-step library generation / (8) Final library structure — V3, V3.1 & V4"


def _token_len(seq: str, token: str) -> int:
    m = re.search(rf"\[{token}:(\d+)\]", seq)
    if not m:
        raise ValueError(f"token [{token}:N] not found in {seq!r}")
    return int(m.group(1))


def _evidence(constant_key: str | None, locator: str) -> list[dict]:
    return [{
        "source_doc": "scg_10xChromium3",
        "locator": locator,
        "verified_against": citation_urls(constant_key) if constant_key else [],
    }]


def _cross_check(parsed: ParsedProtocol) -> None:
    """Assert every parsed sequence matches the verified oracle; raise loudly otherwise."""
    o = parsed.oligos

    def eq(key: str, got, exp) -> None:
        if got != exp:
            raise ValueError(f"cross-check failed for {key}: parsed {got!r} != verified {exp!r}")

    for key in ("tso", "cdna_forward_primer", "cdna_reverse_primer", "truseq_read1_primer",
                "truseq_read2_primer", "sample_index_seq_primer", "p5", "p7"):
        eq(key, o[key], VERIFIED[key])
    eq("truseq_adapter_fwd", o["truseq_adapter"]["fwd"], VERIFIED["truseq_adapter_fwd"])
    eq("truseq_adapter_rev", o["truseq_adapter"]["rev"], VERIFIED["truseq_adapter_rev"])

    if not o["beads_oligo_dt"].startswith(VERIFIED["r1_partial_handle"]):
        raise ValueError("beads oligo does not start with the R1 partial handle")
    if not o["library_pcr_primer_1"].startswith(VERIFIED["p5"]):
        raise ValueError("Library PCR primer 1 does not start with P5")
    if not o["library_pcr_primer_2"].startswith(VERIFIED["p7"]):
        raise ValueError("Library PCR primer 2 does not start with P7")

    # derived revcomp identities (also asserted at import time in verified_constants)
    if DERIVED["r2_readthrough_adapter"] != revcomp(VERIFIED["truseq_read2_primer"]):
        raise ValueError("r2_readthrough_adapter != revcomp(truseq_read2_primer)")
    if DERIVED["r1_readinto_adapter"] != revcomp(VERIFIED["truseq_read1_primer"]):
        raise ValueError("r1_readinto_adapter != revcomp(truseq_read1_primer)")
    if DERIVED["p5_rc"] != revcomp(VERIFIED["p5"]):
        raise ValueError("p5_rc != revcomp(p5)")


def _components(key: str, parsed: ParsedProtocol, cb_len: int, umi_len: int, idx_len: int) -> list[dict]:
    o = parsed.oligos
    if key == "beads_oligo_dt":
        return [
            {"name": "cDNA forward primer", "sequence": VERIFIED["cdna_forward_primer"], "role": "primer"},
            {"name": f"[CELL_BARCODE:{cb_len}]", "sequence": f"[CELL_BARCODE:{cb_len}]", "role": "cell_barcode"},
            {"name": f"[UMI:{umi_len}]", "sequence": f"[UMI:{umi_len}]", "role": "umi"},
            {"name": "polyT", "sequence": homopolymer("T", POLYT_LEN) + "VN", "role": "polyT"},
        ]
    if key == "tso":
        return [{"name": "cDNA reverse primer", "sequence": VERIFIED["cdna_reverse_primer"], "role": "primer"}]
    if key == "truseq_read1_primer":
        return [{"name": "cDNA forward primer", "sequence": VERIFIED["cdna_forward_primer"], "role": "primer"}]
    if key == "truseq_adapter":
        return [
            {"name": "TruSeq adapter forward", "sequence": o["truseq_adapter"]["fwd"], "role": "forward_strand"},
            {"name": "TruSeq adapter reverse", "sequence": o["truseq_adapter"]["rev"], "role": "reverse_strand"},
        ]
    if key == "library_pcr_primer_1":
        return [{"name": "Illumina P5 adapter", "sequence": VERIFIED["p5"], "role": "adapter"}]
    if key == "library_pcr_primer_2":
        return [
            {"name": "Illumina P7 adapter", "sequence": VERIFIED["p7"], "role": "adapter"},
            {"name": f"[SAMPLE_INDEX:{idx_len}]", "sequence": f"[SAMPLE_INDEX:{idx_len}]", "role": "sample_index"},
        ]
    return []


def _build_oligos(parsed: ParsedProtocol, cb_len: int, umi_len: int, idx_len: int) -> list[dict]:
    oligos: list[dict] = []
    for key, oid, name, role, kind, prov, xkey, aliases, notes in _OLIGO_BUILD:
        if kind == "double_stranded":
            sequence = None
        else:
            sequence = parsed.oligos[key]
        oligos.append({
            "oligo_id": oid,
            "name": name,
            "aliases": aliases,
            "role": role,
            "kind": kind,
            "sequence": sequence,
            "direction": "5_to_3",
            "components": _components(key, parsed, cb_len, umi_len, idx_len),
            "provenance": prov,
            "derivation": None,
            "sequence_source": "parsed_scg_html",
            "evidence": _evidence(xkey, _ADAPTER_SECTION),
            "notes": notes,
        })
    for oid, name, role, dkey, derivation, notes in _DERIVED_BUILD:
        oligos.append({
            "oligo_id": oid,
            "name": name,
            "aliases": [],
            "role": role,
            "kind": "single",
            "sequence": DERIVED[dkey],
            "direction": "5_to_3",
            "components": [],
            "provenance": "document",
            "derivation": derivation,
            "sequence_source": "derived_revcomp",
            "evidence": _evidence(dkey, "Derived (reverse complement) — see base oligo"),
            "notes": notes,
        })
    return oligos


def _build_final_library(parsed: ParsedProtocol, cb_len: int, umi_len: int, idx_len: int) -> dict:
    p5 = VERIFIED["p5"]
    r1 = VERIFIED["truseq_read1_primer"]
    s5_lib = r1[len("ACAC"):]  # library context: P5's 3' ACAC overlaps the R1 primer's 5' ACAC
    polyt = homopolymer("T", POLYT_LEN)
    r2_adapter = DERIVED["r2_readthrough_adapter"]
    p7_rc = DERIVED["p7_rc"]

    cb, umi, si = f"[CELL_BARCODE:{cb_len}]", f"[UMI:{umi_len}]", f"[SAMPLE_INDEX:{idx_len}]"
    annotated = f"{p5}{s5_lib}{cb}{umi}{polyt}VN[CDNA]{r2_adapter}{si}{p7_rc}"
    # scoring placeholders (cDNA omitted from scoring, per the groundtruth normalization policy)
    scored = (f"{p5}{s5_lib}{'#' * cb_len}{'~' * umi_len}{polyt}VN{r2_adapter}{'@' * idx_len}{p7_rc}")

    return {
        "source_label": parsed.final_library["source_label"],
        "annotated_library_sequence": annotated,
        "library_sequence": scored,
        "strands": [
            {"direction": "5_to_3",
             "source_html": parsed.final_library["strand_5to3_html"],
             "source_sequence": parsed.final_library["strand_5to3_text"]},
            {"direction": "3_to_5",
             "source_html": parsed.final_library["strand_3to5_html"],
             "source_sequence": parsed.final_library["strand_3to5_text"]},
        ],
        "annotation_lines": [
            "Illumina P5 | TruSeq Read 1 | cell barcode | UMI | poly(dT)VN | cDNA | "
            "TruSeq Read 2 | sample index (i7) | Illumina P7",
        ],
        "evidence": _evidence("r2_readthrough_adapter", _FINAL_SECTION),
    }


def _build_read_structure(parsed: ParsedProtocol, cb_len: int, umi_len: int, idx_len: int,
                          r2_cycles: int) -> dict:
    r1_cycles = parsed.sequencing.get("R1_cycles", cb_len + umi_len)
    reads = [
        {
            "read": "R1",
            "primer": "Illumina TruSeq Read 1 primer",
            "template": "bottom",
            "cycles": r1_cycles,
            "segments": [
                {"name": "cell_barcode", "type": "barcode", "order": 0, "length": cb_len,
                 "scored": True, "provenance": None, "whitelist_ref": "cell_barcode_3M_feb2018",
                 "constant_ref": None, "notes": None},
                {"name": "umi", "type": "umi", "order": 1, "length": umi_len, "scored": True,
                 "provenance": None, "whitelist_ref": None, "constant_ref": None, "notes": None},
            ],
        },
        {
            "read": "I1",
            "primer": "Sample index sequencing primer",
            "template": "bottom",
            "cycles": idx_len,
            "segments": [
                {"name": "sample_index_i7", "type": "index", "order": 0, "length": idx_len,
                 "scored": False, "provenance": None, "whitelist_ref": None, "constant_ref": None,
                 "notes": "v3/v3.1 single index (SI-GA)"},
            ],
        },
        {
            "read": "R2",
            "primer": "Illumina TruSeq Read 2 primer",
            "template": "top",
            "cycles": r2_cycles,
            "segments": [
                {"name": "cdna_insert", "type": "insert", "order": 0, "length_range": [1, r2_cycles],
                 "scored": True, "provenance": None, "whitelist_ref": None, "constant_ref": None,
                 "notes": "sequenced from TSO/5' end toward poly(A)/3' end; read length preserved by the simulator"},
            ],
            "readthrough_chain": [
                {"name": "tso_5prime", "type": "constant", "constant_ref": "oligo_template_switching_oligo_tso",
                 "notes": "adapter-dimer / short-insert R2 leads with the TSO (HTML Step (5)-(6) Product 1)"},
                {"name": "cdna_short", "type": "insert", "notes": "residual insert 0-30 nt (pure dimer: 0)"},
                {"name": "polyA", "type": "polyA", "base": "A", "notes": "variable-length poly(A)"},
                {"name": "umi_rc", "type": "umi", "derivation": "revcomp(umi)"},
                {"name": "cbc_rc", "type": "barcode", "derivation": "revcomp(cell_barcode)"},
                {"name": "r1_primer_rc", "type": "constant", "constant_ref": "oligo_r1_readinto_adapter"},
                {"name": "p5_rc", "type": "constant", "constant_ref": "oligo_p5_rc"},
                {"name": "polyG_pad", "type": "constant", "base": "G",
                 "notes": "two-color (NextSeq/NovaSeq) no-signal pad to read length; spuriously high quality"},
            ],
        },
    ]
    return {"reads": reads}


def _build_source_docs() -> list[dict]:
    docs = []
    for doc_id, meta in CITATIONS.items():
        docs.append({
            "doc_id": doc_id,
            "title": meta["title"],
            "url": meta.get("url"),
            "path": meta.get("path"),
            "retrieved_date": RETRIEVED_DATE if doc_id == "scg_10xChromium3" else None,
        })
    return docs


def build_spec(html_path: str | Path = DEFAULT_HTML) -> dict:
    """Parse the HTML, cross-check, and assemble the consolidated spec dict."""
    parsed = parse_protocol(html_path)
    _cross_check(parsed)

    cb_len = _token_len(parsed.oligos["beads_oligo_dt"], "CELL_BARCODE")
    umi_len = _token_len(parsed.oligos["beads_oligo_dt"], "UMI")
    idx_len = _token_len(parsed.oligos["library_pcr_primer_2"], "SAMPLE_INDEX")
    r2_cycles = 90  # 10x recommendation; source diagram shows 98; pbmc_1k_v3 data is 91

    spec = {
        "schema_version": "seqcolyte.spec.v1",
        "spec_id": SPEC_ID,
        "assay": "10x Chromium Single Cell 3' Gene Expression",
        "chemistry_version": "v3/v3.1",
        "platform": "illumina",
        "platform_params": {
            "two_color_chemistry": True,
            "dark_base": "G",
            "polyA_base": "A",
            "index_scheme": "single",
            "i7_length": idx_len,
            "i5_length": None,
            "read_lengths": {"R1": cb_len + umi_len, "R2": r2_cycles, "I1": idx_len},
        },
        "source_docs": _build_source_docs(),
        "oligos": _build_oligos(parsed, cb_len, umi_len, idx_len),
        "final_library": _build_final_library(parsed, cb_len, umi_len, idx_len),
        "read_structure": _build_read_structure(parsed, cb_len, umi_len, idx_len, r2_cycles),
        "library_generation": parsed.library_generation,
        "whitelists": {
            "cell_barcode_3M_feb2018": {
                "name": "3M-february-2018",
                "path": "whitelists/3M-february-2018.txt.gz",
                "md5": None,
                "md5_provenance": "computed_local_no_official_checksum",
                "source_url": "https://raw.githubusercontent.com/f0t1h/3M-february-2018/master/3M-february-2018.txt.gz",
                "source_note": "community mirror; official file ships only inside Cell Ranger; no vendor checksum published",
                "size_bytes_gz": 18350152,
                "count": 6794880,
                "length": cb_len,
                "retrieved_date": None,
            }
        },
        "build": {
            "builder_version": BUILDER_VERSION,
            "deterministic": True,
            "source_html_sha256": parsed.source_html_sha256,
        },
    }
    validate_spec(spec)
    return spec


def to_canonical_json(spec: dict) -> bytes:
    """Canonical, byte-reproducible serialization (fixed insertion order, no timestamps)."""
    return (json.dumps(spec, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
