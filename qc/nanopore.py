"""Single-cell Nanopore long-read QC.

Scans raw ONT reads for the **TSO-concatemer** artifact — internal template-switch-oligo copies
left when template switching chains cDNAs — plus barcode-structure and read-length checks. Emits
the same ``qc_report.json`` schema as the Illumina engine so the studio renders it identically.

The concatemer finding's recommended fix names biotinylated-TSO + streptavidin pull-down enrichment
(the Cell Stem Cell mitigation), which the LLM diagnosis picks up.

    python -m qc.nanopore --spec <spec.json> --reads <reads.fastq.gz> [--labels labels.tsv] \
        --json-out <report.json> [--no-llm] [--model claude-opus-4-8]
"""

from __future__ import annotations

import argparse
import gzip
import json

from qc import QC_VERSION
from qc.engine import _deterministic_rank
from seqcolyte.spec.loader import load_spec

TSO = "AAGCAGTGGTATCAACGCAGAGTACATGGG"
R1_HANDLE = "CTACACGACGCTCTTCCGATCT"
_COMP = str.maketrans("ACGTN", "TGCAN")


def revcomp(s: str) -> str:
    return s.translate(_COMP)[::-1]


TSOR = revcomp(TSO)
_L = len(TSO)
CONC_THRESHOLD = 0.05  # >5% concatemer reads → fail


def _fuzzy_at(seq: str, pos: int, target: str, k: int) -> bool:
    w = seq[pos : pos + len(target)]
    return len(w) == len(target) and sum(a != b for a, b in zip(w, target)) <= k


def _fuzzy_find(seq: str, target: str, k: int, hi: int) -> bool:
    for i in range(0, min(hi, len(seq) - len(target)) + 1):
        if _fuzzy_at(seq, i, target, k):
            return True
    return False


def internal_tso(seq: str, k: int = 4, edge: int = 45) -> int:
    """TSO/revcomp hits that are NOT within `edge` bp of either end — the concatemer signature."""
    hits, i = 0, edge
    while i <= len(seq) - _L - edge:
        if _fuzzy_at(seq, i, TSO, k) or _fuzzy_at(seq, i, TSOR, k):
            hits += 1
            i += _L
        else:
            i += 1
    return hits


def _load_labels(path: str | None) -> dict[str, int]:
    labels: dict[str, int] = {}
    if not path:
        return labels
    for j, line in enumerate(open(path)):
        if j == 0:
            continue
        p = line.rstrip("\n").split("\t")
        if len(p) > 3:
            labels[p[0]] = int(p[3])  # `affected`
    return labels


def scan(reads_path: str, labels: dict[str, int]) -> dict:
    lengths: list[int] = []
    n = n_conc = n_bc = 0
    tp = fp = fn = tn = 0
    rid = None
    for j, line in enumerate(gzip.open(reads_path, "rt")):
        m = j % 4
        if m == 0:
            rid = line[1:].strip()
        elif m == 1:
            seq = line.strip()
            n += 1
            lengths.append(len(seq))
            is_conc = internal_tso(seq) >= 1
            if is_conc:
                n_conc += 1
            if _fuzzy_find(seq, R1_HANDLE, 6, 60):
                n_bc += 1
            if labels:
                t = labels.get(rid, 0)
                tp += is_conc and t
                fp += is_conc and not t
                fn += (not is_conc) and t
                tn += (not is_conc) and (not t)
    lengths.sort()
    return {
        "n": n, "lengths": lengths, "n_conc": n_conc, "n_bc": n_bc,
        "cm": (tp, fp, fn, tn), "true_aff": (sum(labels.values()) if labels else None),
    }


def build_findings(s: dict) -> list[dict]:
    n = s["n"]
    lengths = s["lengths"]
    modal = max(set(lengths), key=lengths.count) if lengths else 0
    med = lengths[len(lengths) // 2] if lengths else 0
    conc = s["n_conc"] / n if n else 0.0
    bc = s["n_bc"] / n if n else 0.0
    conc_fail = conc > CONC_THRESHOLD
    return [
        {
            "check_id": "tso_concatemer",
            "title": "TSO concatemers (internal template-switch oligo)",
            "verdict": "fail" if conc_fail else "pass",
            "value": round(conc, 4), "unit": "fraction", "threshold": "< 0.05",
            "affected_fraction": round(conc, 4),
            "severity": round(min(1.0, conc * 2), 3) if conc_fail else 0.0,
            "evidence": [
                {
                    "spec_ref": "oligos.oligo_template_switching_oligo_tso",
                    "note": "an internal TSO copy is the hallmark of a template-switch concatemer",
                }
            ],
            "detail": (
                f"{conc * 100:.1f}% of reads carry an internal TSO copy — a template-switch "
                f"concatemer (two cDNAs joined through tandem TSO sequences). Standard mitigation is "
                f"biotinylated-TSO with streptavidin pull-down to remove concatemers before "
                f"sequencing (Cell Stem Cell); computationally, split reads at internal TSO junctions."
            ),
        },
        {
            "check_id": "cell_barcode_structure",
            "title": "Cell barcode + UMI structure present",
            "verdict": "pass" if bc >= 0.9 else "warn",
            "value": round(bc, 4), "unit": "fraction", "threshold": ">= 0.9",
            "affected_fraction": round(1 - bc, 4),
            "severity": 0.0 if bc >= 0.9 else 0.2,
            "evidence": [
                {
                    "spec_ref": "oligos.oligo_illumina_truseq_read1_primer",
                    "note": "Read 1 handle + 16 bp barcode + 12 bp UMI at the read 5' end",
                }
            ],
            "detail": f"{bc * 100:.1f}% of reads carry the Read-1 handle + barcode/UMI block at the 5' end.",
        },
        {
            "check_id": "read_length",
            "title": "Full-length read distribution",
            "verdict": "pass",
            "value": modal, "unit": "bp", "threshold": "long-read",
            "affected_fraction": None, "severity": 0.0,
            "evidence": [{"spec_ref": "read_structure.reads", "note": "Nanopore reads span the full molecule"}],
            "detail": f"read length median {med} bp (modal {modal} bp) across {n:,} reads.",
        },
    ]


def run_nanopore_qc(spec_path, reads, *, labels=None, use_llm=True, model="claude-opus-4-8"):
    spec = load_spec(spec_path)
    label_map = _load_labels(labels)
    s = scan(reads, label_map)
    findings = build_findings(s)
    lengths = s["lengths"]
    modal = max(set(lengths), key=lengths.count) if lengths else 0
    profile = {
        "n_pairs": s["n"],
        "r1_len": {"min": lengths[0], "max": lengths[-1], "modal": modal} if lengths else {"min": 0, "max": 0, "modal": 0},
        "r2_len": {"min": lengths[0], "max": lengths[-1], "modal": modal} if lengths else {"min": 0, "max": 0, "modal": 0},
    }

    if use_llm:
        try:
            from qc.planner import rank_with_llm
            plan = rank_with_llm(spec, profile, findings, model=model)
            plan["method"] = "llm"
        except Exception as exc:
            plan = _deterministic_rank(findings)
            plan["llm_error"] = str(exc)[:200]
    else:
        plan = _deterministic_rank(findings)

    report = {
        "qc_version": QC_VERSION, "spec_id": spec.spec_id, "assay": spec.assay,
        "platform": spec.platform, "profile": profile, "findings": findings, "plan": plan,
        "overall": "fail" if any(f["verdict"] == "fail" for f in findings)
        else "warn" if any(f["verdict"] == "warn" for f in findings) else "pass",
    }
    if label_map:
        tp, fp, fn, tn = s["cm"]
        prec = tp / (tp + fp) if (tp + fp) else None
        rec = tp / (tp + fn) if (tp + fn) else None
        f1 = (2 * prec * rec / (prec + rec)) if (prec and rec) else None
        report["eval"] = {
            "n": s["n"], "predicted_affected": s["n_conc"], "true_affected": s["true_aff"],
            "precision": round(prec, 4) if prec is not None else None,
            "recall": round(rec, 4) if rec is not None else None,
            "f1": round(f1, 4) if f1 is not None else None,
            "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        }
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--reads", required=True)
    ap.add_argument("--labels", default=None)
    ap.add_argument("--json-out", required=True)
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--model", default="claude-opus-4-8")
    a = ap.parse_args()
    report = run_nanopore_qc(a.spec, a.reads, labels=a.labels, use_llm=not a.no_llm, model=a.model)
    with open(a.json_out, "w") as fh:
        json.dump(report, fh, indent=2)
    print(f"[nanopore-qc] overall={report['overall']} → {a.json_out}")
    for f in report["findings"]:
        print(f"  [{f['verdict']:>4}] {f['check_id']}: {f['detail'][:80]}")


if __name__ == "__main__":
    main()
