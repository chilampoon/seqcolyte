"""Deterministically render the catalog into checked-in artifacts:

  - spec/diagnostics/catalog.json   (consumed by the studio Diagnostic Wiki)
  - docs/qc/diagnostics.md          (human-readable catalog)
  - docs/qc/metric-glossary.md      (canonical metric glossary)

Pure functions, stable ordering; tests/test_diagnostic_catalog.py re-runs this and diffs the tree.
No network, no LLM.
"""

from __future__ import annotations

import json
from pathlib import Path

from qc.catalog.loader import Catalog, load_catalog

__all__ = ["render_artifacts", "write_artifacts", "REPO_ROOT", "ARTIFACTS"]

REPO_ROOT = Path(__file__).resolve().parents[2]

# relpath (posix) -> produced content; the keys are the checked-in artifacts.
ARTIFACTS = ("spec/diagnostics/catalog.json", "docs/qc/diagnostics.md", "docs/qc/metric-glossary.md")


def _md_escape(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def catalog_json(cat: Catalog) -> str:
    return json.dumps(cat.raw, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join(_md_escape(c) for c in row) + " |")
    return "\n".join(out)


def diagnostics_md(cat: Catalog) -> str:
    L: list[str] = []
    L.append("# Seqcolyte diagnostic catalog")
    L.append("")
    L.append(
        "> Generated from `qc/catalog/diagnostic_catalog.yaml` by `python -m qc.catalog render`. "
        "Do not edit by hand."
    )
    L.append("")
    L.append(f"Catalog version: `{cat.raw.get('catalog_version', '?')}`")
    L.append("")

    L.append("## Conceptual model")
    L.append("")
    L.append("```")
    L.append("metric -> signal -> issue -> root cause -> diagnostic test -> impact -> recovery action")
    L.append("```")
    L.append("")
    L.append(
        "A **metric** is a measured value. A **signal** is an abnormal pattern in one or more metrics. "
        "An **issue** is the user-facing problem. A **root cause** is a candidate mechanism. A "
        "**diagnostic test** is a deterministic analysis that supports or rejects a cause. A **recovery "
        "action** classifies how recoverable the outcome is. The LLM may later rank/explain candidate "
        "causes, but never computes, changes, or fabricates deterministic metrics."
    )
    L.append("")

    L.append("## Issue families")
    L.append("")
    for issue in cat.section("issues"):
        L.append(f"### {issue['title']}  (`{issue['issue_id']}`)")
        L.append("")
        L.append(issue["summary"])
        L.append("")
        L.append(f"- **Outcome domains:** {', '.join(issue['outcome_domains'])}")
        L.append(f"- **Platforms:** {', '.join(issue['platforms'])}")
        L.append(f"- **Workflow stages:** {', '.join(issue['workflow_stages'])}")
        L.append(f"- **Supporting signals:** {', '.join(issue.get('supporting_signals', [])) or '—'}")
        L.append(f"- **Candidate root causes:** {', '.join(issue['candidate_root_causes'])}")
        L.append(f"- **Confirmatory tests:** {', '.join(issue.get('confirmatory_tests', [])) or '—'}")
        L.append(f"- **Recovery classes:** {', '.join(issue['recovery_classes'])}")
        L.append(f"- **Cannot explain:** {issue['what_this_issue_cannot_explain']}")
        L.append("")

    L.append("## Root causes")
    L.append("")
    rows = []
    for c in cat.section("root_causes"):
        rows.append(
            [
                c["cause_id"],
                c["title"],
                c["workflow_stage"],
                c["cell_recovery_relationship"]["relationship"],
                c["recoverability"],
                ", ".join(c.get("produces_issues", [])),
            ]
        )
    L.append(_table(["cause_id", "title", "stage", "cell-recovery", "recoverability", "produces"], rows))
    L.append("")

    L.append("## Root-cause matrix (issue x candidate cause)")
    L.append("")
    causes = [c["cause_id"] for c in cat.section("root_causes")]
    issues = cat.section("issues")
    header = ["issue \\ cause"] + [c.split(".", 1)[-1] for c in causes]
    rows = []
    for issue in issues:
        cand = set(issue.get("candidate_root_causes", []))
        rows.append([issue["issue_id"]] + ["x" if c in cand else "" for c in causes])
    L.append(_table(header, rows))
    L.append("")

    L.append("## Diagnostic tests")
    L.append("")
    rows = []
    for t in cat.section("diagnostic_tests"):
        rows.append([t["test_id"], t["title"], t["status"], ", ".join(t.get("supports_causes", []))])
    L.append(_table(["test_id", "title", "status", "supports"], rows))
    L.append("")

    L.append("## Recovery classes")
    L.append("")
    rows = [[a["recovery_class"], a["label"], a["description"]] for a in cat.section("recovery_actions")]
    L.append(_table(["recovery_class", "label", "description"], rows))
    L.append("")

    L.append("## Evidence-scope coverage (metrics by required scope)")
    L.append("")
    scopes: dict[str, list[str]] = {}
    for m in cat.section("metrics"):
        for s in m["required_scopes"]:
            scopes.setdefault(s, []).append(m["metric_id"])
    rows = [[s, str(len(scopes[s])), ", ".join(scopes[s])] for s in sorted(scopes)]
    L.append(_table(["scope", "metrics", "metric ids"], rows))
    L.append("")

    L.append("## References")
    L.append("")
    rows = []
    for r in cat.section("references"):
        rows.append([r["reference_id"], r["title"], r["source"], r["evidence_strength"], r.get("url", "")])
    L.append(_table(["reference_id", "title", "source", "evidence", "url"], rows))
    L.append("")

    return "\n".join(L)


def metric_glossary_md(cat: Catalog) -> str:
    L: list[str] = []
    L.append("# Canonical metric glossary")
    L.append("")
    L.append(
        "> Generated from `qc/catalog/diagnostic_catalog.yaml` by `python -m qc.catalog render`. "
        "Do not edit by hand."
    )
    L.append("")
    rows = []
    for m in cat.section("metrics"):
        aliases = "; ".join(a["label"] for a in m.get("aliases", []))
        rows.append(
            [
                m["metric_id"],
                m["label"],
                m["domain"],
                m["unit"],
                m["direction"],
                m["scoreability"],
                m.get("denominator", ""),
                aliases,
            ]
        )
    L.append(
        _table(
            ["metric_id", "label", "domain", "unit", "direction", "scoreability", "denominator", "source aliases"],
            rows,
        )
    )
    L.append("")
    return "\n".join(L)


def _ends_nl(text: str) -> str:
    return text if text.endswith("\n") else text + "\n"


def render_artifacts(cat: Catalog | None = None) -> dict[str, str]:
    """Return {relpath: content} for every generated artifact (does not write)."""
    c = cat if cat is not None else load_catalog()
    return {
        "spec/diagnostics/catalog.json": catalog_json(c),
        "docs/qc/diagnostics.md": _ends_nl(diagnostics_md(c)),
        "docs/qc/metric-glossary.md": _ends_nl(metric_glossary_md(c)),
    }


def write_artifacts(cat: Catalog | None = None, *, root: Path | None = None) -> list[str]:
    """Write all artifacts under ``root`` (default: repo root). Returns the written relpaths."""
    base = root if root is not None else REPO_ROOT
    written = []
    for rel, content in render_artifacts(cat).items():
        dst = base / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content)
        written.append(rel)
    return written
