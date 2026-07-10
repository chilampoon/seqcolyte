"""Single-cell Nanopore long-read QC.

Does NOT assume reads start with the R1 handle. Every read is first **stranded / classified** by
searching for adapter1 (R1 handle), adapter2 (TSO-derived motif), their reverse complements, and
internal copies (fused/concatemer), then normalized to adapter1-first before barcode/UMI extraction.

Reports a long-read profile (N50, median, orientation/classification fractions) and separates:
handle-detection rate, extractable-CB/UMI rate, full-length (both-flank) rate, and the internal-TSO
concatemer/fused fraction (fix: split at internal TSO junctions; enriched-profile pull-down is optional).

Emits the ``qc_report.json`` schema. Long-read fields are primary; ``n_pairs``/``r1_len``/``r2_len``
are retained only as a documented backward-compatibility layer for the existing report renderer.

    python -m qc.nanopore --spec <spec.json> --reads <reads.fastq.gz> [--labels labels.tsv] \
        --json-out <report.json> [--no-llm]
"""

from __future__ import annotations

import argparse
import gzip
import json
import statistics
from collections import Counter

from qc import QC_VERSION
from qc.engine import _deterministic_rank
from seqcolyte.nanopore import ADAPTER2_MOTIF, NanoporeChem, reverse_complement
from seqcolyte.spec.loader import load_spec

CONC_THRESHOLD = 0.05  # >5% concatemer/fused reads → fail
EDGE = 45  # bp from either end considered "terminal"


def _seed_find(seq: str, target: str, lo: int = 0, hi: int | None = None,
               seed_len: int = 9, n_seeds: int = 3) -> int | None:
    """Indel-tolerant detection: an adapter is 'present' if any of a few short exact seeds of it
    appears in the window. Seeds survive indels elsewhere in the adapter (ONT reads have indels), and
    exact seed lookup via str.find is fast. Returns the approximate adapter start, else None."""
    L = len(target)
    hi = len(seq) if hi is None else min(hi + L, len(seq))
    span = max(1, (L - seed_len) // max(1, n_seeds - 1)) if n_seeds > 1 else 1
    for s in range(0, L - seed_len + 1, span):
        p = seq.find(target[s : s + seed_len], max(0, lo), hi)
        if p != -1:
            return max(0, p - s)
    return None


def _count_internal(seq: str, target: str, lo: int, hi: int, seed_len: int = 8, min_seeds: int = 2) -> int:
    """Count distinct internal occurrences of `target` in [lo, hi) — indel-tolerant, low false-positive.

    Several short seeds of `target` are located; each hit is projected to the implied `target` start;
    hits within ~8 bp are one cluster. A cluster counts as a real signature only if **≥ min_seeds
    distinct seeds** agree on it — so a lone chance seed match in random cDNA is ignored, while a real
    (noisy) TSO_RC still lights up 2–3 seeds."""
    L = len(target)
    offsets = list(range(0, L - seed_len + 1, max(1, (L - seed_len) // 2)))
    starts: list[tuple[int, int]] = []
    for off in offsets:
        sd = target[off : off + seed_len]
        i = lo
        while True:
            p = seq.find(sd, i, hi)
            if p == -1:
                break
            starts.append((p - off, off))  # implied target start
            i = p + 1
    starts.sort()
    clusters, cluster, last = 0, [], None
    for ts, off in starts + [(10**9, -1)]:
        if last is not None and ts - last > 8:
            if len({o for _, o in cluster}) >= min_seeds:
                clusters += 1
            cluster = []
        cluster.append((ts, off))
        last = ts
    return clusters


def n50(lengths_sorted: list[int]) -> int:
    total = sum(lengths_sorted)
    if not total:
        return 0
    acc = 0
    for x in reversed(lengths_sorted):  # descending
        acc += x
        if acc * 2 >= total:
            return x
    return lengths_sorted[-1]


class Stranding:
    """Adapter1/adapter2 detection + orientation normalization + read classification."""

    def __init__(self, chem: NanoporeChem):
        self.a1 = chem.r1_handle
        self.a1_rc = reverse_complement(chem.r1_handle)
        self.a2 = ADAPTER2_MOTIF  # short ONT stranding motif (TSO_RC minus CCC)
        self.a2_rc = reverse_complement(ADAPTER2_MOTIF)
        self.tso_rc = chem.tso_rc
        self.cb_len, self.umi_len = chem.cb_len, chem.umi_len

    def classify(self, seq: str) -> dict:
        n = len(seq)
        tso = reverse_complement(self.tso_rc)  # the forward TSO (5' of a reverse-oriented read)
        # orientation evidence (indel-tolerant seeds, at the expected ends)
        a1_5 = _seed_find(seq, self.a1, 0, EDGE)
        tsorc_3 = _seed_find(seq, self.tso_rc, n - EDGE - len(self.tso_rc), n)
        tso_5 = _seed_find(seq, tso, 0, EDGE)
        a1rc_3 = _seed_find(seq, self.a1_rc, n - EDGE - len(self.a1_rc), n)
        fwd_ev = a1_5 is not None or tsorc_3 is not None
        rev_ev = tso_5 is not None or a1rc_3 is not None
        orientation = "forward" if (fwd_ev and not rev_ev) else "reverse" if (rev_ev and not fwd_ev) \
            else ("forward" if fwd_ev else "unknown")
        normalized = seq if orientation != "reverse" else reverse_complement(seq)

        # on the normalized (adapter1-first) read: flanks + internal signatures
        h = _seed_find(normalized, self.a1, 0, EDGE + 20)
        t = _seed_find(normalized, self.tso_rc, len(normalized) - EDGE - len(self.tso_rc), len(normalized))
        internal = _count_internal(normalized, self.tso_rc, EDGE, max(EDGE, len(normalized) - EDGE))
        both = h is not None and t is not None
        if internal >= 1:
            category = "fused_or_concatemer"
        elif both:
            category = "full_length"
        elif h is not None:
            category = "adapter1_only"
        elif t is not None:
            category = "adapter2_only"
        else:
            category = "unclassified"
        return {"orientation": orientation, "category": category, "internal": internal,
                "both_flanks": both, "normalized": normalized, "handle_pos": h}

    def extract_cb_umi(self, normalized: str, handle_pos: int | None) -> tuple[str, str] | None:
        """Tolerant extraction: anchor on the R1 handle, take the next CB+UMI bases."""
        if handle_pos is None:
            return None
        start = handle_pos + len(self.a1)
        cb = normalized[start : start + self.cb_len]
        umi = normalized[start + self.cb_len : start + self.cb_len + self.umi_len]
        if len(cb) < self.cb_len or len(umi) < self.umi_len:
            return None
        return cb, umi


def _labels_index(path: str | None):
    if not path:
        return None
    rows = [ln.rstrip("\n").split("\t") for ln in open(path)]
    h = rows[0]
    idx = {c: i for i, c in enumerate(h)}
    aff = idx.get("affected")
    concat = idx.get("failure_mode")
    m: dict[str, tuple[int, bool]] = {}
    for r in rows[1:]:
        rid = r[0]
        affected = int(r[aff]) if aff is not None else 0
        is_conc = concat is not None and r[concat] in ("tso_concatemer", "fused_read")
        m[rid] = (affected, is_conc)
    return m


def scan(reads_path: str, chem: NanoporeChem, labels):
    st = Stranding(chem)
    lengths: list[int] = []
    cats: Counter = Counter()
    orients: Counter = Counter()
    n = n_handle = n_extract = n_both = n_conc = 0
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
            c = st.classify(seq)
            cats[c["category"]] += 1
            orients[c["orientation"]] += 1
            if c["both_flanks"]:
                n_both += 1
            is_conc = c["category"] == "fused_or_concatemer"
            if is_conc:
                n_conc += 1
            if c["handle_pos"] is not None:
                n_handle += 1
            if st.extract_cb_umi(c["normalized"], c["handle_pos"]) is not None:
                n_extract += 1
            if labels is not None and rid in labels:
                truth = labels[rid][1]  # concatemer/fused label specifically
                pred = is_conc
                tp += pred and truth
                fp += pred and not truth
                fn += (not pred) and truth
                tn += (not pred) and (not truth)
    lengths.sort()
    return {"n": n, "lengths": lengths, "cats": cats, "orients": orients, "n_handle": n_handle,
            "n_extract": n_extract, "n_both": n_both, "n_conc": n_conc, "cm": (tp, fp, fn, tn),
            "true_aff": (sum(1 for v in labels.values() if v[1]) if labels else None)}


def build_findings(s: dict) -> list[dict]:
    n = max(1, s["n"])
    L = s["lengths"]
    conc = s["n_conc"] / n
    handle = s["n_handle"] / n
    extract = s["n_extract"] / n
    full = s["n_both"] / n
    classified = (n - s["cats"].get("unclassified", 0)) / n
    fwd = s["orients"].get("forward", 0) / n
    conc_fail = conc > CONC_THRESHOLD
    return [
        {"check_id": "tso_concatemer", "title": "TSO concatemers / fused reads (internal adapter2)",
         "verdict": "fail" if conc_fail else "pass", "value": round(conc, 4), "unit": "fraction",
         "threshold": "< 0.05", "affected_fraction": round(conc, 4),
         "severity": round(min(1.0, conc * 2), 3) if conc_fail else 0.0,
         "evidence": [{"spec_ref": "adapter_detection.adapter2_motif",
                       "note": "an internal adapter2/TSO copy is the hallmark of a fused/concatemer read"}],
         "detail": (f"{conc * 100:.1f}% of reads carry an internal TSO/adapter2 signature (template-switch "
                    f"concatemer or two fused cDNAs). Fix: split reads at internal TSO junctions "
                    f"(computational). At the bench, the optional enriched profile — full-length "
                    f"biotinylated-primer streptavidin pull-down (ONT SST_9198) — depletes such artifacts; "
                    f"the baseline direct-ligation prep does not.")},
        {"check_id": "read_classification", "title": "Stranding / read classification",
         "verdict": "warn" if classified < 0.8 else "pass", "value": round(classified, 4), "unit": "fraction",
         "threshold": ">= 0.8", "affected_fraction": round(1 - classified, 4),
         "severity": 0.0 if classified >= 0.8 else 0.2,
         "evidence": [{"spec_ref": "read_models", "note": "adapter1/adapter2 detection on both strands"}],
         "detail": (f"{classified * 100:.1f}% of reads classified; {full * 100:.1f}% full-length (both flanks); "
                    f"orientation {fwd * 100:.0f}% forward. Categories: "
                    f"{dict(s['cats'])}.")},
        {"check_id": "handle_detection", "title": "R1-derived handle detected near read end",
         "verdict": "pass" if handle >= 0.7 else "warn", "value": round(handle, 4), "unit": "fraction",
         "threshold": ">= 0.7", "affected_fraction": round(1 - handle, 4),
         "severity": 0.0 if handle >= 0.7 else 0.2,
         "evidence": [{"spec_ref": "adapter_detection.adapter1", "note": "R1 handle (partial TruSeq Read 1)"}],
         "detail": f"R1 handle detected in {handle * 100:.1f}% of reads (handle detection ≠ barcode recovery)."},
        {"check_id": "cb_umi_extractable", "title": "Extractable cell barcode + UMI",
         "verdict": "pass" if extract >= 0.6 else "warn", "value": round(extract, 4), "unit": "fraction",
         "threshold": ">= 0.6", "affected_fraction": round(1 - extract, 4),
         "severity": 0.0 if extract >= 0.6 else 0.2,
         "evidence": [{"spec_ref": "read_models", "note": "handle-anchored 16 bp CB + 12 bp UMI probe"}],
         "detail": f"CB+UMI extractable in {extract * 100:.1f}% of reads (whitelist match not evaluated here)."},
        {"check_id": "read_length", "title": "Long-read length distribution",
         "verdict": "pass", "value": (L[len(L) // 2] if L else 0), "unit": "bp", "threshold": "descriptive",
         "affected_fraction": None, "severity": 0.0,
         "evidence": [{"spec_ref": "read_structure.reads", "note": "single full-molecule read (L1)"}],
         "detail": (f"n={n:,}, median {L[len(L)//2] if L else 0} bp, N50 {n50(L)} bp, max {L[-1] if L else 0} bp." )},
    ]


def run_nanopore_qc(spec_path, reads, *, labels=None, use_llm=True, model="claude-opus-4-8"):
    spec = load_spec(spec_path)
    chem = NanoporeChem.from_spec(spec)
    label_idx = _labels_index(labels)
    s = scan(reads, chem, label_idx)
    findings = build_findings(s)
    L = s["lengths"]
    n = s["n"]
    modal = Counter(L).most_common(1)[0][0] if L else 0
    long_profile = {
        "n_reads": n, "min_length": (L[0] if L else 0), "median_length": (L[len(L) // 2] if L else 0),
        "n50": n50(L), "max_length": (L[-1] if L else 0), "modal_length": modal,
        "full_length_fraction": round(s["n_both"] / max(1, n), 4),
        "orientation_fraction": {k: round(v / max(1, n), 4) for k, v in s["orients"].items()},
        "classified_fraction": round((n - s["cats"].get("unclassified", 0)) / max(1, n), 4),
        "categories": dict(s["cats"]),
    }
    # backward-compat shim for the existing report renderer (documented; NOT paired-end reads)
    profile = {"n_pairs": n,
               "r1_len": {"min": (L[0] if L else 0), "max": (L[-1] if L else 0), "modal": modal},
               "r2_len": {"min": (L[0] if L else 0), "max": (L[-1] if L else 0), "modal": modal},
               "long_read": long_profile}

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
    if label_idx:
        tp, fp, fn, tn = s["cm"]
        prec = tp / (tp + fp) if (tp + fp) else None
        rec = tp / (tp + fn) if (tp + fn) else None
        f1 = (2 * prec * rec / (prec + rec)) if (prec and rec) else None
        report["eval"] = {"n": n, "predicted_affected": s["n_conc"], "true_affected": s["true_aff"],
                          "precision": round(prec, 4) if prec is not None else None,
                          "recall": round(rec, 4) if rec is not None else None,
                          "f1": round(f1, 4) if f1 is not None else None,
                          "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn}}
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
        print(f"  [{f['verdict']:>4}] {f['check_id']}: {f['detail'][:78]}")


if __name__ == "__main__":
    main()
