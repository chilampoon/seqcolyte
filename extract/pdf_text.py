"""Extract text from a protocol PDF with **docling** — capturing text inside tables and figures.

docling reconstructs document structure far better than a raw text layer: TableFormer rebuilds
tables (oligo tables survive as tables), OCR recovers text baked into raster figures, and the
Markdown export preserves reading order + headings for the downstream LLM extractor.

Caveat handled here: docling's layout model buckets *vector-text* diagram panels (e.g. 10x's
"Oligonucleotide Sequences" page, where the DNA sequences are drawn as a figure) into `picture`
clusters and drops their text. To honour "output all text within figures and tables" for those
panels, we append the PDF **text layer** (via pypdfium2, docling's own backend — no pypdf) so no
vector/figure text is lost. Set ``full_page_ocr=True`` for scanned/image-only PDFs.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["extract_text", "docling_markdown", "text_layer"]

_TEXT_LAYER_HEADER = "\n\n## Appendix: raw PDF text layer (figure/vector text docling may not emit)\n\n"


def docling_markdown(pdf_path: str | Path, *, full_page_ocr: bool = False) -> str:
    """docling structured Markdown: tables reconstructed, raster-figure text OCR'd."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions()
    opts.do_table_structure = True   # reconstruct tables -> all text within tables
    opts.do_ocr = True               # OCR raster figures -> text within (raster) figures
    if full_page_ocr:
        opts.ocr_options.force_full_page_ocr = True
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
    return converter.convert(str(pdf_path)).document.export_to_markdown()


def text_layer(pdf_path: str | Path) -> str:
    """Raw PDF text layer via pypdfium2 (docling's backend) — recovers vector-text figure content."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        return "\n".join(pdf[i].get_textpage().get_text_range() for i in range(len(pdf)))
    finally:
        pdf.close()


def extract_text(pdf_path: str | Path, *, full_page_ocr: bool = False,
                 include_text_layer: bool = True) -> str:
    """docling Markdown (structure + tables + figure OCR), plus the raw text layer appended so
    vector-text figures docling drops are still captured."""
    md = docling_markdown(pdf_path, full_page_ocr=full_page_ocr)
    if include_text_layer:
        md += _TEXT_LAYER_HEADER + text_layer(pdf_path)
    return md
