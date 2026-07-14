#!/usr/bin/env python3
"""
Remediate check_id tso_at_r2_start for a 10x 3' v3 library.

QC finding: "32.6% of R2 start with the TSO".

10x GEX libraries orient the cDNA insert on R2 (16nt CB + 12nt UMI live on R1).
The Template Switch Oligo (TSO) handle can remain at the 5' start of R2 when the
molecule is short / read-through, contaminating the insert. Cell Ranger's GEX
algorithm trims TSO at the 5' end of R2 (and poly-A at the 3'); here we do the
5' TSO trim only, exactly as the finding calls for.

THE FIX (only this):
  - Trim the leading TSO handle from the 5' start of R2 when present (<=1 mismatch).
  - Leave R1 and adapter-free reads unchanged.
  - Drop a pair if either mate is < 20 bp after trimming.
  - Keep R1/R2 paired, emit both mates in lockstep, deterministic, re-runnable.
"""

import gzip
import os
import sys

# 10x Genomics Template Switch Oligo (doc_id 10x_tso / cellranger_gex).
# Canonical handle: AAGCAGTGGTATCAACGCAGAGTA + rGrGrG -> ...TACATGGG
TSO = "AAGCAGTGGTATCAACGCAGAGTACATGGG"
TSO_LEN = len(TSO)
MAX_MISMATCH = 1     # allow 1 mismatch across the TSO window
MIN_LEN = 20         # drop a pair if either mate falls below this after trimming

R1_IN = sys.argv[1] if len(sys.argv) > 1 else "inputs/fastq/R1.fastq.gz"
R2_IN = sys.argv[2] if len(sys.argv) > 2 else "inputs/fastq/R2.fastq.gz"
R1_OUT = sys.argv[3] if len(sys.argv) > 3 else "remediated/R1.fastq.gz"
R2_OUT = sys.argv[4] if len(sys.argv) > 4 else "remediated/R2.fastq.gz"


def read_records(path):
    """Yield (name, seq, plus, qual) FASTQ records from a gzipped file."""
    with gzip.open(path, "rt") as fh:
        while True:
            name = fh.readline()
            if not name:
                return
            seq = fh.readline()
            plus = fh.readline()
            qual = fh.readline()
            if not qual:
                raise ValueError("Truncated FASTQ record in %s" % path)
            yield (name.rstrip("\n"), seq.rstrip("\n"),
                   plus.rstrip("\n"), qual.rstrip("\n"))


def tso_leading_len(seq):
    """Return TSO_LEN if seq starts with the TSO (<=MAX_MISMATCH), else 0."""
    if len(seq) < TSO_LEN:
        return 0
    mism = 0
    for a, b in zip(seq, TSO):  # zip stops at TSO_LEN
        if a != b:
            mism += 1
            if mism > MAX_MISMATCH:
                return 0
    return TSO_LEN


def main():
    for out in (R1_OUT, R2_OUT):
        parent = os.path.dirname(out)
        if parent:
            os.makedirs(parent, exist_ok=True)

    pairs_in = 0
    pairs_out = 0
    trimmed = 0
    dropped = 0

    r1_iter = read_records(R1_IN)
    r2_iter = read_records(R2_IN)

    with gzip.open(R1_OUT, "wt") as o1, gzip.open(R2_OUT, "wt") as o2:
        for r1, r2 in zip(r1_iter, r2_iter):
            pairs_in += 1
            n1, s1, p1, q1 = r1
            n2, s2, p2, q2 = r2

            cut = tso_leading_len(s2)
            if cut:
                s2 = s2[cut:]
                q2 = q2[cut:]
                trimmed += 1

            if len(s1) < MIN_LEN or len(s2) < MIN_LEN:
                dropped += 1
                continue

            o1.write("%s\n%s\n%s\n%s\n" % (n1, s1, p1, q1))
            o2.write("%s\n%s\n%s\n%s\n" % (n2, s2, p2, q2))
            pairs_out += 1

    # Guard against mate-count mismatch (unequal R1/R2 lengths).
    leftover_r1 = sum(1 for _ in r1_iter)
    leftover_r2 = sum(1 for _ in r2_iter)
    extra = ""
    if leftover_r1 or leftover_r2:
        extra = " WARNING: unpaired trailing records (R1=%d, R2=%d) ignored" % (
            leftover_r1, leftover_r2)

    print(
        "tso_at_r2_start: pairs_in=%d pairs_out=%d "
        "r2_tso_trimmed=%d pairs_dropped_short(<%dbp)=%d "
        "(R1 unchanged; adapter-free R2 unchanged)%s"
        % (pairs_in, pairs_out, trimmed, MIN_LEN, dropped, extra)
    )


if __name__ == "__main__":
    main()
