"""Check registry. Each check is ``fn(profile, spec, resources) -> Finding | None`` (None = not
applicable, e.g. a whitelist check with no whitelist, or a poly-G check on a non-two-color platform)."""

from __future__ import annotations

from typing import Callable

_CHECKS: list[tuple[str, Callable]] = []


def register(check_id: str):
    def deco(fn: Callable) -> Callable:
        _CHECKS.append((check_id, fn))
        return fn
    return deco


def registered_checks() -> list[tuple[str, Callable]]:
    import qc.checks  # noqa: F401  (ensure checks are registered)
    return list(_CHECKS)
