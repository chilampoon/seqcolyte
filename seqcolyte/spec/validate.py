"""Deterministic (offline, no LLM) chemistry/consistency validator for spec dicts.

Complements the JSON-Schema validation with biology-aware checks: barcode/UMI lengths, reverse-
complement consistency, that a full-length ONT branch never carries P5/P7/i7, that derived sequences
reference an existing source, and that molecule-state / branch references resolve. The headline check
is the **hybrid conflict**: an Illumina P5/P7 final library paired with a full-length TSO-flanked read
model is a contradiction and must be flagged.

    python -m seqcolyte.spec.validate spec/nanopore_10x_3p.json
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass

from seqcolyte.nanopore import reverse_complement

P5 = "AATGATACGGCGACCACCGAGATCTACAC"
P7 = "CAAGCAGAAGACGGCATACGAGAT"
P7_RC = reverse_complement(P7)
_IUPAC = set("ACGTNRYSWKMBVDH")


@dataclass
class Issue:
    severity: str  # "error" | "warning"
    code: str
    message: str

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.code}: {self.message}"


class SpecValidationError(ValueError):
    pass


def _clean(seq: str | None) -> str:
    return "".join(c for c in (seq or "").upper() if c.isalpha())


def _find_oligo(data: dict, *needles: str) -> str | None:
    for o in data.get("oligos", []):
        blob = ((o.get("name") or "") + " " + (o.get("oligo_id") or "")).lower()
        if all(x in blob for x in needles) and o.get("sequence"):
            return _clean(o["sequence"])
    return None


def check_spec(data: dict) -> list[Issue]:
    issues: list[Issue] = []
    platform = data.get("platform")
    nano = platform == "nanopore"

    # 1. valid IUPAC symbols in oligo sequences (ignore bracketed tokens + chemistry marks)
    for o in data.get("oligos", []):
        seq = o.get("sequence")
        if not seq:
            continue
        bare = re.sub(r"\[[^\]]*\]|/[^/]*/|\*", "", seq).upper()
        bad = set(bare) - _IUPAC
        if bad:
            issues.append(Issue("error", "invalid_symbols",
                                f"oligo {o.get('oligo_id')} has non-IUPAC symbols {sorted(bad)}"))

    # 2. CB/UMI lengths for v3/v3.1
    pp = data.get("platform_params", {})
    if pp.get("cell_barcode_len") not in (None, 16):
        issues.append(Issue("error", "cb_length", f"cell_barcode_len={pp['cell_barcode_len']} (v3/v3.1 must be 16)"))
    if pp.get("umi_len") not in (None, 12):
        issues.append(Issue("error", "umi_length", f"umi_len={pp['umi_len']} (v3/v3.1 must be 12)"))
    for rm in data.get("read_models", []):
        for sg in rm.get("segments", []):
            if sg.get("type") == "barcode" and sg.get("length") not in (None, 16):
                issues.append(Issue("error", "cb_length", f"read_model {rm.get('id')} barcode length={sg['length']} (must be 16)"))
            if sg.get("type") == "umi" and sg.get("length") not in (None, 12):
                issues.append(Issue("error", "umi_length", f"read_model {rm.get('id')} umi length={sg['length']} (must be 12)"))

    # 3. TSO_RC consistency (derived == reverse_complement(TSO))
    tso = _find_oligo(data, "template", "switch") or _find_oligo(data, "tso")
    ad = data.get("adapter_detection", {})
    a2_full = _clean(ad.get("adapter2_full", {}).get("sequence"))
    if tso and a2_full and a2_full != reverse_complement(tso):
        issues.append(Issue("error", "tso_rc_mismatch",
                            "adapter_detection.adapter2_full is not reverse_complement(TSO)"))

    # 4/6. no P5/P7/i7 in a full-length ONT final library + hybrid conflict
    fl = data.get("final_library", {})
    fl_seq = _clean(fl.get("annotated_library_sequence"))
    fl_tokens = fl.get("annotated_library_sequence", "")
    illumina_in_final = any(m and m in fl_seq for m in (P5, P7, P7_RC)) or "SAMPLE_INDEX" in fl_tokens
    read_models_full_length = any(
        rm.get("orientation") == "forward" or any(sg.get("name") == "tso_rc" for sg in rm.get("segments", []))
        for rm in data.get("read_models", [])
    )
    read_structure_full_length = any(r.get("read") == "L1" for r in data.get("read_structure", {}).get("reads", []))
    if nano and illumina_in_final:
        issues.append(Issue("error", "ont_final_is_illumina",
                            "platform=nanopore but final_library contains P5/P7/i7 — the full-length ONT input "
                            "must not be the indexed P5/P7 Illumina library"))
    if illumina_in_final and (read_models_full_length or (nano and read_structure_full_length)):
        issues.append(Issue("error", "hybrid_conflict",
                            "incompatible hybrid: an Illumina P5/P7-indexed final_library is paired with a "
                            "full-length TSO-flanked read model / L1 long read"))

    # 5. derived sequences must reference an existing source sequence
    known_names = {"tso": tso is not None, "p5": True, "p7": True}
    for rm in data.get("read_models", []):
        for sg in rm.get("segments", []):
            deriv = sg.get("derivation")
            if deriv:
                m = re.search(r"\(([^)]+)\)", deriv)
                ref = (m.group(1).strip().lower() if m else "")
                if ref and not known_names.get(ref, False):
                    issues.append(Issue("error", "unresolved_derivation",
                                        f"read_model {rm.get('id')} segment {sg.get('name')} derives from "
                                        f"unknown source '{ref}'"))

    # 7. branch material references resolve
    state_ids = {m["id"] for m in data.get("molecule_states", [])}
    for br in data.get("branches", []):
        for key in ("from_material", "final_material"):
            mid = br.get(key)
            if mid and mid not in state_ids:
                issues.append(Issue("error", "bad_material_ref",
                                    f"branch {br.get('id')} {key}={mid!r} is not a molecule_state id"))

    return issues


def validate_or_raise(data: dict) -> list[Issue]:
    issues = check_spec(data)
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        raise SpecValidationError("; ".join(str(e) for e in errors))
    return issues


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python -m seqcolyte.spec.validate <spec.json>", file=sys.stderr)
        sys.exit(2)
    data = json.load(open(sys.argv[1]))
    issues = check_spec(data)
    for i in issues:
        print(i)
    errs = [i for i in issues if i.severity == "error"]
    print(f"\n{len(issues)} issue(s), {len(errs)} error(s)")
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
