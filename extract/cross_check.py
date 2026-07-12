"""Cross-check a paper-derived extraction against a technology's curated ground truth — PAPERS FIRST.

The oracle is each protocol's ``groundtruth_oligos.json`` + ``groundtruth_final_lib_struct.json`` (the
normalized, machine-readable form of the curated scg_html; each records ``source_html_file``). We NEVER
overwrite the extraction — we only record where the paper-derived spec diverges from the human curation and
flag the *big* conflicts for the user.

``big_conflict`` is driven by the substantive signals — oligo-sequence recall and cell-barcode/UMI length
disagreement — NOT by an exact match of the annotated library string (token naming legitimately differs
across technologies, e.g. ``[I7_INDEX:8]`` vs ``[SAMPLE_INDEX:8]``), which is kept informational only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from extract.doc_extract import _norm

_LEN_TOKENS = ("CELL_BARCODE", "UMI")
# `big_conflict` should mean a genuine scientific divergence, not just missing standard adapters the paper
# omits. So we flag only when >half the curated oligo sequences are absent, or a barcode/UMI LENGTH differs.
RECALL_FLOOR = 0.5


def _token_lengths(seq: str) -> dict[str, list[int]]:
    """{token: [lengths]} — multiple entries for combinatorial multi-round barcodes."""
    return {t: sorted(int(m) for m in re.findall(rf"\[{t}:(\d+)\]", seq or "")) for t in _LEN_TOKENS}


def cross_check_against_groundtruth(extraction: dict, groundtruth_dir: str | Path) -> dict:
    gt_dir = Path(groundtruth_dir)
    gto, gtl = gt_dir / "groundtruth_oligos.json", gt_dir / "groundtruth_final_lib_struct.json"
    if not (gto.exists() and gtl.exists()):
        return {"status": "no_groundtruth", "big_conflict": False}

    gt_oligos = json.loads(gto.read_text()).get("oligos", [])
    libs = json.loads(gtl.read_text()).get("libraries") or [{}]
    gt_lib = libs[0]

    got = {_norm(o.get("sequence", "")) for o in extraction.get("oligos", []) if o.get("sequence")}
    for o in extraction.get("oligos", []):
        for c in o.get("components", []):
            if c.get("sequence"):
                got.add(_norm(c["sequence"]))

    gt_pairs = [(_norm(o.get("sequence") or ""), o.get("name", "")) for o in gt_oligos if o.get("sequence")]
    hits = [(name, norm in got) for norm, name in gt_pairs if norm]
    n_hit = sum(1 for _, ok in hits if ok)
    recall = round(n_hit / len(hits), 3) if hits else None
    missed = [name for name, ok in hits if not ok]

    got_ann = extraction.get("final_library", {}).get("annotated_library_sequence", "")
    gt_ann = gt_lib.get("annotated_library_sequence", "")
    lib_match = bool(_norm(got_ann)) and _norm(got_ann) == _norm(gt_ann)

    # Only a REAL length disagreement: both sides tokenized the region and the lengths differ. If one side
    # is empty it means that side used prose / a bare token (a tokenization gap, not a length conflict) —
    # that shows up as low recall instead, not a substantive flag.
    et, gt = _token_lengths(got_ann), _token_lengths(gt_ann)
    length_diffs = {t: {"extracted": et[t], "groundtruth": gt[t]}
                    for t in _LEN_TOKENS if et[t] and gt[t] and et[t] != gt[t]}

    big = bool((recall is not None and recall < RECALL_FLOOR) or length_diffs)
    return {
        "status": "checked", "source_html_file": gt_lib.get("source_html_file"),
        "oligo_seq_recall": recall, "oligo_seqs_matched": n_hit, "oligo_seqs_total": len(hits),
        "missed_oligos": missed,
        "annotated_library_exact_match": lib_match,        # informational only
        "annotated_library_got": got_ann, "annotated_library_expected": gt_ann,
        "barcode_umi_length_diffs": length_diffs,
        "big_conflict": big,
    }


def render_report(records: list[dict]) -> str:
    """Render an aggregate CONFLICTS.md from per-technology records ``{folder, title, crosscheck}``.

    Separates the SUBSTANTIVE conflicts (barcode/UMI length disagreements — a real chemistry
    contradiction) from the noisier low-overlap cases (usually version drift between the paper and the
    curated page, or standard adapters the paper references but never prints)."""
    checked = [r for r in records if r.get("crosscheck", {}).get("status") == "checked"]
    length = [r for r in checked if r["crosscheck"]["barcode_umi_length_diffs"]]
    low_overlap = [r for r in checked
                   if not r["crosscheck"]["barcode_umi_length_diffs"]
                   and (r["crosscheck"].get("oligo_seq_recall") or 1) < RECALL_FLOOR]
    low_overlap.sort(key=lambda r: r["crosscheck"].get("oligo_seq_recall") or 1)

    lines = ["# Cross-check conflicts — paper-derived extraction vs curated scg_html", ""]
    lines.append("The wiki spec is extracted from the papers/protocols (papers-first); this compares it "
                 "against the curated scg_html ground truth. A flag means the paper disagrees with the "
                 "human curation — which may itself be the error. Recall is sequence-EXACT, so version "
                 "drift and standard adapters the paper omits legitimately lower it.")
    lines.append("")
    lines.append(f"{len(checked)} cross-checked · **{len(length)} barcode/UMI length disagreements "
                 f"(substantive)** · {len(low_overlap)} low sequence-overlap (recall < {RECALL_FLOOR}).")

    lines += ["", "## Barcode/UMI length disagreements (substantive — review these first)", ""]
    if length:
        lines += ["| technology | recall | length disagreement |", "|---|---|---|"]
        for r in sorted(length, key=lambda r: r["folder"]):
            c = r["crosscheck"]
            diffs = "; ".join(f"**{t}**: paper {v['extracted']} vs curation {v['groundtruth']}"
                              for t, v in c["barcode_umi_length_diffs"].items())
            lines.append(f"| {r['folder']} | {c['oligo_seq_recall']} | {diffs} |")
    else:
        lines.append("_None — no barcode/UMI length contradictions._")

    lines += ["", "## Low sequence overlap (recall < %s — usually version drift / unprinted adapters)" % RECALL_FLOOR, "",
              "| technology | recall | oligos matched | top missed oligos |", "|---|---|---|---|"]
    for r in low_overlap:
        c = r["crosscheck"]
        missed = ", ".join(c["missed_oligos"][:5]) + ("…" if len(c["missed_oligos"]) > 5 else "")
        lines.append(f"| {r['folder']} | {c['oligo_seq_recall']} | "
                     f"{c['oligo_seqs_matched']}/{c['oligo_seqs_total']} | {missed or '—'} |")

    lines += ["", "## All cross-checked technologies", "",
              "| technology | recall | library exact-match | flag |", "|---|---|---|---|"]
    for r in sorted(checked, key=lambda r: r["folder"]):
        c = r["crosscheck"]
        flag = "⚠️ length" if c["barcode_umi_length_diffs"] else ("low-overlap" if c["big_conflict"] else "ok")
        lines.append(f"| {r['folder']} | {c['oligo_seq_recall']} | "
                     f"{'yes' if c['annotated_library_exact_match'] else 'no'} | {flag} |")
    no_gt = [r["folder"] for r in records if r.get("crosscheck", {}).get("status") == "no_groundtruth"]
    if no_gt:
        lines += ["", f"_No ground truth (cross-check skipped): {', '.join(no_gt)}._"]
    return "\n".join(lines) + "\n"
