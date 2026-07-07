"""Load + validate a simulator YAML config into a ``SimConfig``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

__all__ = ["SimConfig", "load_config"]


@dataclass
class SimConfig:
    name: str
    spec: str
    input_r1: str
    input_r2: str
    out_r1: str
    out_r2: str
    out_labels: str
    out_manifest: str
    seed: int
    failure_mode: str
    params: dict[str, Any]
    source_path: str = ""


def load_config(path: str | Path) -> SimConfig:
    d = yaml.safe_load(Path(path).read_text())
    for key in ("spec", "input", "output", "seed", "failure_mode"):
        if key not in d:
            raise ValueError(f"config {path} missing required key {key!r}")
    inp, out = d["input"], d["output"]
    return SimConfig(
        name=d.get("name", "sim"),
        spec=d["spec"],
        input_r1=inp["r1"],
        input_r2=inp["r2"],
        out_r1=out["r1"],
        out_r2=out["r2"],
        out_labels=out["labels"],
        out_manifest=out["manifest"],
        seed=int(d["seed"]),
        failure_mode=d["failure_mode"],
        params=d.get("params", {}),
        source_path=str(path),
    )
