"""Ground-truth labels TSV — one row per read pair, fixed column order."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping

__all__ = ["LABEL_COLUMNS", "write_labels"]

LABEL_COLUMNS = [
    "read_id", "pair_index", "label", "failure_mode", "affected",
    "r1_len", "r2_len", "cb", "umi",
    "insert_len", "polyA_len", "pad_len", "truncated", "construct",
]


def write_labels(path: str | Path, rows: Iterable[Mapping[str, object]]) -> int:
    lines = ["\t".join(LABEL_COLUMNS)]
    n = 0
    for row in rows:
        lines.append("\t".join(str(row.get(col, "")) for col in LABEL_COLUMNS))
        n += 1
    Path(path).write_text("\n".join(lines) + "\n")
    return n
