"""Deterministic validation of the diagnostic catalog: JSON Schema + cross-reference integrity.

No network, no LLM. ``validate_or_raise`` is the entry point used by the CLI and tests.
"""

from __future__ import annotations

from typing import Any

from qc.catalog.loader import Catalog, load_catalog, load_schema

__all__ = ["CatalogError", "validate_catalog", "validate_or_raise"]


class CatalogError(ValueError):
    """Raised when the catalog fails schema or cross-reference validation."""


# (section, field, target_section, is_list) — each referenced id must resolve in target_section.
_REFS: list[tuple[str, str, str, bool]] = [
    ("metrics", "references", "references", True),
    ("signals", "metrics", "metrics", True),
    ("signals", "related_causes", "root_causes", True),
    ("signals", "references", "references", True),
    ("issues", "supporting_signals", "signals", True),
    ("issues", "contradicting_signals", "signals", True),
    ("issues", "candidate_root_causes", "root_causes", True),
    ("issues", "confirmatory_tests", "diagnostic_tests", True),
    ("issues", "recovery_classes", "recovery_actions", True),
    ("issues", "related_issues", "issues", True),
    ("issues", "references", "references", True),
    ("root_causes", "produces_issues", "issues", True),
    ("root_causes", "observable_signals", "signals", True),
    ("root_causes", "evidence_against", "signals", True),
    ("root_causes", "diagnostic_tests", "diagnostic_tests", True),
    ("root_causes", "recoverability", "recovery_actions", False),
    ("root_causes", "references", "references", True),
    ("diagnostic_tests", "supports_causes", "root_causes", True),
    ("diagnostic_tests", "rejects_causes", "root_causes", True),
    ("diagnostic_tests", "references", "references", True),
]

_ID_FIELD = {
    "metrics": "metric_id",
    "signals": "signal_id",
    "issues": "issue_id",
    "root_causes": "cause_id",
    "diagnostic_tests": "test_id",
    "recovery_actions": "recovery_class",
    "references": "reference_id",
}


def _schema_errors(catalog: Catalog) -> list[str]:
    import jsonschema

    validator = jsonschema.Draft202012Validator(load_schema())
    out = []
    for err in sorted(validator.iter_errors(catalog.raw), key=lambda e: list(e.absolute_path)):
        loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
        out.append(f"schema: {loc}: {err.message}")
    return out


def validate_catalog(catalog: Catalog) -> list[str]:
    """Return a list of human-readable validation errors (empty list == valid)."""
    errors: list[str] = []

    # 1. schema
    errors.extend(_schema_errors(catalog))

    # 2. id uniqueness per section
    id_sets: dict[str, set[str]] = {}
    for section, field in _ID_FIELD.items():
        seen: set[str] = set()
        for item in catalog.section(section):
            if not isinstance(item, dict) or field not in item:
                continue
            _id = item[field]
            if _id in seen:
                errors.append(f"duplicate id in {section}: {_id!r}")
            seen.add(_id)
        id_sets[section] = seen

    # 3. cross-references resolve
    for section, field, target, is_list in _REFS:
        valid = id_sets.get(target, set())
        tid_field = _ID_FIELD[section]
        for item in catalog.section(section):
            if not isinstance(item, dict) or field not in item:
                continue
            owner = item.get(tid_field, "<unknown>")
            values = item[field] if is_list else [item[field]]
            for ref in values:
                if ref not in valid:
                    errors.append(
                        f"{section}[{owner}].{field}: unresolved reference {ref!r} (not a valid {target} id)"
                    )

    # 4. every issue has at least one supporting signal or required-evidence scope
    for issue in catalog.section("issues"):
        if not isinstance(issue, dict):
            continue
        iid = issue.get("issue_id", "<unknown>")
        if not issue.get("supporting_signals") and not issue.get("required_evidence"):
            errors.append(f"issues[{iid}]: must declare at least one supporting_signal or required_evidence")

    # 5. every root cause declares a cell-recovery relationship + recoverability
    for cause in catalog.section("root_causes"):
        if not isinstance(cause, dict):
            continue
        cid = cause.get("cause_id", "<unknown>")
        rel = cause.get("cell_recovery_relationship")
        if not (isinstance(rel, dict) and rel.get("relationship") and rel.get("note")):
            errors.append(f"root_causes[{cid}]: must declare cell_recovery_relationship (relationship + note)")
        if not cause.get("recoverability"):
            errors.append(f"root_causes[{cid}]: must declare recoverability")

    return errors


def validate_or_raise(catalog: Catalog | None = None) -> Catalog:
    """Validate the catalog (loading the default if none given); raise :class:`CatalogError` on failure."""
    cat = catalog if catalog is not None else load_catalog()
    errors = validate_catalog(cat)
    if errors:
        raise CatalogError(
            f"diagnostic catalog failed validation ({len(errors)} error(s)):\n  - "
            + "\n  - ".join(errors)
        )
    return cat
