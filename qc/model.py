"""QC data model + sequence-pattern helpers (pure, testable)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

__all__ = [
    "DataProfile", "Finding", "fraction", "startswith_fuzzy", "has_homopolymer_tail",
]


def fraction(flags: Iterable[bool]) -> float:
    flags = list(flags)
    return sum(flags) / len(flags) if flags else 0.0


def startswith_fuzzy(seq: str, pattern: str, max_mismatch: int = 2) -> bool:
    """True if ``seq`` begins with ``pattern`` allowing up to ``max_mismatch`` substitutions."""
    if len(seq) < len(pattern):
        return False
    mm = 0
    for a, b in zip(seq, pattern):
        if a != b:
            mm += 1
            if mm > max_mismatch:
                return False
    return True


def has_homopolymer_tail(seq: str, base: str, *, window: int = 20, min_run: int = 15, tol: int = 3) -> bool:
    """True if the 3' end of ``seq`` is a (near-pure) run of ``base`` — e.g. a poly-G no-signal tail."""
    if len(seq) < min_run:
        return False
    tail = seq[-window:]
    return tail.count(base) >= len(tail) - tol


@dataclass
class DataProfile:
    n_pairs: int
    r1: list[str]
    r2: list[str]

    @classmethod
    def from_reads(cls, r1: list[str], r2: list[str]) -> "DataProfile":
        return cls(n_pairs=len(r1), r1=r1, r2=r2)

    def _len_stats(self, seqs: list[str]) -> dict:
        lens = [len(s) for s in seqs]
        modal = Counter(lens).most_common(1)[0][0] if lens else 0
        return {"min": min(lens) if lens else 0, "max": max(lens) if lens else 0, "modal": modal}

    def summary(self) -> dict:
        """Compact, read-free summary safe to hand to the LLM planner."""
        return {"n_pairs": self.n_pairs, "r1_len": self._len_stats(self.r1), "r2_len": self._len_stats(self.r2)}


@dataclass
class Finding:
    check_id: str
    title: str
    verdict: str                 # pass | warn | fail
    value: float | None
    unit: str
    threshold: str
    affected_fraction: float | None
    severity: float              # 0..1
    evidence: list[dict] = field(default_factory=list)
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "check_id": self.check_id, "title": self.title, "verdict": self.verdict,
            "value": self.value, "unit": self.unit, "threshold": self.threshold,
            "affected_fraction": self.affected_fraction, "severity": round(self.severity, 4),
            "evidence": self.evidence, "detail": self.detail,
        }
