"""Invoke the `seqcolyte-qc` Rust binary for the QC compute core (profiling + checks + eval).

This mirrors how ``extract/doc_extract.py`` shells out to the ``claude`` CLI: build an argv,
run it, parse JSON from stdout. The binary streams the FASTQ pair in one pass and returns
``{"profile": {...}, "findings": [...], "eval": {...}|null}`` that is field-for-field identical
to the pure-Python compute path (guarded by ``tests/test_rust_parity.py``).

Locate the binary via ``$SEQCOLYTE_QC_BIN`` or the crate's default release path. Raise
``RustEngineUnavailable`` when it's missing/unbuilt so callers can fall back to Python.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

__all__ = ["run_rust_qc", "rust_binary", "RustEngineUnavailable"]

_DEFAULT_BIN = (
    Path(__file__).resolve().parent.parent
    / "rust" / "seqcolyte-qc" / "target" / "release" / "seqcolyte-qc"
)


class RustEngineUnavailable(RuntimeError):
    """The seqcolyte-qc binary could not be found (build it with `make rust`)."""


def rust_binary() -> Path:
    env = os.environ.get("SEQCOLYTE_QC_BIN")
    return Path(env) if env else _DEFAULT_BIN


def run_rust_qc(spec_path: str, r1: str, r2: str, *, whitelist: str | None = None,
                labels: str | None = None, max_reads: int | None = None) -> dict:
    binary = rust_binary()
    if not binary.exists():
        raise RustEngineUnavailable(f"seqcolyte-qc binary not found at {binary}")

    cmd = [str(binary), "--spec", spec_path, "--r1", r1, "--r2", r2]
    if whitelist:
        cmd += ["--whitelist", whitelist]
    if labels:
        cmd += ["--labels", labels]
    if max_reads is not None:
        cmd += ["--max-reads", str(max_reads)]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"seqcolyte-qc failed ({proc.returncode}): {proc.stderr.strip()[:500]}")
    return json.loads(proc.stdout)
