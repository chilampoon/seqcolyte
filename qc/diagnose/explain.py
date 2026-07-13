"""Optional LLM layer: narrate the deterministic diagnosis. It NEVER computes, reorders, changes scores,
or invents causes/metrics — it only attaches plain-language explanations grounded in the given evidence.
Runs through the authenticated `claude` CLI (same wrapper as qc/planner.py); offline-safe (errors are
swallowed into a warning). Not part of any checked-in/deterministic artifact.
"""

from __future__ import annotations

import json

from qc.diagnose.model import Diagnosis

__all__ = ["EXPLAIN_SCHEMA", "explain"]

EXPLAIN_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "hypotheses"],
    "properties": {
        "summary": {"type": "string"},
        "hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["cause_id", "narrative"],
                "properties": {
                    "cause_id": {"type": "string"},
                    "narrative": {"type": "string"},
                },
            },
        },
    },
}


def explain(diagnosis: Diagnosis, *, model: str = "claude-opus-4-8") -> Diagnosis:
    """Attach an LLM narrative to the (unchanged) deterministic ranking. Returns the same Diagnosis object.
    The ranking, scores, fired signals, and metrics are never modified — only prose is added."""
    payload = {
        "note": "Explain this DETERMINISTIC diagnosis. Do NOT change order, scores, or numbers.",
        "title": diagnosis.title,
        "fired_signals": [s.to_dict() for s in diagnosis.fired_signals],
        "hypotheses": [
            {"cause_id": h.cause_id, "title": h.title, "score": h.score,
             "cell_recovery_relationship": h.cell_recovery_relationship,
             "recoverability": h.recoverability, "mechanism": h.mechanism,
             "supporting_signals": h.supporting_signals}
            for h in diagnosis.hypotheses
        ],
        "warnings": diagnosis.warnings,
    }
    prompt = (
        "You are a single-cell sequencing-QC analyst. Below is a DETERMINISTIC diagnosis: firing signals "
        "and a ranked list of candidate root-cause hypotheses with scores. Write a 2-3 sentence overall "
        "summary, and for each hypothesis a one-sentence plain-language narrative a bench scientist would "
        "act on. Ground every statement ONLY in the given signals/hypotheses — do not invent metrics, "
        "numbers, causes, or reorder anything. Return ONLY JSON matching the schema.\n\n"
        + json.dumps(payload, indent=1)
    )
    try:
        from extract.doc_extract import _run_claude

        result = _run_claude(prompt, EXPLAIN_SCHEMA, model=model)["extraction"]
    except Exception as exc:  # offline / CLI unavailable / bad output — degrade gracefully
        diagnosis.warnings.append(f"LLM explanation unavailable ({type(exc).__name__}); showing deterministic result only")
        return diagnosis

    diagnosis.summary = result.get("summary")
    narratives = {h["cause_id"]: h["narrative"] for h in result.get("hypotheses", []) if "cause_id" in h}
    for h in diagnosis.hypotheses:
        if h.cause_id in narratives:  # ignore any cause_id the model invents
            h.narrative = narratives[h.cause_id]
    return diagnosis
