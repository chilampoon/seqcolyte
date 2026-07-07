"""The read-structure spec: the single source of truth that ``extract/`` produces and
``sim/`` (and later QC) consume."""

from seqcolyte.spec.loader import load_spec, validate_spec, SCHEMA_PATH
from seqcolyte.spec.model import Spec

__all__ = ["Spec", "load_spec", "validate_spec", "SCHEMA_PATH"]
