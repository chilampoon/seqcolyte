"""Discover and run external CLI tools (seqkit/seqtk) found on ``PATH``.

Keeping tool invocation behind ``shutil.which`` makes the Python package independent of
*how* the tools were installed (conda, brew, ...) — nothing here shells out to a package manager.
"""

from __future__ import annotations

import shutil
import subprocess

__all__ = ["which_tool", "require_tool", "tool_version", "run"]


def which_tool(name: str) -> str | None:
    """Absolute path to ``name`` on PATH, or None."""
    return shutil.which(name)


def require_tool(name: str) -> str:
    """Absolute path to ``name``; raise a clear error if it is missing."""
    path = which_tool(name)
    if path is None:
        raise RuntimeError(
            f"required tool {name!r} not found on PATH. "
            f"Install it (e.g. `conda env create -f environment.yml` or `brew install {name}`)."
        )
    return path


def tool_version(name: str) -> str:
    """Best-effort one-line version string for a tool (used in run manifests)."""
    path = which_tool(name)
    if path is None:
        return f"{name}: not found"
    for args in ([path, "version"], [path, "--version"], [path]):
        try:
            proc = subprocess.run(args, capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            continue
        out = (proc.stdout or "") + (proc.stderr or "")
        for line in out.splitlines():
            line = line.strip()
            if line and ("version" in line.lower() or name in line.lower() or line[0].isdigit()):
                return line
    return f"{name}: unknown version"


def run(cmd: list[str], *, check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Thin ``subprocess.run`` wrapper with sensible defaults (raises on non-zero by default)."""
    return subprocess.run(cmd, check=check, **kwargs)
