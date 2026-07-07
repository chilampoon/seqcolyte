"""Extract plain text from a protocol PDF (pypdf). Deterministic, offline."""

from __future__ import annotations

from pathlib import Path

__all__ = ["extract_text"]


def extract_text(pdf_path: str | Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)
