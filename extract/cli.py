"""``python -m extract build|check`` — build the spec from the HTML, or verify no drift."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from extract.builder import DEFAULT_HTML, SPEC_ID, build_spec, to_canonical_json

_REPO = Path(__file__).resolve().parents[1]

# Per-spec metadata used when assembling an LLM-extracted spec.
_WHITELIST_3M = {
    "cell_barcode_3M_feb2018": {
        "name": "3M-february-2018", "path": "whitelists/3M-february-2018.txt.gz", "md5": None,
        "md5_provenance": "computed_local_no_official_checksum",
        "source_url": "https://raw.githubusercontent.com/f0t1h/3M-february-2018/master/3M-february-2018.txt.gz",
        "source_note": "community mirror; no vendor checksum published",
        "size_bytes_gz": 18350152, "count": 6794880, "length": 16, "retrieved_date": None,
    }
}
_SPEC_META = {
    "tenx_3p_v3": {
        "assay": "10x Chromium Single Cell 3' Gene Expression", "chemistry_version": "v3/v3.1",
        "protocol_name": "10x Chromium 3' Gene Expression v3", "whitelist": _WHITELIST_3M,
    },
}


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


def cmd_from_doc(args: argparse.Namespace) -> int:
    """Extract a spec from a protocol PDF via Claude Code headless (LLM extraction)."""
    from extract.doc_extract import assemble_spec, cross_check, evaluate, extract_document

    meta = _SPEC_META.get(args.spec)
    if meta is None:
        print(f"ERROR: no metadata registered for spec {args.spec!r} (known: {list(_SPEC_META)})", file=sys.stderr)
        return 1

    print(f"[from-doc] extracting {args.doc} via Claude Code ({args.model}) …", file=sys.stderr)
    result = extract_document(args.doc, meta["protocol_name"], model=args.model)
    extraction = result["extraction"]
    print(f"[from-doc] extracted {len(extraction['oligos'])} oligos "
          f"(source {result['source_chars']} chars, {result.get('duration_ms', 0)/1000:.0f}s, "
          f"${result.get('cost_usd') or 0:.3f})", file=sys.stderr)

    cc = cross_check(extraction)
    print(f"[from-doc] cross-check vs verified constants: {cc['matched']}/{cc['checked']} matched", file=sys.stderr)

    spec = assemble_spec(extraction, spec_id=args.spec, assay=meta["assay"],
                         chemistry_version=meta["chemistry_version"], source_doc_path=args.doc,
                         model=args.model, whitelist_block=meta["whitelist"])
    out = Path(args.out) if args.out else _REPO / "spec" / f"{args.spec}.pdf.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(to_canonical_json(spec))
    print(f"[from-doc] wrote {out} ({len(spec['oligos'])} oligos, LLM-extracted)")

    if args.eval:
        gt_dir = args.groundtruth_dir or str(Path(args.doc).parent)
        ev = evaluate(extraction, gt_dir)
        print("\n[from-doc] EVAL vs groundtruth:")
        print(f"  oligo sequence recall : {ev['oligo_seqs_matched']}/{ev['oligo_seqs_total']} "
              f"({ev['oligo_seq_recall']})")
        if ev["missed_oligos"]:
            print(f"  missed                : {', '.join(ev['missed_oligos'])}")
        print(f"  annotated library     : {'EXACT MATCH' if ev['annotated_library_exact_match'] else 'DIFFERS'}")
        if not ev["annotated_library_exact_match"]:
            print(f"    got     : {ev['annotated_library_got']}")
            print(f"    expected: {ev['annotated_library_expected']}")
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

    fd = sub.add_parser("from-doc", help=cmd_from_doc.__doc__)
    fd.add_argument("--doc", required=True, help="protocol PDF to extract from")
    fd.add_argument("--spec", default=SPEC_ID, help="spec id (default: %(default)s)")
    fd.add_argument("--model", default="claude-opus-4-8", help="Claude model (default: %(default)s)")
    fd.add_argument("--out", default=None, help="output path (default: spec/<spec>.pdf.json)")
    fd.add_argument("--eval", action="store_true", help="evaluate against groundtruth in the PDF's dir")
    fd.add_argument("--groundtruth-dir", default=None, dest="groundtruth_dir")
    fd.set_defaults(func=cmd_from_doc)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
