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

__all__ = ["extract_text", "docling_markdown", "text_layer"]

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
    return docling_markdown(path)  # xlsx / docx / pptx / … handled by docling's format backends
