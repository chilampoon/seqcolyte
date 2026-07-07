"""Failure-mode plugin interface + shared construct primitives.

A ``FailureMode`` rewrites R2 for an affected read pair; the engine handles clean pairs and
keeps R1 byte-identical. Primitives (quality synthesis, length fitting) are shared so a new
modality (e.g. Nanopore ``tso_concatemer``) reuses them without touching the engine.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from seqcolyte.dna import homopolymer
from seqcolyte.io.fastx import FastqRecord
from seqcolyte.spec.model import Spec

__all__ = ["ReadCtx", "R2Result", "FailureMode", "synth_quality", "fit_to_length", "draw_uniform_int"]


def synth_quality(n: int, phred: int) -> str:
    """A run of ``n`` identical Phred+33 quality chars."""
    return chr(33 + phred) * n


def fit_to_length(seq: str, qual: str, target: int, pad_base: str, phred: int) -> tuple[str, str, int, bool]:
    """Pad (with ``pad_base`` at high quality) or truncate seq+qual to exactly ``target``.

    Returns (seq, qual, pad_len, truncated). Padding models the two-color no-signal poly-G tail.
    """
    if len(seq) < target:
        pad = target - len(seq)
        return seq + homopolymer(pad_base, pad), qual + synth_quality(pad, phred), pad, False
    if len(seq) > target:
        return seq[:target], qual[:target], 0, True
    return seq, qual, 0, False


def draw_uniform_int(rng: np.random.Generator, spec: dict) -> int:
    """Inclusive uniform integer from ``{'min': lo, 'max': hi}``."""
    return int(rng.integers(int(spec["min"]), int(spec["max"]) + 1))


@dataclass
class ReadCtx:
    r1: FastqRecord
    r2: FastqRecord
    spec: Spec
    params: dict
    rng: np.random.Generator
    pair_index: int
    subtype: str          # "readthrough" | "pure_dimer"
    cb: str               # this pair's cell barcode (from R1)
    umi: str              # this pair's UMI (from R1)
    r2_len: int           # original R2 length, preserved in the output


@dataclass
class R2Result:
    sequence: str
    quality: str
    construct: str                        # human-readable recipe for the labels TSV
    fields: dict[str, Any] = field(default_factory=dict)  # extra label columns


class FailureMode(ABC):
    name: str = ""
    platform: str = ""

    def applies_to(self, spec: Spec) -> bool:
        return self.platform == "" or self.platform == spec.platform

    @abstractmethod
    def build_r2(self, ctx: ReadCtx) -> R2Result:
        """Return the rewritten R2 (sequence+quality of length ``ctx.r2_len``) for an affected pair."""
