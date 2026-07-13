"""Offline tests for the typed input manifest + cell-target compatibility."""

from __future__ import annotations

import pytest

from qc.manifest.loader import manifest_from_dict, validate_manifest
from qc.manifest.model import CellTarget, target_attainment


def _manifest(target_type: str):
    return manifest_from_dict(
        {
            "schema_version": "seqcolyte.input_manifest.v1",
            "cell_target": {"value": 45000, "target_type": target_type, "confidence": "high"},
        }
    )


def test_compatible_target_yields_attainment():
    m = _manifest("expected_recovered_cells")
    att, warn = target_attainment(2000, m.cell_target)
    assert att == pytest.approx(2000 / 45000)
    assert warn is None


def test_incompatible_target_is_not_compared():
    m = _manifest("cells_loaded")
    att, warn = target_attainment(2000, m.cell_target)
    assert att is None
    assert warn and "not comparable" in warn


def test_missing_optional_inputs_validate():
    validate_manifest({"schema_version": "seqcolyte.input_manifest.v1"})  # no cell_target, no fastq — fine


def test_bad_target_type_fails_schema():
    import jsonschema

    with pytest.raises(jsonschema.ValidationError):
        validate_manifest(
            {
                "schema_version": "seqcolyte.input_manifest.v1",
                "cell_target": {"value": 100, "target_type": "not_a_real_type"},
            }
        )


def test_nonpositive_target_value_fails_schema():
    import jsonschema

    with pytest.raises(jsonschema.ValidationError):
        validate_manifest(
            {
                "schema_version": "seqcolyte.input_manifest.v1",
                "cell_target": {"value": 0, "target_type": "expected_recovered_cells"},
            }
        )


def test_comparable_helper():
    assert CellTarget(45000, "expected_called_cells").comparable_with_called()
    assert not CellTarget(45000, "viable_cells_loaded").comparable_with_called()
