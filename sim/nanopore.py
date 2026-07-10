"""Single-cell Nanopore long-read simulator, built from a real wf-single-cell BAM.

Each simulated read is a raw (un-trimmed) full-length molecule:

    R1 handle + [cell barcode:16] + [UMI:12] + cDNA + poly(A) + TSO

The **healthy** set is one clean molecule per read (a single terminal TSO). The **problematic**
set injects TSO **concatemers** — the hallmark long-read scRNA-seq artifact where template
switching chains cDNAs through tandem TSO sequences, leaving *internal* TSO copies:

    R1 handle + [CB] + [UMI] + cDNA1 + TSO + revcomp(TSO) + cDNA2 + poly(A) + TSO   (3 TSO hits)

Ground-truth labels are written per read so the QC can score itself. The intended diagnosis for a
high concatemer fraction is TSO-concatemer removal / enrichment (e.g. biotin pull-down; see the
Cell Stem Cell biotinylated-TSO mitigation).

Usage:
    python -m sim.nanopore --bam data/raw/MDS02.50k.bam --out data/sim --n 40000
"""

from __future__ import annotations

import argparse
import gzip
import os
import random

import pysam

R1_HANDLE = "CTACACGACGCTCTTCCGATCT"  # partial TruSeq Read 1
TSO = "AAGCAGTGGTATCAACGCAGAGTACATGGG"  # 10x template-switching oligo
_COMP = str.maketrans("ACGTN", "TGCAN")


def revcomp(s: str) -> str:
    return s.translate(_COMP)[::-1]


def _ham(a: str, b: str) -> int:
    return sum(x != y for x, y in zip(a, b))


def _strip_leading_tso(seq: str, k: int = 6) -> str:
    """Some BAM cDNAs retain the 5' TSO; drop it so we control the TSO count exactly."""
    return seq[len(TSO):] if len(seq) > len(TSO) and _ham(seq[: len(TSO)], TSO) <= k else seq


def _noise(seq: str, rate: float, rng: random.Random) -> str:
    if rate <= 0:
        return seq
    return "".join(rng.choice("ACGT") if rng.random() < rate else c for c in seq)


def load_reads(bam_path: str, limit: int) -> list[tuple[str, str, str]]:
    """Return (cell_barcode, umi, cDNA) triples from primary, barcoded reads."""
    out: list[tuple[str, str, str]] = []
    bam = pysam.AlignmentFile(bam_path, "rb", check_sq=False)
    for r in bam:
        if r.is_secondary or r.is_supplementary:
            continue
        seq = r.query_sequence
        if not seq or not r.has_tag("CB") or not r.has_tag("UB"):
            continue
        cb, umi = str(r.get_tag("CB")), str(r.get_tag("UB"))
        if len(cb) != 16 or len(umi) != 12:
            continue
        cdna = _strip_leading_tso(seq)
        if not (150 <= len(cdna) <= 4000):
            continue
        out.append((cb, umi, cdna))
        if len(out) >= limit:
            break
    return out


def _phred(n: int, q: int = 25) -> str:
    return chr(q + 33) * n


def _build_healthy(cb, umi, cdna, rng, noise):
    polya = "A" * rng.randint(15, 28)
    return _noise(R1_HANDLE + cb + umi + cdna + polya + TSO, noise, rng), 1


def _build_concatemer(cb, umi, cdna, cdna2, rng, noise):
    polya = "A" * rng.randint(15, 28)
    half = len(cdna) // 2
    read = R1_HANDLE + cb + umi + cdna[:half] + TSO + revcomp(TSO) + cdna2 + polya + TSO
    return _noise(read, noise, rng), 3


def simulate(bam, out_dir, n, conc_frac, noise, seed, name):
    rng = random.Random(seed)
    reads = load_reads(bam, 200_000)
    if not reads:
        raise SystemExit(f"no usable reads in {bam}")
    rng.shuffle(reads)
    os.makedirs(out_dir, exist_ok=True)
    n_conc = 0
    with gzip.open(os.path.join(out_dir, "reads.fastq.gz"), "wt") as fq, open(
        os.path.join(out_dir, "labels.tsv"), "w"
    ) as lab:
        lab.write("read_id\tlabel\tfailure_mode\taffected\tn_tso\tcb\tumi\tcdna_len\n")
        for i in range(n):
            cb, umi, cdna = reads[i % len(reads)]
            if rng.random() < conc_frac:
                cdna2 = reads[(i + 7) % len(reads)][2]
                cdna2 = cdna2[: rng.randint(150, min(800, len(cdna2)))]
                read, ntso = _build_concatemer(cb, umi, cdna, cdna2, rng, noise)
                label, mode, aff = "concatemer", "tso_concatemer", 1
                n_conc += 1
            else:
                read, ntso = _build_healthy(cb, umi, cdna, rng, noise)
                label, mode, aff = "clean", "none", 0
            rid = f"{name}_{i:06d}"
            fq.write(f"@{rid}\n{read}\n+\n{_phred(len(read))}\n")
            lab.write(f"{rid}\t{label}\t{mode}\t{aff}\t{ntso}\t{cb}\t{umi}\t{len(cdna)}\n")
    return n, n_conc


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bam", required=True, help="wf-single-cell BAM with CB/UB tags")
    ap.add_argument("--out", required=True, help="output base dir")
    ap.add_argument("--n", type=int, default=40_000, help="reads per dataset")
    ap.add_argument("--concatemer-frac", type=float, default=0.30, help="concatemer fraction (problematic)")
    ap.add_argument("--healthy-frac", type=float, default=0.01, help="natural concatemer rate (healthy)")
    ap.add_argument("--noise", type=float, default=0.02, help="per-base substitution rate (ONT-like)")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    for sub, frac, nm in [
        ("nanopore_healthy", a.healthy_frac, "nano_healthy"),
        ("nanopore_tso_concatemer", a.concatemer_frac, "nano_conc"),
    ]:
        tot, conc = simulate(a.bam, os.path.join(a.out, sub), a.n, frac, a.noise, a.seed, nm)
        print(f"{sub}: {tot} reads, {conc} concatemers ({100 * conc / tot:.1f}%)")


if __name__ == "__main__":
    main()
