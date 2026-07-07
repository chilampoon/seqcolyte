"""Profile a FASTQ pair into an in-memory ``DataProfile`` the checks read from (one pass)."""

from __future__ import annotations

from seqcolyte.io.fastx import iter_pairs
from qc.model import DataProfile

__all__ = ["profile"]


def profile(r1_path: str, r2_path: str, *, max_reads: int | None = None) -> DataProfile:
    r1: list[str] = []
    r2: list[str] = []
    for i, (a, b) in enumerate(iter_pairs(r1_path, r2_path)):
        if max_reads is not None and i >= max_reads:
            break
        r1.append(a.sequence)
        r2.append(b.sequence)
    return DataProfile.from_reads(r1, r2)
