"""``python -m qc run --spec <spec.json> --r1 R1.fastq.gz --r2 R2.fastq.gz [...]``"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from qc.engine import run_qc
from qc.rust_engine import RustEngineUnavailable

_ICON = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}


def _print_report(r: dict) -> None:
    bar = "=" * 74
    print(bar)
    print(f"SEQCOLYTE QC — {r['assay']} ({r['platform']})   spec={r['spec_id']}   overall: {r['overall'].upper()}")
    print(bar)
    p = r["profile"]
    print(f"reads: {p['n_pairs']:,} pairs   R1 modal {p['r1_len']['modal']} bp   R2 modal {p['r2_len']['modal']} bp\n")
    print("checks:")
    for f in r["findings"]:
        af = f"   [{f['affected_fraction']:.1%} of reads]" if f["affected_fraction"] is not None else ""
        print(f"  {_ICON.get(f['verdict'], '?'):4}  {f['title']:<52} {f['value']} {f['unit']} (want {f['threshold']}){af}")

    plan = r["plan"]
    print(f"\ndiagnosis ({plan.get('method', '?')}):")
    print(f"  root cause : {plan['root_cause']}")
    print(f"  {plan['diagnosis']}")
    if plan.get("ranked"):
        print("  ranked findings:")
        for x in plan["ranked"]:
            print(f"    - [{x['severity']:>6}] {x['check_id']}: {x['why']}")
    if plan.get("llm_error"):
        print(f"  (LLM ranking unavailable: {plan['llm_error']} — used deterministic fallback)")

    if r.get("eval"):
        e = r["eval"]
        c = e["confusion"]
        print(f"\neval vs ground-truth labels: precision={e['precision']} recall={e['recall']} f1={e['f1']}")
        print(f"  predicted {e['predicted_affected']:,} affected / {e['true_affected']:,} truly affected of {e['n']:,} "
              f"(tp={c['tp']} fp={c['fp']} fn={c['fn']} tn={c['tn']})")
    print(bar)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="qc", description="Protocol-aware sequencing QC")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rp = sub.add_parser("run", help="run QC on a FASTQ pair against a spec")
    rp.add_argument("--spec", required=True)
    rp.add_argument("--r1", required=True)
    rp.add_argument("--r2", required=True)
    rp.add_argument("--whitelist", default=None, help="cell-barcode whitelist (enables the whitelist check)")
    rp.add_argument("--labels", default=None, help="ground-truth labels TSV (enables the eval)")
    rp.add_argument("--no-llm", action="store_true", dest="no_llm", help="skip Claude ranking; deterministic only")
    rp.add_argument("--model", default="claude-opus-4-8")
    rp.add_argument("--max-reads", type=int, default=None, dest="max_reads")
    rp.add_argument("--json-out", default=None, dest="json_out")
    args = ap.parse_args(argv)

    try:
        report = run_qc(args.spec, args.r1, args.r2, whitelist=args.whitelist, labels=args.labels,
                        use_llm=not args.no_llm, model=args.model, max_reads=args.max_reads)
    except RustEngineUnavailable as exc:
        print(f"error: {exc}\nbuild the compute core first:  make rust", file=sys.stderr)
        return 2
    _print_report(report)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
