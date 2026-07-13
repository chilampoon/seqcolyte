"""CLI for the diagnostic catalog: ``python -m qc.catalog validate|render``. No network, no LLM."""

from __future__ import annotations

import argparse
import sys

from qc.catalog.loader import load_catalog
from qc.catalog.render_docs import render_artifacts, write_artifacts
from qc.catalog.validate import CatalogError, validate_or_raise


def _validate(_args: argparse.Namespace) -> int:
    try:
        validate_or_raise()
    except CatalogError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    cat = load_catalog()
    counts = {name: len(cat.section(name)) for name in
              ("metrics", "signals", "issues", "root_causes", "diagnostic_tests", "recovery_actions", "references")}
    print("catalog OK: " + ", ".join(f"{n}={c}" for n, c in counts.items()))
    return 0


def _render(args: argparse.Namespace) -> int:
    cat = validate_or_raise()  # never render an invalid catalog
    if args.check:
        stale = []
        from qc.catalog.render_docs import REPO_ROOT

        for rel, content in render_artifacts(cat).items():
            dst = REPO_ROOT / rel
            current = dst.read_text() if dst.exists() else None
            if current != content:
                stale.append(rel)
        if stale:
            print("stale generated artifacts (run `python -m qc.catalog render`):", file=sys.stderr)
            for rel in stale:
                print(f"  - {rel}", file=sys.stderr)
            return 1
        print("generated artifacts are up to date")
        return 0
    written = write_artifacts(cat)
    print("wrote " + ", ".join(written))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qc.catalog", description="Diagnostic catalog validate/render")
    sub = parser.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="validate the catalog (schema + cross-references)")
    v.set_defaults(func=_validate)

    r = sub.add_parser("render", help="render catalog.json + docs/qc/*.md from the catalog")
    r.add_argument("--check", action="store_true", help="verify checked-in artifacts are up to date (no write)")
    r.set_defaults(func=_render)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
