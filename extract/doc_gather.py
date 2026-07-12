"""Gather per-technology input documents from the curated protocol corpus.

The corpus lives outside the repo at ``$SEQCOLYTE_PROTOCOLS`` (default ``~/playground/protocols-test``):

    protocols/SOURCE_MANIFEST.tsv         # folder,local_file,kind,title,doi,landing_url,... (partial ledger)
    protocols/<folder>/*.pdf|*.xlsx|...   # paper + protocol + supplementary inputs (the real doc set)
    protocols/<folder>/groundtruth_*.json # normalized scg_html ground truth (cross-check oracle)
    protocol_split.tsv                    # Split \t protocol_name   (eval/test/train)

The document LIST comes from scanning each ``protocols/<folder>/`` directory (the manifest is only a
partial ledger, so we do not rely on it for coverage) — this honours "feed all documents". The manifest
enriches each file with its ``kind``/title/doi where available and supplies the technology's headline
citation. This module is the single source of truth for the ``extract wiki`` command.
"""

from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_ROOT = str(Path.home() / "playground" / "protocols-test")


def protocols_root() -> Path:
    """Corpus root, read at call time so ``$SEQCOLYTE_PROTOCOLS`` can be set per-invocation (and in tests)."""
    return Path(os.environ.get("SEQCOLYTE_PROTOCOLS", _DEFAULT_ROOT))

# Input document formats we can ingest (see extract/pdf_text.py). Anything else in a folder is ignored.
_INPUT_SUFFIXES = {".pdf", ".xlsx", ".xls", ".docx", ".doc", ".csv", ".tsv", ".txt", ".md", ".html", ".htm", ".pptx"}

# Manifest `kind` values, most-canonical first — orders docs so primary sources lead the concatenated text
# and picks the technology's headline citation.
_KIND_RANK = {
    "foundational_paper": 0, "paper": 1, "protocol_article": 2, "author_protocol": 3,
    "vendor_protocol": 4, "protocol": 5, "technical_note": 6,
    "supplement": 7, "supplement_pdf": 7, "supplement_docx": 8, "supplement_table": 9,
    "unknown": 50,
}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


@dataclass
class Doc:
    path: Path
    name: str
    kind: str
    bytes: int
    title: str | None = None
    doi: str | None = None


@dataclass
class Technology:
    folder: str
    docs: list[Doc]
    groundtruth_dir: Path
    split: str | None = None
    title: str | None = None       # headline citation (from the canonical paper row)
    doi: str | None = None
    landing_url: str | None = None
    notes: str = ""

    @property
    def has_groundtruth(self) -> bool:
        return (self.groundtruth_dir / "groundtruth_oligos.json").exists()

    @property
    def doc_paths(self) -> list[Path]:
        return [d.path for d in self.docs]


def _manifest_path() -> Path:
    return protocols_root() / "protocols" / "SOURCE_MANIFEST.tsv"


def read_manifest() -> dict[str, list[dict]]:
    """Group SOURCE_MANIFEST.tsv rows by ``folder`` (partial — not every file is listed)."""
    by_folder: dict[str, list[dict]] = {}
    p = _manifest_path()
    if p.exists():
        with p.open(newline="") as fh:
            for row in csv.DictReader(fh, delimiter="\t"):
                by_folder.setdefault(row["folder"], []).append(row)
    return by_folder


def read_split() -> dict[str, str]:
    """Map folder-slug -> split (eval/test/train) from protocol_split.tsv."""
    path = protocols_root() / "protocol_split.tsv"
    out: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            parts = line.split("\t")
            if len(parts) == 2 and parts[0].lower() != "split":
                out[_slug(parts[1])] = parts[0].strip().lower()
    return out


def _folder_docs(folder: str, rows: list[dict]) -> list[Doc]:
    by_name = {Path(r["local_file"]).name: r for r in rows}
    d = protocols_root() / "protocols" / folder
    docs: list[Doc] = []
    for f in sorted(d.iterdir()):
        if f.suffix.lower() not in _INPUT_SUFFIXES or f.name.startswith("groundtruth_"):
            continue
        r = by_name.get(f.name, {})
        docs.append(Doc(path=f, name=f.name, kind=(r.get("kind") or "").strip() or "unknown",
                        bytes=f.stat().st_size, title=r.get("title") or None, doi=r.get("doi") or None))
    docs.sort(key=lambda x: (_KIND_RANK.get(x.kind, 99), x.bytes))
    return docs


def technology(folder: str, rows: list[dict], split: dict[str, str]) -> Technology:
    docs = _folder_docs(folder, rows)
    cite = next((d for d in docs if d.doi and d.kind in ("foundational_paper", "paper")), None) \
        or next((d for d in docs if d.doi), docs[0] if docs else None)
    return Technology(
        folder=folder,
        docs=docs,
        groundtruth_dir=protocols_root() / "protocols" / folder,
        split=split.get(_slug(folder)),
        title=cite.title if cite else None,
        doi=cite.doi if cite else None,
        landing_url=next((r.get("landing_url") for r in rows if r.get("landing_url")), None),
        notes="; ".join(r.get("notes", "") for r in rows if r.get("notes")).strip("; "),
    )


def list_technology_folders() -> list[str]:
    """All protocol dirs that carry ground truth (the authoritative technology set)."""
    base = protocols_root() / "protocols"
    return sorted(p.name for p in base.iterdir()
                  if p.is_dir() and (p / "groundtruth_oligos.json").exists())


def get_technology(folder: str) -> Technology:
    return technology(folder, read_manifest().get(folder, []), read_split())


def list_technologies() -> list[Technology]:
    manifest, split = read_manifest(), read_split()
    return [technology(f, manifest.get(f, []), split) for f in list_technology_folders()]
