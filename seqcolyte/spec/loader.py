"""Load + schema-validate a consolidated spec JSON into a :class:`Spec`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from seqcolyte.spec.model import Spec

__all__ = ["load_spec", "validate_spec", "SCHEMA_PATH"]

SCHEMA_PATH = Path(__file__).with_name("schema.json")


def _load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text())


def validate_spec(data: dict[str, Any]) -> None:
    """Validate a spec dict against the JSON Schema. Raises ``jsonschema.ValidationError``."""
    import jsonschema

    jsonschema.validate(instance=data, schema=_load_schema())


def load_spec(path: str | Path, *, validate: bool = True) -> Spec:
    """Read, optionally validate, and wrap a consolidated spec JSON."""
    data = json.loads(Path(path).read_text())
    if validate:
        validate_spec(data)
    return Spec(data)
