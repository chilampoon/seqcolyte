"""Load the diagnostic catalog YAML into a lightweight, indexed :class:`Catalog`. No network, no LLM."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["Catalog", "load_catalog", "CATALOG_PATH", "SCHEMA_PATH"]

CATALOG_PATH = Path(__file__).with_name("diagnostic_catalog.yaml")
SCHEMA_PATH = Path(__file__).with_name("schema.json")

# section name -> the id field used by items in that section
_ID_FIELD = {
    "metrics": "metric_id",
    "signals": "signal_id",
    "issues": "issue_id",
    "root_causes": "cause_id",
    "diagnostic_tests": "test_id",
    "recovery_actions": "recovery_class",
    "references": "reference_id",
}


@dataclass
class Catalog:
    """A parsed diagnostic catalog with per-section id indexes."""

    raw: dict[str, Any]

    def section(self, name: str) -> list[dict[str, Any]]:
        return list(self.raw.get(name) or [])

    def ids(self, name: str) -> set[str]:
        field = _ID_FIELD[name]
        return {item[field] for item in self.section(name) if field in item}

    def index(self, name: str) -> dict[str, dict[str, Any]]:
        field = _ID_FIELD[name]
        return {item[field]: item for item in self.section(name) if field in item}

    @property
    def all_ids(self) -> set[str]:
        out: set[str] = set()
        for name in _ID_FIELD:
            out |= self.ids(name)
        return out


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text())


def load_catalog(path: str | Path | None = None) -> Catalog:
    """Read and parse the catalog YAML (no validation — call :mod:`qc.catalog.validate` for that)."""
    import yaml

    p = Path(path) if path is not None else CATALOG_PATH
    data = yaml.safe_load(p.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"catalog root must be a mapping, got {type(data).__name__}")
    return Catalog(data)
