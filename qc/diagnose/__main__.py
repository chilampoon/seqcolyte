"""CLI: ``python -m qc.diagnose run --evidence <report> [--manifest m.yaml] [--qc qc.json] [--explain]``
and ``python -m qc.diagnose render-examples [--check]``. The deterministic path needs no network/LLM."""

from __future__ import annotations

import argparse
import json
import sys

from qc.diagnose.engine import diagnose_from_reports
from qc.diagnose.examples import render_examples, write_examples, EXAMPLES_DIR


def _print_report(dx) -> None:
    print(f"# Diagnosis (profile {dx.profile_version})")
    if dx.title:
        print(f"# {dx.title}")
    if dx.summary:
        print(dx.summary)
    print("\nFiring signals:")
    for s in dx.fired_signals or ["  (none)"]:
        print(f"  - {s.label}  [{s.magnitude:g}]" if hasattr(s, "label") else f"  {s}")
    print("\nRanked hypotheses (most likely first):")
    for i, h in enumerate(dx.hypotheses, 1):
        print(f"  {i}. {h.title}  score={h.score:g}  cell-recovery={h.cell_recovery_relationship}  "
              f"[{h.recoverability}]")
        if h.narrative:
            print(f"       {h.narrative}")
    if not dx.hypotheses:
        print("  (no candidate causes — insufficient firing signals)")
    if dx.warnings:
        print("\nWarnings:")
        for w in dx.warnings:
            print(f"  ! {w}")
    if dx.missing_evidence:
        print("\nMissing evidence (metrics not supplied): " + ", ".join(dx.missing_evidence))


def _run(args: argparse.Namespace) -> int:
    from qc.evidence.registry import import_report
    from qc.manifest.loader import load_manifest

    reports = [import_report(p) for p in (args.evidence or [])]
    manifest = load_manifest(args.manifest) if args.manifest else None
    qc_findings = None
    if args.qc:
        qc_findings = json.loads(open(args.qc).read()).get("findings")

    dx = diagnose_from_reports(reports, manifest=manifest, qc_findings=qc_findings, title=args.title)
    if args.explain:
        from qc.diagnose.explain import explain

        dx = explain(dx, model=args.model)

    if args.json_out:
        with open(args.json_out, "w") as fh:
            fh.write(json.dumps(dx.to_dict(), indent=2) + "\n")
        print(f"wrote {args.json_out}")
    _print_report(dx)
    return 0


def _render_examples(args: argparse.Namespace) -> int:
    if args.check:
        stale = []
        for rel, content in render_examples().items():
            dst = EXAMPLES_DIR / rel
            if (dst.read_text() if dst.exists() else None) != content:
                stale.append(rel)
        if stale:
            print("stale example diagnoses (run `python -m qc.diagnose render-examples`):", file=sys.stderr)
            for rel in stale:
                print(f"  - {rel}", file=sys.stderr)
            return 1
        print("example diagnoses are up to date")
        return 0
    written = write_examples()
    print("wrote " + ", ".join(written))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qc.diagnose", description="Deterministic diagnosis + ranking")
    sub = parser.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="diagnose from imported evidence + a typed cell target")
    r.add_argument("--evidence", action="append", help="QC evidence report (HTML); repeatable")
    r.add_argument("--manifest", help="input manifest (.yaml/.json) with a typed cell_target")
    r.add_argument("--qc", help="an existing qc_report.json to fold in via check adapters")
    r.add_argument("--title", default=None)
    r.add_argument("--json-out", dest="json_out", default=None)
    r.add_argument("--explain", action="store_true", help="add an LLM narrative (needs the claude CLI)")
    r.add_argument("--model", default="claude-opus-4-8")
    r.set_defaults(func=_run)

    e = sub.add_parser("render-examples", help="render the committed worked-example diagnoses")
    e.add_argument("--check", action="store_true", help="verify checked-in examples are up to date")
    e.set_defaults(func=_render_examples)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
