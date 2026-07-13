"""Deterministically render committed worked-example diagnoses for the studio + docs.

Each `spec/diagnostics/examples/<id>.scenario.json` declares a manifest + a set of canonical metric
observations; this renders `<id>.diagnosis.json` (the deterministic engine output) plus an `index.json`
that the studio reads. A test re-runs this and diffs, so the checked-in examples never drift.
"""

from __future__ import annotations

import json
from pathlib import Path

from qc.diagnose.engine import diagnose
from qc.manifest.loader import manifest_from_dict

__all__ = ["EXAMPLES_DIR", "render_examples", "write_examples"]

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = REPO_ROOT / "spec" / "diagnostics" / "examples"


def _diagnosis_for(scenario: dict) -> dict:
    manifest = manifest_from_dict(scenario["manifest"]) if scenario.get("manifest") else None
    dx = diagnose(
        {k: float(v) for k, v in scenario["observations"].items()},
        manifest=manifest,
        title=scenario.get("title"),
    )
    data = dx.to_dict()
    data["scenario_id"] = scenario["scenario_id"]
    return data


def render_examples(examples_dir: Path | None = None) -> dict[str, str]:
    """Return {relpath: content} for every rendered example diagnosis + the index (does not write)."""
    base = examples_dir if examples_dir is not None else EXAMPLES_DIR
    scenarios = sorted(base.glob("*.scenario.json"))
    out: dict[str, str] = {}
    index = []
    for sp in scenarios:
        scenario = json.loads(sp.read_text())
        data = _diagnosis_for(scenario)
        rel = f"{sp.name[:-len('.scenario.json')]}.diagnosis.json"
        out[rel] = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        top = data["hypotheses"][0]["cause_id"] if data["hypotheses"] else None
        index.append(
            {
                "scenario_id": scenario["scenario_id"],
                "title": scenario.get("title"),
                "file": rel,
                "top_hypothesis": top,
            }
        )
    out["index.json"] = json.dumps(index, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    return out


def write_examples(examples_dir: Path | None = None) -> list[str]:
    base = examples_dir if examples_dir is not None else EXAMPLES_DIR
    base.mkdir(parents=True, exist_ok=True)
    written = []
    for rel, content in render_examples(base).items():
        (base / rel).write_text(content)
        written.append(rel)
    return written
