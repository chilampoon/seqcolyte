"""Validate/serialize QC evidence reports against schema.json. No network, no LLM."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qc.evidence.model import EvidenceReport

__all__ = ["SCHEMA_PATH", "validate_evidence", "load_evidence_json", "dump_evidence_json"]

SCHEMA_PATH = Path(__file__).with_name("schema.json")


def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text())


def validate_evidence(data: dict[str, Any]) -> None:
    """Validate an evidence-report dict against the JSON Schema. Raises ``jsonschema.ValidationError``."""
    import jsonschema

    jsonschema.validate(instance=data, schema=_schema())


def dump_evidence_json(report: EvidenceReport, *, validate: bool = True) -> str:
    data = report.to_dict()
    if validate:
        validate_evidence(data)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def load_evidence_json(path: str | Path, *, validate: bool = True) -> dict[str, Any]:
    data = json.loads(Path(path).read_text())
    if validate:
        validate_evidence(data)
    return data
