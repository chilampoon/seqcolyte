"""Deterministic per-read RNG. Keying by (seed, pair_index) makes every read's draws
independent of chunking/threads/order — the whole run is reproducible from one seed."""

from __future__ import annotations

import numpy as np

__all__ = ["read_rng"]


def read_rng(seed: int, pair_index: int) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence([int(seed), int(pair_index)]))
