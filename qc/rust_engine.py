"""Invoke the `qc-core` Rust binary for the QC compute core (profiling + checks + eval).

This mirrors how ``extract/doc_extract.py`` shells out to the ``claude`` CLI: build an argv,
run it, parse JSON from stdout. The binary streams the FASTQ pair in one pass and returns
``{"profile": {...}, "findings": [...], "eval": {...}|null}`` — the sole QC compute path.
``tests/test_rust_qc.py`` pins that output against a committed golden.

Locate the binary via ``$SEQCOLYTE_QC_BIN`` or the crate's default release path. Raise
``RustEngineUnavailable`` when it's missing/unbuilt (build it with ``make rust`` / ``seqcolyte core``).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

__all__ = ["run_rust_qc", "rust_binary", "RustEngineUnavailable"]

_DEFAULT_BIN = (
    Path(__file__).resolve().parent
    / "core" / "target" / "release" / "qc-core"
)


class RustEngineUnavailable(RuntimeError):
    """The qc-core binary could not be found (build it with `make rust`)."""


def rust_binary() -> Path:
    env = os.environ.get("SEQCOLYTE_QC_BIN")
    return Path(env) if env else _DEFAULT_BIN


def run_rust_qc(spec_path: str, r1: str, r2: str, *, whitelist: str | None = None,
                labels: str | None = None, max_reads: int | None = None) -> dict:
    binary = rust_binary()
    if not binary.exists():
        raise RustEngineUnavailable(f"qc-core binary not found at {binary}")

    cmd = [str(binary), "--spec", spec_path, "--r1", r1, "--r2", r2]
    if whitelist:
        cmd += ["--whitelist", whitelist]
    if labels:
        cmd += ["--labels", labels]
    if max_reads is not None:
        cmd += ["--max-reads", str(max_reads)]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"qc-core failed ({proc.returncode}): {proc.stderr.strip()[:500]}")
    return json.loads(proc.stdout)
