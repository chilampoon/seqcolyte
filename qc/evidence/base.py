"""Safe parsing primitives + importer base class for QC evidence HTML.

Hard rules: never execute report JavaScript, never ``eval``, never render imported HTML. Embedded data
is recovered by (a) brace-matching a ``const X = {...}`` literal and ``json.loads``-ing it, or (b) scraping
``<th>``/``<td>`` table rows with BeautifulSoup. Canonical metric ids + units come from the diagnostic
catalog so the vocabulary stays single-sourced.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qc.evidence.model import EvidenceReport

# reports carry large embedded assets; cap what we read to keep parsing bounded.
MAX_BYTES = 64 * 1024 * 1024


class Importer:
    """Base class: ``probe`` returns a 0..1 confidence from content; ``parse`` builds an EvidenceReport."""

    name: str = "importer"

    def probe(self, path: str | Path) -> float:  # pragma: no cover - overridden
        raise NotImplementedError

    def parse(self, path: str | Path) -> EvidenceReport:  # pragma: no cover - overridden
        raise NotImplementedError


def read_text_capped(path: str | Path, *, max_bytes: int = MAX_BYTES) -> str:
    """Read up to ``max_bytes`` of a file as text (utf-8, errors replaced). Never executes anything."""
    data = Path(path).read_bytes()[:max_bytes]
    return data.decode("utf-8", errors="replace")


def sha256_file(path: str | Path, *, max_bytes: int = MAX_BYTES) -> str:
    h = hashlib.sha256()
    h.update(Path(path).read_bytes()[:max_bytes])
    return h.hexdigest()


def extract_js_object(text: str, varname: str) -> dict[str, Any] | None:
    """Brace-match a ``<varname> = { ... }`` JSON object literal and parse it. Returns None on miss/parse
    failure. String bodies (with escapes) are respected so braces inside strings don't terminate early.
    Never uses ``eval``."""
    import json

    m = re.search(r"(?:const|let|var|window\.)?\s*" + re.escape(varname) + r"\s*=\s*\{", text)
    if not m:
        return None
    start = text.index("{", m.end() - 1)
    depth = 0
    in_str: str | None = None
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str is not None:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == in_str:
                in_str = None
            continue
        if ch in "\"'`":
            in_str = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                blob = text[start : i + 1]
                try:
                    return json.loads(blob)
                except (ValueError, RecursionError):
                    return None
    return None


def find_nested(obj: Any, key: str) -> Any | None:
    """Depth-first search for the first dict value stored under ``key``."""
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if key in cur:
                return cur[key]
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return None


@dataclass
class KVRow:
    label: str
    value_text: str
    locator: str


def scrape_kv_tables(html: str) -> list[KVRow]:
    """Scrape two-column ``<th>label</th><td>value</td>`` rows from every table. Duplicate labels across
    tables are all returned (callers keep them as separate observations)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    rows: list[KVRow] = []
    for ti, table in enumerate(soup.find_all("table")):
        for ri, tr in enumerate(table.find_all("tr")):
            th = tr.find("th")
            td = tr.find("td")
            if th is None or td is None:
                continue
            label = th.get_text(" ", strip=True)
            value = td.get_text(" ", strip=True)
            if label and value:
                rows.append(KVRow(label=label, value_text=value, locator=f"table{ti}/row{ri}"))
    return rows


_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def parse_number(text: str) -> tuple[float | None, bool]:
    """Parse the first numeric token from ``text``. Returns (value, is_percent). Commas are stripped;
    a trailing ``%`` marks a percentage but the value is returned as-written (not yet divided)."""
    is_percent = "%" in text
    m = _NUM_RE.search(text.replace(",", ""))
    if not m:
        return None, is_percent
    try:
        return float(m.group(0)), is_percent
    except ValueError:
        return None, is_percent


# ---- catalog-driven label -> canonical metric mapping (single-sourced from the diagnostic catalog) ----

_LABEL_INDEX: dict[str, dict[str, str]] | None = None


def _label_index() -> dict[str, dict[str, str]]:
    """lowercased label -> {metric_id, unit, denominator} built from the catalog's labels + aliases."""
    global _LABEL_INDEX
    if _LABEL_INDEX is None:
        from qc.catalog.loader import load_catalog

        idx: dict[str, dict[str, str]] = {}
        for m in load_catalog().section("metrics"):
            entry = {
                "metric_id": m["metric_id"],
                "unit": m["unit"],
                "denominator": m.get("denominator", ""),
                "domain": m["domain"],
            }
            idx.setdefault(m["label"].strip().lower(), entry)
            for alias in m.get("aliases", []):
                idx.setdefault(alias["label"].strip().lower(), entry)
        _LABEL_INDEX = idx
    return _LABEL_INDEX


def map_label(label: str) -> dict[str, str] | None:
    """Resolve a report label to {metric_id, unit, denominator}, or None if unknown."""
    return _label_index().get(label.strip().lower())


def normalize_value(value: float | None, is_percent: bool, unit: str | None) -> tuple[float | None, str | None]:
    """Normalize a raw number to the canonical unit. Returns (value, note). Fractions given as percentages
    (an explicit ``%`` or a value > 1) are divided by 100 and annotated."""
    if value is None or unit != "fraction":
        return value, None
    if is_percent or value > 1.0:
        return value / 100.0, "interpreted as a percentage and divided by 100"
    return value, None
