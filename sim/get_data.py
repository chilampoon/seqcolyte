"""Acquire the known-good control: subsample the 10x pbmc_1k_v3 FASTQs to ~40k read pairs,
and download the 3M-february-2018 cell-barcode whitelist (with a computed md5).

Deterministic subsample: the same seeded ``seqkit sample`` mask is applied to R1 and R2 (they
share record order), so pairs stay locked; ``seqkit head`` trims to an exact count.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tarfile
from pathlib import Path

from seqcolyte.io.external import require_tool, tool_version

_REPO = Path(__file__).resolve().parents[1]
TARBALL_URL = "https://cf.10xgenomics.com/samples/cell-exp/3.0.0/pbmc_1k_v3/pbmc_1k_v3_fastqs.tar"
TARBALL_SIZE = 5_549_312_000
WHITELIST_URL = "https://raw.githubusercontent.com/f0t1h/3M-february-2018/master/3M-february-2018.txt.gz"
WHITELIST_SIZE = 18_350_152
WHITELIST_COUNT = 6_794_880


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, **kw)


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_tarball(tarball: Path, *, url: str = TARBALL_URL, expected_size: int = TARBALL_SIZE) -> None:
    if not tarball.exists():
        print(f"[get_data] downloading {url} -> {tarball}")
        tarball.parent.mkdir(parents=True, exist_ok=True)
        _run(["wget", "-c", "-q", "-O", str(tarball), url])
    size = tarball.stat().st_size
    if size != expected_size:
        raise RuntimeError(f"tarball size {size} != expected {expected_size}; re-download")
    print(f"[get_data] tarball OK ({size} bytes)")


def _concat_members(tarball: Path, members: list[str], out: Path) -> None:
    with open(out, "wb") as fh:
        for m in members:
            _run(["tar", "-xOf", str(tarball), m], stdout=fh)


def extract_reads(tarball: Path, workdir: Path) -> tuple[Path, Path]:
    """Concatenate the per-lane R1s and R2s (in lane order) into two gzipped FASTQs."""
    with tarfile.open(tarball) as tf:
        names = tf.getnames()
    r1 = sorted(n for n in names if "_R1_" in n)
    r2 = sorted(n for n in names if "_R2_" in n)
    if not r1 or not r2:
        raise RuntimeError(f"no R1/R2 members found in {tarball}")
    full_r1, full_r2 = workdir / "full_R1.fastq.gz", workdir / "full_R2.fastq.gz"
    print(f"[get_data] concatenating {len(r1)} R1 + {len(r2)} R2 lane files")
    _concat_members(tarball, r1, full_r1)
    _concat_members(tarball, r2, full_r2)
    return full_r1, full_r2


def _num_seqs(seqkit: str, path: Path) -> int:
    out = _run([seqkit, "stats", "-T", str(path)], capture_output=True, text=True).stdout
    header, row = out.splitlines()[0].split("\t"), out.splitlines()[1].split("\t")
    return int(row[header.index("num_seqs")].replace(",", ""))


def _subsample_one(seqkit: str, src: Path, dst: Path, prop: float, n: int, seed: int) -> None:
    # Two steps (no pipe): order-preserving Bernoulli sample with a fixed seed, then trim to
    # exactly n. Same seed + same record order on R1 and R2 keeps pairs locked. A pipe would
    # SIGPIPE `seqkit sample` when `seqkit head` closes early, so materialize a temp file.
    tmp = dst.with_suffix(dst.suffix + ".sampled.tmp.gz")
    try:
        _run([seqkit, "sample", "-s", str(seed), "-p", f"{prop:.8f}", str(src), "-o", str(tmp)])
        _run([seqkit, "head", "-n", str(n), str(tmp), "-o", str(dst)])
    finally:
        tmp.unlink(missing_ok=True)


def subsample(full_r1: Path, full_r2: Path, out_r1: Path, out_r2: Path, *, n: int, seed: int) -> int:
    seqkit = require_tool("seqkit")
    total = _num_seqs(seqkit, full_r1)
    prop = min(1.0, (n * 2.0) / total) if total else 1.0
    print(f"[get_data] {total} pairs total; sampling p={prop:.6f} then head -n {n} (seed={seed})")
    out_r1.parent.mkdir(parents=True, exist_ok=True)
    _subsample_one(seqkit, full_r1, out_r1, prop, n, seed)
    _subsample_one(seqkit, full_r2, out_r2, prop, n, seed)
    kept = _num_seqs(seqkit, out_r1)
    kept2 = _num_seqs(seqkit, out_r2)
    if kept != kept2:
        raise RuntimeError(f"R1/R2 subsample counts differ: {kept} != {kept2}")
    print(f"[get_data] wrote {kept} pairs -> {out_r1}, {out_r2}")
    return kept


def cmd_data(args: argparse.Namespace) -> int:
    tarball = Path(args.tarball)
    ensure_tarball(tarball, url=args.url, expected_size=args.expected_size)
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    full_r1, full_r2 = extract_reads(tarball, workdir)
    try:
        subsample(full_r1, full_r2, Path(args.out_r1), Path(args.out_r2), n=args.n, seed=args.seed)
    finally:
        for f in (full_r1, full_r2):
            f.unlink(missing_ok=True)
    if not args.keep_tarball:
        tarball.unlink(missing_ok=True)
        print(f"[get_data] removed {tarball}")
    return 0


def cmd_whitelist(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        print(f"[get_data] downloading whitelist -> {out}")
        _run(["wget", "-c", "-q", "-O", str(out), args.url])
    size = out.stat().st_size
    if size != WHITELIST_SIZE:
        raise RuntimeError(f"whitelist size {size} != expected {WHITELIST_SIZE}")
    md5 = _md5(out)
    provenance = {
        "name": "3M-february-2018",
        "path": str(out.relative_to(_REPO)) if out.is_absolute() else str(out),
        "source_url": args.url,
        "size_bytes_gz": size,
        "count": WHITELIST_COUNT,
        "md5": md5,
        "md5_provenance": "computed_local_no_official_checksum",
        "retrieved_date": args.date,
        "tool_versions": {"seqkit": tool_version("seqkit")},
    }
    Path(args.provenance_out).write_text(json.dumps(provenance, indent=2) + "\n")
    print(f"[get_data] whitelist OK ({size} bytes, md5={md5}) — provenance -> {args.provenance_out}")
    print("[get_data] note: no official 10x checksum exists; md5 recorded in the sidecar, not the committed spec")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="get_data", description="Acquire the pbmc_1k_v3 control + whitelist")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("data", help="download + subsample pbmc_1k_v3 to ~N pairs")
    d.add_argument("--tarball", default=str(_REPO / "data/raw/pbmc_1k_v3_fastqs.tar"))
    d.add_argument("--url", default=TARBALL_URL)
    d.add_argument("--expected-size", type=int, default=TARBALL_SIZE, dest="expected_size")
    d.add_argument("--workdir", default=str(_REPO / "data/raw"))
    d.add_argument("--out-r1", default=str(_REPO / "data/raw/pbmc_1k_v3_sub_R1.fastq.gz"), dest="out_r1")
    d.add_argument("--out-r2", default=str(_REPO / "data/raw/pbmc_1k_v3_sub_R2.fastq.gz"), dest="out_r2")
    d.add_argument("--n", type=int, default=40000)
    d.add_argument("--seed", type=int, default=100)
    d.add_argument("--keep-tarball", action="store_true", dest="keep_tarball")
    d.set_defaults(func=cmd_data)

    w = sub.add_parser("whitelist", help="download 3M-february-2018 whitelist + compute md5")
    w.add_argument("--url", default=WHITELIST_URL)
    w.add_argument("--out", default=str(_REPO / "whitelists/3M-february-2018.txt.gz"))
    w.add_argument("--provenance-out", default=str(_REPO / "whitelists/3M-february-2018.provenance.json"),
                   dest="provenance_out")
    w.add_argument("--date", default="2026-07-07")
    w.set_defaults(func=cmd_whitelist)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
