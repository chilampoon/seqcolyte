"""Pure DNA-sequence utilities. Standard-library only — the one implementation of
reverse-complement shared by the spec builder, the simulator, and (later) QC."""

from __future__ import annotations

__all__ = ["complement", "revcomp", "is_dna", "homopolymer"]

_COMPLEMENT = str.maketrans("ACGTNacgtn", "TGCANtgcan")
_ACGT = frozenset("ACGT")
_ACGTN = frozenset("ACGTN")


def complement(seq: str) -> str:
    """Base complement (A<->T, C<->G, N->N); case preserved. Unmapped chars pass through."""
    return seq.translate(_COMPLEMENT)


def revcomp(seq: str) -> str:
    """Reverse complement, returned 5'->3'. N maps to N. Input expected to be ACGTN."""
    return seq.translate(_COMPLEMENT)[::-1]


def is_dna(seq: str, *, allow_n: bool = True) -> bool:
    """True iff ``seq`` is non-empty and drawn only from ACGT (plus N when ``allow_n``)."""
    if not seq:
        return False
    alphabet = _ACGTN if allow_n else _ACGT
    return set(seq.upper()) <= alphabet


def homopolymer(base: str, n: int) -> str:
    """A run of ``n`` copies of a single base: ``homopolymer('A', 5) == 'AAAAA'``."""
    if len(base) != 1:
        raise ValueError(f"base must be a single character, got {base!r}")
    if n < 0:
        raise ValueError(f"n must be >= 0, got {n}")
    return base * n
