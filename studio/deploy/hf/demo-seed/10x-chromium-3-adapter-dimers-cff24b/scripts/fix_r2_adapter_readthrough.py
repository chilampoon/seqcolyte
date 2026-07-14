#!/usr/bin/env python3
"""Remediate check_id r2_adapter_readthrough for the 10x_3p_v3 library.

QC finding: 3.6% of R2 reads contain the 3' read-through adapter stem
AGATCGGAAGAGCACA (the Illumina/TruSeq Read 2 adapter, per the library spec's
illumina_truseq oligo). On a 10x 3' v3 library R2 is the cDNA read; when the
insert is shorter than the read length the sequencer reads through into the
adapter on the 3' end.

Fix (ONLY this): trim the 3' read-through adapter from R2 and everything 3' of
it. R1 (the cell-barcode + UMI read) and all 5' bases are left untouched. A
pair is dropped if either mate is shorter than MIN_LEN after trimming. R1/R2
stay paired and in lockstep. Deterministic and safe to re-run (outputs are
overwritten).
"""

import gzip
import os
import sys

R1_IN = sys.argv[1] if len(sys.argv) > 1 else "inputs/fastq/R1.fastq.gz"
R2_IN = sys.argv[2] if len(sys.argv) > 2 else "inputs/fastq/R2.fastq.gz"
R1_OUT = sys.argv[3] if len(sys.argv) > 3 else "remediated/R1.fastq.gz"
R2_OUT = sys.argv[4] if len(sys.argv) > 4 else "remediated/R2.fastq.gz"

# Illumina Read 2 adapter stem (spec oligo illumina_truseq; the QC finding's
# reported read-through sequence). Match >=8 bp overlap, allow 1 mismatch.
ADAPTER = "AGATCGGAAGAGCACA"
MIN_OVERLAP = 8
MAX_MISMATCH = 1
MIN_LEN = 20


def find_adapter(seq):
    """Return the leftmost index where the 3' read-through adapter begins,
    or -1 if absent. Considers full-length internal matches and shorter
    partial overlaps flush against the 3' end of the read."""
    alen = len(ADAPTER)
    slen = len(seq)
    last_start = slen - MIN_OVERLAP  # beyond this the overlap is < MIN_OVERLAP
    for i in range(last_start + 1):
        overlap = alen if slen - i >= alen else slen - i
        mism = 0
        matched = True
        for j in range(overlap):
            if seq[i + j] != ADAPTER[j]:
                mism += 1
                if mism > MAX_MISMATCH:
                    matched = False
                    break
        if matched:
            return i
    return -1


def read_records(handle):
    """Yield (header, seq, plus, qual) FASTQ records."""
    while True:
        header = handle.readline()
        if not header:
            return
        seq = handle.readline()
        plus = handle.readline()
        qual = handle.readline()
        if not qual:
            return
        yield (header.rstrip("\n"), seq.rstrip("\n"),
               plus.rstrip("\n"), qual.rstrip("\n"))


def main():
    for out_path in (R1_OUT, R2_OUT):
        parent = os.path.dirname(out_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    pairs_in = 0
    pairs_out = 0
    r2_trimmed = 0
    pairs_dropped = 0

    with gzip.open(R1_IN, "rt") as r1_in, \
            gzip.open(R2_IN, "rt") as r2_in, \
            gzip.open(R1_OUT, "wt") as r1_out, \
            gzip.open(R2_OUT, "wt") as r2_out:
        r1_iter = read_records(r1_in)
        r2_iter = read_records(r2_in)
        for rec1, rec2 in zip(r1_iter, r2_iter):
            pairs_in += 1
            h1, s1, p1, q1 = rec1
            h2, s2, p2, q2 = rec2

            cut = find_adapter(s2)
            if cut >= 0:
                s2 = s2[:cut]
                q2 = q2[:cut]
                r2_trimmed += 1

            if len(s1) < MIN_LEN or len(s2) < MIN_LEN:
                pairs_dropped += 1
                continue

            r1_out.write("%s\n%s\n%s\n%s\n" % (h1, s1, p1, q1))
            r2_out.write("%s\n%s\n%s\n%s\n" % (h2, s2, p2, q2))
            pairs_out += 1

    print(
        "r2_adapter_readthrough remediation: pairs_in=%d pairs_out=%d "
        "r2_reads_adapter_trimmed=%d pairs_dropped_below_%dbp=%d "
        "(trimmed 3' adapter %s from R2 only; R1 and 5' bases untouched)"
        % (pairs_in, pairs_out, r2_trimmed, MIN_LEN, pairs_dropped, ADAPTER)
    )


if __name__ == "__main__":
    main()
