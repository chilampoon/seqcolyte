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
    "10x_3p_v3": {
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


def cmd_wiki(args: argparse.Namespace) -> int:
    """Extract one technology's wiki spec from ALL its documents + cross-check the curated ground truth."""
    from extract.doc_gather import get_technology
    from extract.doc_extract import assemble_generic_spec, extract_documents
    from extract.cross_check import cross_check_against_groundtruth

    tech = get_technology(args.tech)
    protocol_name = args.tech.replace("_", " ")
    source_docs = [{"doc_id": d.name, "title": d.title or d.name,
                    "url": (f"https://doi.org/{d.doi}" if d.doi else None),
                    "path": str(d.path), "retrieved_date": None} for d in tech.docs]
    reference = {"kind": "paper" if tech.doi else "protocol_doc", "label": tech.title or protocol_name,
                 "path": None, "url": tech.landing_url, "doi": tech.doi}

    print(f"[wiki] {args.tech}: {len(tech.docs)} docs → extracting via {args.model} …", file=sys.stderr)
    result = extract_documents(tech.doc_paths, protocol_name, model=args.model, char_budget=args.char_budget)
    extraction = result["extraction"]
    trunc = [d["name"] for d in result.get("text_log", []) if d.get("truncated")]
    print(f"[wiki] extracted {len(extraction.get('oligos', []))} oligos "
          f"({result['source_chars']} chars, {result.get('duration_ms', 0)/1000:.0f}s, "
          f"${result.get('cost_usd') or 0:.3f}){'; truncated: ' + ', '.join(trunc) if trunc else ''}",
          file=sys.stderr)

    spec = assemble_generic_spec(extraction, spec_id=args.tech,
                                 assay=(extraction.get("title") or protocol_name),
                                 chemistry_version=extraction.get("chemistry_version") or "",
                                 source_docs=source_docs, reference=reference, model=args.model)
    out = Path(args.out) if args.out else _REPO / "spec" / "technologies" / f"{args.tech}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(to_canonical_json(spec))

    cc = cross_check_against_groundtruth(extraction, tech.groundtruth_dir)
    (out.parent / f"{args.tech}.crosscheck.json").write_text(json.dumps(
        {"folder": args.tech, "title": spec.get("title"), "split": tech.split,
         "crosscheck": cc, "text_log": result.get("text_log")}, indent=2) + "\n")
    print(f"[wiki] wrote {out} ({len(spec['oligos'])} oligos, platform={spec['platform']}) | "
          f"cross-check recall={cc.get('oligo_seq_recall')} big_conflict={cc.get('big_conflict')}")
    return 0


def cmd_enrich(args: argparse.Namespace) -> int:
    """Enrich an existing wiki spec with modality / method_type / data_processing (+ aligned lib-seq)."""
    from extract.doc_gather import get_technology
    from extract.doc_extract import enrich_extraction, merge_enrichment

    spec_path = _REPO / "spec" / "technologies" / f"{args.tech}.json"
    if not spec_path.exists():
        print(f"ERROR: no spec at {spec_path} — run `extract wiki --tech {args.tech}` first", file=sys.stderr)
        return 1
    spec = json.loads(spec_path.read_text())
    tech = get_technology(args.tech)
    # primary sources only (paper/protocol) — modality + data-processing live there, not the oligo tables
    primary_kinds = ("foundational_paper", "paper", "protocol_article", "author_protocol",
                     "vendor_protocol", "protocol", "technical_note")
    docs = [d.path for d in tech.docs if d.kind in primary_kinds] or tech.doc_paths

    print(f"[enrich] {args.tech}: {len(docs)} primary docs → {args.model} …", file=sys.stderr)
    res = enrich_extraction(spec, docs, args.tech.replace("_", " "), model=args.model)
    spec = merge_enrichment(spec, res["extraction"])
    spec_path.write_bytes(to_canonical_json(spec))
    print(f"[enrich] {args.tech}: modality={spec.get('modality')!r} method={spec.get('method_type')!r} "
          f"data_processing={'yes' if spec.get('data_processing') else 'no'} "
          f"(${res.get('cost_usd') or 0:.2f})")
    return 0


def cmd_dag(args: argparse.Namespace) -> int:
    """Convert a wiki spec's flat data_processing into a proper DAG (stages/nodes/edges)."""
    from extract.doc_extract import graphify_data_processing
    from seqcolyte.spec.loader import validate_spec

    spec_path = _REPO / "spec" / "technologies" / f"{args.tech}.json"
    if not spec_path.exists():
        print(f"ERROR: no spec at {spec_path}", file=sys.stderr)
        return 1
    spec = json.loads(spec_path.read_text())
    res = graphify_data_processing(spec, model=args.model)
    g = res["extraction"]
    dp = spec.get("data_processing") or {}
    spec["data_processing"] = {
        "summary": dp.get("summary"),
        "stages": g.get("stages", []), "nodes": g.get("nodes", []), "edges": g.get("edges", []),
        "statistical_model": g.get("statistical_model") or dp.get("statistical_model"),
    }
    validate_spec(spec)
    spec_path.write_bytes(to_canonical_json(spec))
    print(f"[dag] {args.tech}: {len(g.get('nodes', []))} nodes, {len(g.get('edges', []))} edges, "
          f"{len(g.get('stages', []))} stages (${res.get('cost_usd') or 0:.2f})")
    return 0


def cmd_wiki_index(args: argparse.Namespace) -> int:
    """Rebuild spec/technologies/index.json + CONFLICTS.md, re-running each cross-check from the written
    spec against its ground truth so the conflict flags always reflect the current thresholds."""
    from extract.cross_check import cross_check_against_groundtruth, render_report
    from extract.doc_gather import protocols_root

    tdir = _REPO / "spec" / "technologies"
    index, records = [], []
    for f in sorted(tdir.glob("*.json")):
        if f.name == "index.json" or f.name.endswith(".crosscheck.json"):
            continue
        spec = json.loads(f.read_text())
        # the spec itself acts as the extraction (it carries oligos + the annotated library)
        cc = cross_check_against_groundtruth(spec, protocols_root() / "protocols" / spec["spec_id"])
        (tdir / f"{f.stem}.crosscheck.json").write_text(json.dumps(
            {"folder": spec["spec_id"], "title": spec.get("title"), "crosscheck": cc}, indent=2) + "\n")
        index.append({"id": spec["spec_id"], "title": spec.get("title") or spec.get("assay"),
                      "platform": spec.get("platform"), "chemistry_version": spec.get("chemistry_version"),
                      "modality": spec.get("modality"), "method_type": spec.get("method_type"),
                      "description": spec.get("description"), "big_conflict": cc.get("big_conflict", False),
                      "oligo_seq_recall": cc.get("oligo_seq_recall")})
        records.append({"folder": spec["spec_id"], "title": spec.get("title"), "crosscheck": cc})
    index.sort(key=lambda x: (x["title"] or x["id"]).lower())
    (tdir / "index.json").write_text(json.dumps(index, indent=2) + "\n")
    (tdir / "CONFLICTS.md").write_text(render_report(records))
    n_flag = sum(1 for x in index if x["big_conflict"])
    print(f"wrote {tdir/'index.json'} ({len(index)} technologies, {n_flag} big conflicts) + CONFLICTS.md")
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

    wk = sub.add_parser("wiki", help=cmd_wiki.__doc__)
    wk.add_argument("--tech", required=True, help="protocol folder name (e.g. drop_seq)")
    wk.add_argument("--model", default="claude-opus-4-8", help="Claude model (default: %(default)s)")
    wk.add_argument("--out", default=None, help="output path (default: spec/technologies/<tech>.json)")
    wk.add_argument("--char-budget", type=int, default=1_800_000, dest="char_budget",
                    help="max total document chars fed to the model (default: %(default)s)")
    wk.set_defaults(func=cmd_wiki)

    en = sub.add_parser("enrich", help=cmd_enrich.__doc__)
    en.add_argument("--tech", required=True, help="protocol folder name (must already have a wiki spec)")
    en.add_argument("--model", default="claude-opus-4-8", help="Claude model (default: %(default)s)")
    en.set_defaults(func=cmd_enrich)

    dg = sub.add_parser("dag", help=cmd_dag.__doc__)
    dg.add_argument("--tech", required=True, help="protocol folder name (must already have a wiki spec)")
    dg.add_argument("--model", default="claude-opus-4-8", help="Claude model (default: %(default)s)")
    dg.set_defaults(func=cmd_dag)

    wi = sub.add_parser("wiki-index", help=cmd_wiki_index.__doc__)
    wi.set_defaults(func=cmd_wiki_index)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
