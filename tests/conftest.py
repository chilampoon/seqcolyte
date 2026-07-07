"""Shared fixtures: tiny synthetic paired FASTQs + SimConfig builders (no network, no big data)."""

from __future__ import annotations

from pathlib import Path

import pytest

from seqcolyte.io.fastx import FastqRecord, write_fastx_gz
from sim.config import SimConfig

REPO = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO / "spec" / "tenx_3p_v3.json"
HTML_PATH = REPO / "protocols" / "10xChromium3.html"

_BASES = "ACGT"


def synth_cb(i: int) -> str:
    return "".join(_BASES[(i * 7 + j * 3) % 4] for j in range(16))


def synth_umi(i: int) -> str:
    return "".join(_BASES[(i * 5 + j * 2) % 4] for j in range(12))


def synth_r2(i: int, length: int = 91) -> str:
    return "".join(_BASES[(i + j) % 4] for j in range(length))


def make_pairs(n: int) -> tuple[list[FastqRecord], list[FastqRecord]]:
    r1, r2 = [], []
    for i in range(n):
        name = f"read{i}"
        s1 = synth_cb(i) + synth_umi(i)
        r1.append(FastqRecord(name=name, sequence=s1, quality="I" * len(s1), comment="1:N:0:AAAA"))
        s2 = synth_r2(i)
        r2.append(FastqRecord(name=name, sequence=s2, quality="I" * len(s2), comment="2:N:0:AAAA"))
    return r1, r2


@pytest.fixture
def spec_path() -> str:
    return str(SPEC_PATH)


@pytest.fixture
def html_path() -> str:
    return str(HTML_PATH)


@pytest.fixture
def control(tmp_path) -> dict:
    """Write a synthetic clean control; return paths + records."""
    def _make(n: int = 200):
        r1, r2 = make_pairs(n)
        r1_path = tmp_path / "ctrl_R1.fastq.gz"
        r2_path = tmp_path / "ctrl_R2.fastq.gz"
        write_fastx_gz(str(r1_path), r1)
        write_fastx_gz(str(r2_path), r2)
        return {"r1": str(r1_path), "r2": str(r2_path), "r1_recs": r1, "r2_recs": r2, "dir": tmp_path}
    return _make


def make_config(tmp_path, r1: str, r2: str, *, seed: int = 1729, mode: str = "adapter_dimer",
                params: dict | None = None, name: str = "test") -> SimConfig:
    outdir = Path(tmp_path) / "out"
    default_params = {
        "affected_fraction": 0.30,
        "dimer_fraction": 0.33,
        "readthrough_insert_len": {"min": 0, "max": 30},
        "polyA_len": {"min": 5, "max": 20},
        "quality": {"phred": 37, "overlay_insert": True},
    }
    if params:
        default_params.update(params)
    return SimConfig(
        name=name, spec=str(SPEC_PATH), input_r1=r1, input_r2=r2,
        out_r1=str(outdir / "R1.fastq.gz"), out_r2=str(outdir / "R2.fastq.gz"),
        out_labels=str(outdir / "labels.tsv"), out_manifest=str(outdir / "run.json"),
        seed=seed, failure_mode=mode, params=default_params,
    )
