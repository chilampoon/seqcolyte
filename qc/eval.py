"""Score the QC's read-level failure detection against the simulator's ground-truth labels.

This is the payoff of a simulator that emits labels: we can measure precision/recall of catching
the injected failures. Prediction uses the same failure signatures the checks flag (TSO at R2 start,
or a poly-G no-signal tail); labels align to FASTQ order (the simulator writes rows in pair order).
"""

from __future__ import annotations

from qc.model import has_homopolymer_tail, startswith_fuzzy

__all__ = ["predict_affected", "evaluate"]

_TSO_OLIGO = "oligo_template_switching_oligo_tso"


def predict_affected(r2: str, tso: str, dark_base: str | None) -> bool:
    if startswith_fuzzy(r2, tso, 2):
        return True
    return bool(dark_base) and has_homopolymer_tail(r2, dark_base)


def _read_truth(labels_path: str) -> list[bool]:
    with open(labels_path) as fh:
        header = fh.readline().rstrip("\n").split("\t")
        ai = header.index("affected")
        return [line.rstrip("\n").split("\t")[ai] == "1" for line in fh]


def evaluate(profile, spec, labels_path: str) -> dict:
    tso = spec.oligo_sequence(_TSO_OLIGO)
    dark = spec.platform_params.get("dark_base")
    truth = _read_truth(labels_path)
    n = min(len(truth), profile.n_pairs)

    tp = fp = fn = tn = 0
    predicted = 0
    for i in range(n):
        pred = predict_affected(profile.r2[i], tso, dark)
        predicted += pred
        t = truth[i]
        if pred and t:
            tp += 1
        elif pred and not t:
            fp += 1
        elif not pred and t:
            fn += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * precision * recall / (precision + recall)) if (precision and recall) else None
    return {
        "n": n, "predicted_affected": predicted, "true_affected": sum(truth[:n]),
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "f1": round(f1, 4) if f1 is not None else None,
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
    }
