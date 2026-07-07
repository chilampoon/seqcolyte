"""Parse the scg_lib_structs ``10xChromium3.html`` into raw sequences.

Extraction only — no interpretation/assembly (that is ``builder.py``). We read the tagged
oligo sequences from the "Adapter and primer sequences" section (selecting the v3+ variant where
the page shows v2-vs-v3+ alternatives), the verbatim v3/v3.1/v4 final-library strand lines, and a
few sequencing hints. Placeholder text becomes tokens: ``[16-bp cell barcode]`` -> ``[CELL_BARCODE:16]``.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup

__all__ = ["ParsedProtocol", "parse_protocol"]

# (key, label prefix in the <p>, layout: "inline" | "pre", kind)
_OLIGO_SPECS: list[tuple[str, str, str, str]] = [
    ("beads_oligo_dt", "Beads-oligo-dT", "pre", "assembled"),
    ("tso", "Template Switching Oligo", "inline", "assembled"),
    ("cdna_forward_primer", "cDNA Forward primer", "inline", "single"),
    ("cdna_reverse_primer", "cDNA Reverse primer", "pre", "single"),
    ("truseq_read1_primer", "Illumina TruSeq Read 1 primer", "inline", "assembled"),
    ("truseq_read2_primer", "Illumina TruSeq Read 2 primer", "inline", "single"),
    ("truseq_adapter", "Truseq adapter", "pre", "double_stranded"),
    ("library_pcr_primer_1", "Library PCR primer 1", "inline", "assembled"),
    ("library_pcr_primer_2", "Library PCR primer 2", "inline", "assembled"),
    ("sample_index_seq_primer", "Sample index sequencing primer", "inline", "single"),
    ("p5", "Illumina P5 adapter", "inline", "single"),
    ("p7", "Illumina P7 adapter", "inline", "single"),
]

_VARIANT_MARKER = "V3"  # select the "V3, V3.1, V4" line in variant <pre> blocks


@dataclass
class ParsedProtocol:
    source_path: str
    source_html_sha256: str
    oligos: dict[str, object] = field(default_factory=dict)   # key -> str | {"fwd","rev"}
    oligo_kinds: dict[str, str] = field(default_factory=dict)
    final_library: dict[str, str] = field(default_factory=dict)
    sequencing: dict[str, int] = field(default_factory=dict)
    library_generation: list = field(default_factory=list)


def _clean_seq(fragment: str) -> str:
    """HTML sequence fragment -> clean sequence-with-tokens (uppercase ACGTN + [TOKEN:n] + VN)."""
    s = fragment
    # (T)<sub>30</sub> -> 30x T ; (A)<sub>30</sub> -> 30x A  (last base char is the repeat unit)
    s = re.sub(r"\((d?[ACGT])\)\s*<sub>(\d+)</sub>", lambda m: m.group(1)[-1] * int(m.group(2)), s)
    # placeholder text -> tokens
    s = re.sub(r"\[(\d+)-bp cell barcode\]", r"[CELL_BARCODE:\1]", s)
    s = re.sub(r"\[(\d+)-bp UMI\]", r"[UMI:\1]", s)
    s = re.sub(r"\[(\d+)-bp sample index\]", r"[SAMPLE_INDEX:\1]", s)
    # ribo-G notation (TSO): rGrGrG -> GGG
    s = s.replace("rG", "G")
    # drop remaining HTML tags
    s = re.sub(r"<[^>]+>", "", s)
    # drop strand markers, arrows, asterisks, ellipses, and all whitespace
    s = re.sub(r"5'-|-3'|3'-|-5'|\|--|-+>|<-+|\.\.\.|\*|\s+", "", s)
    return s


def _inline_seq(p_tag) -> str:
    frag = p_tag.decode_contents()
    idx = frag.find("5'-")
    if idx < 0:
        raise ValueError(f"no 5'- marker in inline oligo <p>: {frag[:80]!r}")
    return _clean_seq(frag[idx:])


def _pre_lines(pre_tag) -> list[str]:
    return [ln for ln in pre_tag.decode_contents().splitlines() if ln.strip()]


def _variant_line_index(lines: list[str]) -> int:
    for i, ln in enumerate(lines):
        if _VARIANT_MARKER in ln and "5'-" in ln:
            return i
    raise ValueError(f"no {_VARIANT_MARKER!r} variant line found in <pre>")


def _find_labeled_p(soup, label_prefix: str):
    for p in soup.find_all("p"):
        if p.get_text().strip().startswith(label_prefix):
            return p
    raise ValueError(f"no <p> starting with {label_prefix!r}")


def _parse_oligos(soup) -> tuple[dict[str, object], dict[str, str]]:
    oligos: dict[str, object] = {}
    kinds: dict[str, str] = {}
    for key, label, layout, kind in _OLIGO_SPECS:
        p = _find_labeled_p(soup, label)
        kinds[key] = kind
        if layout == "inline":
            oligos[key] = _inline_seq(p)
        else:  # "pre"
            pre = p.find_next_sibling("pre")
            if pre is None:
                raise ValueError(f"no <pre> after label {label!r}")
            lines = _pre_lines(pre)
            i = _variant_line_index(lines)
            fwd_line = lines[i]
            fwd = _clean_seq(fwd_line[fwd_line.find("5'-"):])
            if kind == "double_stranded":
                rev_line = lines[i + 1]
                rev = _clean_seq(rev_line[rev_line.find("3'-"):])
                oligos[key] = {"fwd": fwd, "rev": rev}
            else:
                oligos[key] = fwd
    return oligos, kinds


def _parse_final_library(soup) -> dict[str, str]:
    for h4 in soup.find_all("h4"):
        if "V3, V3.1 & V4" in h4.get_text():
            pre = h4.find_next_sibling("pre")
            if pre is None:
                raise ValueError("no <pre> after V3/V3.1/V4 library heading")
            lines = _pre_lines(pre)
            top = next(ln for ln in lines if "5'-" in ln and "-3'" in ln)
            bot = next(ln for ln in lines if "3'-" in ln and "-5'" in ln)
            strip_tags = lambda ln: re.sub(r"<[^>]+>", "", ln).strip()
            return {
                "source_label": "V3, V3.1 & V4 final library structure",
                "strand_5to3_html": top.strip(),
                "strand_3to5_html": bot.strip(),
                "strand_5to3_text": strip_tags(top),
                "strand_3to5_text": strip_tags(bot),
            }
    raise ValueError("V3/V3.1/V4 final library section not found")


def _parse_library_generation(soup) -> list[dict]:
    """The ordered 'Step-by-step library generation' section: one entry per numbered <h3> step."""
    h2 = next((h for h in soup.find_all("h2") if "step-by-step" in h.get_text().lower()), None)
    if h2 is None:
        return []
    steps: list[dict] = []
    for el in h2.find_all_next():
        if el.name == "h2":
            break  # reached the next section (Library sequencing)
        if el.name == "h3":
            title = re.sub(r"\s+", " ", el.get_text()).strip().rstrip(":")
            m = re.match(r"\((\d+)\)\s*(.*)", title)
            if m:
                steps.append({"step": int(m.group(1)), "title": m.group(2).strip(), "note": None})
            else:
                steps.append({"step": len(steps) + 1, "title": title, "note": None})
    return steps


def _parse_sequencing(soup) -> dict[str, int]:
    text = soup.get_text()
    out: dict[str, int] = {}
    m = re.search(r"(\d+)\s*cycles for V3", text)
    if m:
        out["R1_cycles"] = int(m.group(1))
    m = re.search(r"sequence cDNA,\s*(\d+)\s*cycles", text)
    if m:
        out["R2_cycles_html"] = int(m.group(1))
    m = re.search(r"\[(\d+)-bp sample index\]", text)
    if m:
        out["i7_length"] = int(m.group(1))
    return out


def parse_protocol(html_path: str | Path) -> ParsedProtocol:
    raw = Path(html_path).read_bytes()
    soup = BeautifulSoup(raw.decode("utf-8"), "lxml")
    oligos, kinds = _parse_oligos(soup)
    return ParsedProtocol(
        source_path=str(html_path),
        source_html_sha256=hashlib.sha256(raw).hexdigest(),
        oligos=oligos,
        oligo_kinds=kinds,
        final_library=_parse_final_library(soup),
        sequencing=_parse_sequencing(soup),
        library_generation=_parse_library_generation(soup),
    )
