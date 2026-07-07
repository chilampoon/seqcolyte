"""``python -m extract build|check`` — build the spec from the HTML, or verify no drift."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from extract.builder import DEFAULT_HTML, SPEC_ID, build_spec, to_canonical_json

_REPO = Path(__file__).resolve().parents[1]


def _out_path(spec: str, out: str | None) -> Path:
    return Path(out) if out else _REPO / "spec" / f"{spec}.json"


def cmd_build(args: argparse.Namespace) -> int:
    spec = build_spec(args.html)
    data = to_canonical_json(spec)
    out = _out_path(args.spec, args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print(f"wrote {out} ({len(data)} bytes, {len(spec['oligos'])} oligos, "
          f"sha256={spec['build']['source_html_sha256'][:12]}…)")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    data = to_canonical_json(build_spec(args.html))
    out = _out_path(args.spec, args.out)
    if not out.exists():
        print(f"ERROR: {out} does not exist — run `python -m extract build` first", file=sys.stderr)
        return 1
    if out.read_bytes() != data:
        print(f"DRIFT: {out} differs from a fresh build — run `python -m extract build`", file=sys.stderr)
        return 1
    print(f"OK: {out} matches a fresh build")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="extract", description="Build/check the Seqcolyte read-structure spec")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, fn in (("build", cmd_build), ("check", cmd_check)):
        sp = sub.add_parser(name, help=fn.__doc__)
        sp.add_argument("--spec", default=SPEC_ID, help="spec id (default: %(default)s)")
        sp.add_argument("--html", default=str(DEFAULT_HTML), help="source protocol HTML")
        sp.add_argument("--out", default=None, help="output path (default: spec/<spec>.json)")
        sp.set_defaults(func=fn)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
