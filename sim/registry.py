"""Failure-mode plugin registry. Modes self-register via ``@register``; ``sim.modes`` imports
each module so registration happens on import."""

from __future__ import annotations

from sim.base import FailureMode

__all__ = ["register", "get_mode", "known_modes"]

_REGISTRY: dict[str, type[FailureMode]] = {}


def register(cls: type[FailureMode]) -> type[FailureMode]:
    if not cls.name:
        raise ValueError(f"{cls.__name__} must set a non-empty `name`")
    _REGISTRY[cls.name] = cls
    return cls


def get_mode(name: str) -> FailureMode:
    import sim.modes  # noqa: F401  (ensure all modes are registered)

    try:
        return _REGISTRY[name]()
    except KeyError:
        raise KeyError(f"unknown failure mode {name!r}; known: {sorted(_REGISTRY)}") from None


def known_modes() -> list[str]:
    import sim.modes  # noqa: F401

    return sorted(_REGISTRY)
