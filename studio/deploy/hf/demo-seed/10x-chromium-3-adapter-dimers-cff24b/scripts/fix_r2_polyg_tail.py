#!/usr/bin/env python3
"""
Seqcolyte remediation: trim 3' poly-G tails from R2 (10x 3' v3, two-color
Illumina chemistry where dark/no-signal base == G, per spec 10x_3p_v3).

QC finding r2_polyg_tail: "9.8% of R2 have a poly-G tail".

Fix (ONLY this):
  - Trim a 3' poly-G tail from R2 when the tail is >=10 G near the 3' end,
    tolerating up to 2 non-G bases (sequencing errors) inside the run.
  - R1 (the 16nt cell barcode + 12nt UMI read) is left completely unchanged.
  - Drop a pair if either mate ends up < 20 bp. Mates stay paired/in lockstep.

Deterministic and safe to re-run (outputs are overwritten).
"""

import gzip
import os
import sys

R1_IN = sys.argv[1] if len(sys.argv) > 1 else "inputs/fastq/R1.fastq.gz"
R2_IN = sys.argv[2] if len(sys.argv) > 2 else "inputs/fastq/R2.fastq.gz"
R1_OUT = sys.argv[3] if len(sys.argv) > 3 else "remediated/R1.fastq.gz"
R2_OUT = sys.argv[4] if len(sys.argv) > 4 else "remediated/R2.fastq.gz"

MIN_LEN = 20          # drop a pair if either mate is shorter than this
MIN_POLYG = 10        # a tail must have at least this many G to be trimmed
MAX_MISMATCH = 2      # tolerate a couple of non-G bases inside the G-run


def polyg_cut(seq):
    """Return the index at which to cut off a 3' poly-G tail.

    Walk inward from the 3' end. Extend the run while it stays G-rich,
    allowing up to MAX_MISMATCH total non-G bases but stopping at two
    consecutive non-G (that is clearly past the G-run, into real cDNA).
    Cut only when the resulting tail is >= MIN_POLYG bases long.
    Returns len(seq) when there is no qualifying tail (no trimming).
    """
    n = len(seq)
    run_g = 0        # G's seen in the tail so far
    mismatch = 0     # non-G's seen in the tail so far
    consec = 0       # consecutive non-G's
    cut = n          # default: no trim
    for j in range(n - 1, -1, -1):
        if seq[j] == "G":
            run_g += 1
            consec = 0
            if run_g >= MIN_POLYG:
                cut = j  # cut here removes seq[j:] (a G-anchored tail)
        else:
            mismatch += 1
            consec += 1
            if mismatch > MAX_MISMATCH or consec >= 2:
                break
    return cut


def fastq_records(path):
    with gzip.open(path, "rt") as fh:
        while True:
            head = fh.readline()
            if not head:
                return
            seq = fh.readline()
            plus = fh.readline()
            qual = fh.readline()
            if not qual:
                return
            yield head.rstrip("\n"), seq.rstrip("\n"), plus.rstrip("\n"), qual.rstrip("\n")


def main():
    for out in (R1_OUT, R2_OUT):
        parent = os.path.dirname(out)
        if parent:
            os.makedirs(parent, exist_ok=True)

    pairs_in = 0
    pairs_out = 0
    r2_trimmed = 0
    pairs_dropped = 0

    r1_iter = fastq_records(R1_IN)
    r2_iter = fastq_records(R2_IN)

    with gzip.open(R1_OUT, "wt") as o1, gzip.open(R2_OUT, "wt") as o2:
        for rec1, rec2 in zip(r1_iter, r2_iter):
            pairs_in += 1
            h1, s1, p1, q1 = rec1
            h2, s2, p2, q2 = rec2

            cut = polyg_cut(s2)
            if cut < len(s2):
                r2_trimmed += 1
                s2 = s2[:cut]
                q2 = q2[:cut]

            if len(s1) < MIN_LEN or len(s2) < MIN_LEN:
                pairs_dropped += 1
                continue

            o1.write("%s\n%s\n%s\n%s\n" % (h1, s1, p1, q1))
            o2.write("%s\n%s\n%s\n%s\n" % (h2, s2, p2, q2))
            pairs_out += 1

    print(
        "r2_polyg_tail remediation: pairs_in=%d pairs_out=%d "
        "r2_polyg_trimmed=%d pairs_dropped_short=%d (R2 3' poly-G tails "
        "trimmed; R1 unchanged; pairs dropped when a mate < %d bp)"
        % (pairs_in, pairs_out, r2_trimmed, pairs_dropped, MIN_LEN)
    )


if __name__ == "__main__":
    main()
