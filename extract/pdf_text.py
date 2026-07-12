"""Extract text from a protocol document (PDF / text / Excel / office formats).

PDFs go through **docling** — capturing text inside tables and figures — with a text-layer
appendix (below); plain text is read as-is; other formats (xlsx/docx/html) use docling too.

docling reconstructs document structure far better than a raw text layer: TableFormer rebuilds
tables (oligo tables survive as tables) and the Markdown export preserves reading order + headings
for the downstream LLM extractor. **OCR is disabled** — it added nothing here (RapidOCR returned
empty on the vector-text sequence panels) and risks misreading exact DNA sequences.

Caveat handled here: docling's layout model buckets *vector-text* diagram panels (e.g. 10x's
"Oligonucleotide Sequences" page, where the DNA sequences are drawn as a figure) into `picture`
clusters and drops their text. To honour "output all text within figures and tables" for those
panels, we append the PDF **text layer** (via pypdfium2, docling's own backend — no pypdf) so no
vector/figure text is lost.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["extract_text", "extract_texts", "docling_markdown", "text_layer"]

_TEXT_LAYER_HEADER = "\n\n## Appendix: raw PDF text layer (figure/vector text docling may not emit)\n\n"


def docling_markdown(pdf_path: str | Path) -> str:
    """docling structured Markdown: tables reconstructed (TableFormer); OCR disabled."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions()
    opts.do_table_structure = True   # reconstruct tables -> all text within tables
    opts.do_ocr = False              # OCR disabled (per request); figure text comes from the text layer
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
    return converter.convert(str(pdf_path)).document.export_to_markdown()


def text_layer(pdf_path: str | Path) -> str:
    """Raw PDF text layer via pypdfium2 (docling's backend) — recovers vector-text figure content."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        # get_text_bounded() with no bounds == full page; get_text_range() aliases to it but warns.
        return "\n".join(pdf[i].get_textpage().get_text_bounded() for i in range(len(pdf)))
    finally:
        pdf.close()


# Text-based formats we can read straight off disk (no parser needed).
_PLAINTEXT_SUFFIXES = {".txt", ".text", ".md", ".markdown", ".rst", ".csv", ".tsv", ".html", ".htm", ".xml"}


def extract_text(doc_path: str | Path, *, include_text_layer: bool = True) -> str:
    """Extract a protocol document's text — PDF, plain text/HTML, or a binary office format.

    - ``.pdf`` -> docling Markdown (tables reconstructed) + the pypdfium2 text layer (so vector-text
      figures docling buckets as pictures are still captured).
    - text / markdown / csv / **html** -> read as-is (all already text).
    - ``.xlsx`` / ``.xls`` / ``.docx`` / ``.pptx`` (zipped-XML office formats) -> docling's converter,
      because reading their raw bytes yields the zip container, not text.
    """
    path = Path(doc_path)
    suffix = path.suffix.lower()
    if suffix in _PLAINTEXT_SUFFIXES:
        return path.read_text()
    if suffix == ".pdf":
        md = docling_markdown(path)
        if include_text_layer:
            md += _TEXT_LAYER_HEADER + text_layer(path)
        return md
    if suffix == ".xls":
        return _xls_text(path)  # docling only reads .xlsx; legacy .xls goes through pandas + xlrd
    return docling_markdown(path)  # xlsx / docx / pptx / … handled by docling's format backends


def _xls_text(path: str | Path) -> str:
    """Legacy .xls (BIFF) → text: every sheet as CSV (pandas + xlrd). Oligo tables often live here."""
    import pandas as pd

    sheets = pd.read_excel(path, sheet_name=None)  # needs xlrd>=2.0.1 for .xls
    return "\n\n".join(f"## Sheet: {name}\n{df.to_csv(index=False)}" for name, df in sheets.items())


def _fair_caps(lengths: list[int], budget: int) -> list[int]:
    """Water-filling: give every doc at least an equal share; short docs keep their full text and free
    budget is redistributed to the longer docs. Guarantees each doc keeps >0 chars (nothing dropped)."""
    caps = [0] * len(lengths)
    remaining, left = budget, len(lengths)
    for i in sorted(range(len(lengths)), key=lambda i: lengths[i]):
        share = max(1, remaining // left)
        caps[i] = min(lengths[i], share)
        remaining -= caps[i]
        left -= 1
    return caps


def extract_texts(
    paths, *, char_budget: int = 1_800_000, include_text_layer: bool = True
) -> tuple[str, list[dict]]:
    """Extract + concatenate several documents into one blob for a single LLM extraction.

    Every document contributes (nothing is silently dropped): each file is extracted, then if the total
    exceeds ``char_budget`` the largest docs are truncated (water-filling) so the concatenation fits the
    model context. Returns ``(combined_text, log)`` where ``log`` records per-doc kept/total chars and
    whether it was truncated. Docs are joined with ``=== DOCUMENT: <name> ===`` separators.
    """
    extracted: list[tuple[str, str]] = []
    for p in paths:
        name = Path(p).name
        try:
            extracted.append((name, extract_text(p, include_text_layer=include_text_layer)))
        except Exception as exc:  # keep going — one unreadable supplement shouldn't sink the whole tech
            extracted.append((name, f"[could not extract {name}: {exc}]"))

    lengths = [len(t) for _, t in extracted]
    total = sum(lengths)
    caps = lengths if total <= char_budget else _fair_caps(lengths, char_budget)

    parts, log = [], []
    for (name, text), cap, full in zip(extracted, caps, lengths):
        truncated = cap < full
        body = text[:cap] + (f"\n…[truncated {full - cap} of {full} chars]" if truncated else "")
        parts.append(f"=== DOCUMENT: {name} ===\n{body}")
        log.append({"name": name, "chars": full, "kept": cap, "truncated": truncated})
    return "\n\n".join(parts), log
