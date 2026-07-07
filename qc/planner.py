"""The 'decide' step (hybrid): Claude reads the spec context + the deterministic findings and ranks
them by severity, names the most likely root cause, and writes a plain-language diagnosis. Runs
through the authenticated `claude` CLI (reuses the headless wrapper) — no API key needed."""

from __future__ import annotations

import json

from extract.doc_extract import _run_claude

__all__ = ["rank_with_llm", "RANK_SCHEMA"]

RANK_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ranked", "root_cause", "diagnosis"],
    "properties": {
        "ranked": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["check_id", "severity", "why"],
                "properties": {
                    "check_id": {"type": "string"},
                    "severity": {"type": "string", "enum": ["none", "low", "medium", "high"]},
                    "why": {"type": "string"},
                },
            },
        },
        "root_cause": {"type": "string"},
        "diagnosis": {"type": "string"},
    },
}


def rank_with_llm(spec, profile, findings, *, model: str) -> dict:
    payload = {
        "assay": spec.assay, "platform": spec.platform, "chemistry": spec.chemistry_version,
        "profile": profile.summary(),
        "findings": [f.to_dict() for f in findings],
    }
    prompt = (
        "You are a sequencing-QC analyst. You are given the EXPECTED library structure "
        "(assay/platform/chemistry) and a set of DETERMINISTIC check findings computed on the raw "
        "FASTQ. Decide which findings most severely indicate a real library-prep or sequencing "
        "FAILURE, rank them (highest severity first), name the single most likely ROOT CAUSE, and "
        "write a 2-3 sentence plain-language diagnosis a bench scientist would act on. Ground every "
        "statement in the given findings and spec — do not invent numbers. Return ONLY the JSON.\n\n"
        + json.dumps(payload, indent=1)
    )
    return _run_claude(prompt, RANK_SCHEMA, model=model)["extraction"]
