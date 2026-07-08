"""Print the Day-1 gate summary: the spec, control-vs-failure counts, and label distribution."""

from __future__ import annotations

import json
from pathlib import Path

from seqcolyte.spec.loader import load_spec

_REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    spec = load_spec(_REPO / "spec" / "10x_3p_v3.json")
    bar = "=" * 72
    print(bar)
    print("SEQCOLYTE — Day 1 gate summary")
    print(bar)
    print(f"Spec: {spec.spec_id}  ({spec.assay}, {spec.chemistry_version}, {spec.platform})")
    print(f"  oligos: {len(spec.oligos)}   source_html_sha256: {spec.data['build']['source_html_sha256'][:16]}…")
    for r in spec.reads:
        segs = ", ".join(f"{s['name']}({s.get('length', s.get('length_range'))})" for s in r["segments"])
        chain = "  ->  readthrough_chain: " + "|".join(e["name"] for e in r.get("readthrough_chain", [])) \
            if r.get("readthrough_chain") else ""
        print(f"  {r['read']} [{r['cycles']} cyc]: {segs}{chain}")
    wl = spec.whitelist("cell_barcode_3M_feb2018")
    print(f"  whitelist: {wl['name']} — {wl['count']:,} x {wl['length']} bp")

    sp = _REPO / "data" / "raw" / "sanity.json"
    if sp.exists():
        s = json.loads(sp.read_text())
        print(f"\nControl sanity: R1 len {s['r1']['min']}–{s['r1']['max']} (n={s['r1']['n']:,}), "
              f"whitelist hit-rate {s['whitelist_hit_rate']:.3f}  ->  {'PASS' if s['passed'] else 'FAIL'}")

    mp = _REPO / "data" / "sim" / "adapter_dimer_f30" / "run.json"
    if mp.exists():
        m = json.loads(mp.read_text())
        print(f"\nFailure sim: {m['name']}  (seed={m['seed']}, mode={m['failure_mode']}, {m['n_pairs']:,} pairs)")
        for k in ("clean", "readthrough", "pure_dimer"):
            print(f"  {k:12} {m['label_counts'].get(k, 0):8,}   ({m['label_fractions'].get(k, 0):.1%})")
        print(f"  R1 output byte-identical to control R1: {m['r1_byte_identical']}")
    print(bar)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
