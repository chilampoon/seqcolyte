"""Load + validate an input manifest from YAML/JSON. No network, no LLM."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qc.manifest.model import CellTarget, InputManifest

__all__ = ["SCHEMA_PATH", "validate_manifest", "manifest_from_dict", "load_manifest"]

SCHEMA_PATH = Path(__file__).with_name("schema.json")


def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text())


def validate_manifest(data: dict[str, Any]) -> None:
    """Validate a manifest dict against the JSON Schema. Raises ``jsonschema.ValidationError``."""
    import jsonschema

    jsonschema.validate(instance=data, schema=_schema())


def manifest_from_dict(data: dict[str, Any], *, validate: bool = True) -> InputManifest:
    if validate:
        validate_manifest(data)
    ct = data.get("cell_target")
    return InputManifest(
        schema_version=data.get("schema_version", InputManifest().schema_version),
        protocol_spec=data.get("protocol_spec"),
        fastq=list(data.get("fastq") or []),
        bam=data.get("bam"),
        feature_matrix=data.get("feature_matrix"),
        qc_evidence_reports=list(data.get("qc_evidence_reports") or []),
        reference=data.get("reference"),
        cell_target=CellTarget(**ct) if isinstance(ct, dict) else None,
        wet_lab=dict(data.get("wet_lab") or {}),
        notes=data.get("notes"),
    )


def load_manifest(path: str | Path, *, validate: bool = True) -> InputManifest:
    """Load a manifest from a .json or .yaml/.yml file."""
    p = Path(path)
    text = p.read_text()
    if p.suffix in (".yaml", ".yml"):
        import yaml

        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("manifest must be a mapping")
    return manifest_from_dict(data, validate=validate)
