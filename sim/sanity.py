"""Clean-control sanity checks: proves the subsampled control is actually a clean 10x 3' v3
library before we derive failures from it.

  - R1 length == 28 (16 bp cell barcode + 12 bp UMI) across the subset
  - R2 modal length recorded
  - cell-barcode whitelist hit-rate >= threshold (correct chemistry + R1 orientation)
  - equal R1/R2 counts (pairing)
"""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

from seqcolyte.io.fastx import read_fastx
from seqcolyte.spec.loader import load_spec

__all__ = ["load_whitelist", "r1_length_stats", "whitelist_hit_rate", "run_sanity"]


def load_whitelist(path: str | Path) -> set[bytes]:
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as fh:  # type: ignore[operator]
        return {line.strip().encode("ascii") for line in fh if line.strip()}


def r1_length_stats(r1_path: str) -> dict:
    lengths_min = lengths_max = None
    n = 0
    for rec in read_fastx(r1_path):
        L = len(rec.sequence)
        lengths_min = L if lengths_min is None else min(lengths_min, L)
        lengths_max = L if lengths_max is None else max(lengths_max, L)
        n += 1
    return {"n": n, "min": lengths_min, "max": lengths_max}


def whitelist_hit_rate(r1_path: str, whitelist: set[bytes], cb_len: int) -> tuple[float, int, int]:
    hits = total = 0
    for rec in read_fastx(r1_path):
        cb = rec.sequence[:cb_len].encode("ascii")
        total += 1
        if cb in whitelist:
            hits += 1
    return (hits / total if total else 0.0), hits, total


def run_sanity(r1_path: str, r2_path: str, whitelist_path: str, spec_path: str,
               *, min_hit_rate: float = 0.85) -> dict:
    spec = load_spec(spec_path)
    expected_r1 = spec.platform_params["read_lengths"]["R1"]
    cb_len = spec.segment_offsets("R1")["cell_barcode"][1]

    r1 = r1_length_stats(r1_path)
    r2 = r1_length_stats(r2_path)
    print(f"[sanity] R1 length: min={r1['min']} max={r1['max']} n={r1['n']} (expected {expected_r1})")
    print(f"[sanity] R2 length: min={r2['min']} max={r2['max']} n={r2['n']}")

    print(f"[sanity] loading whitelist {whitelist_path} …")
    whitelist = load_whitelist(whitelist_path)
    rate, hits, total = whitelist_hit_rate(r1_path, whitelist, cb_len)
    print(f"[sanity] whitelist hit-rate: {rate:.4f} ({hits}/{total}, {len(whitelist)} barcodes)")

    checks = {
        "r1_length_28": r1["min"] == r1["max"] == expected_r1,
        "pairing_equal_counts": r1["n"] == r2["n"],
        "whitelist_hit_rate_ok": rate >= min_hit_rate,
    }
    result = {
        "r1": r1, "r2": r2,
        "whitelist_hit_rate": round(rate, 4), "whitelist_hits": hits, "whitelist_total": total,
        "whitelist_size": len(whitelist), "min_hit_rate": min_hit_rate,
        "checks": checks, "passed": all(checks.values()),
    }
    for name, ok in checks.items():
        print(f"[sanity] {'PASS' if ok else 'FAIL'}  {name}")
    return result


def main(argv: list[str] | None = None) -> int:
    _repo = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(prog="sanity", description="Clean-control sanity checks")
    ap.add_argument("--r1", default=str(_repo / "data/raw/pbmc_1k_v3_sub_R1.fastq.gz"))
    ap.add_argument("--r2", default=str(_repo / "data/raw/pbmc_1k_v3_sub_R2.fastq.gz"))
    ap.add_argument("--whitelist", default=str(_repo / "whitelists/3M-february-2018.txt.gz"))
    ap.add_argument("--spec", default=str(_repo / "spec/10x_3p_v3.json"))
    ap.add_argument("--min-hit-rate", type=float, default=0.85, dest="min_hit_rate")
    ap.add_argument("--json-out", default=None, dest="json_out")
    args = ap.parse_args(argv)
    result = run_sanity(args.r1, args.r2, args.whitelist, args.spec, min_hit_rate=args.min_hit_rate)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=2) + "\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
