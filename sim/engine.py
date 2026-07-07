"""Simulator orchestrator: assign each pair a label, rewrite R2 for affected pairs (R1 copied
byte-identically), and emit the failure FASTQs, ground-truth labels, and a run manifest."""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
from collections import Counter
from pathlib import Path

import numpy as np

from seqcolyte.io.fastx import FastqRecord, iter_pairs, write_fastx_gz
from seqcolyte.spec.loader import load_spec
from sim import SIM_VERSION
from sim.base import ReadCtx
from sim.config import SimConfig
from sim.labels import write_labels
from sim.registry import get_mode
from sim.rng import read_rng

__all__ = ["run_simulation", "assign_label"]


def assign_label(rng: np.random.Generator, params: dict) -> tuple[str, str | None]:
    """Assign clean / readthrough / pure_dimer using two sequential draws from ``rng``."""
    affected_fraction = float(params.get("affected_fraction", 0.30))
    dimer_fraction = float(params.get("dimer_fraction", 0.33))
    if rng.random() >= affected_fraction:
        return "clean", None
    if rng.random() < dimer_fraction:
        return "pure_dimer", "pure_dimer"
    return "readthrough", "readthrough"


def _md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_simulation(config: SimConfig) -> dict:
    spec = load_spec(config.spec)
    mode = get_mode(config.failure_mode)
    if not mode.applies_to(spec):
        raise ValueError(
            f"mode {mode.name!r} (platform {mode.platform!r}) does not apply to spec platform {spec.platform!r}"
        )
    cb_slice = spec.segment_slice("R1", "cell_barcode")
    umi_slice = spec.segment_slice("R1", "umi")

    for p in (config.out_r1, config.out_r2, config.out_labels, config.out_manifest):
        Path(p).parent.mkdir(parents=True, exist_ok=True)

    # R1 is left byte-identical: copy the file rather than round-tripping records.
    shutil.copyfile(config.input_r1, config.out_r1)

    counts: Counter[str] = Counter()
    rows: list[dict] = []

    def rewritten_r2():
        for i, (r1, r2) in enumerate(iter_pairs(config.input_r1, config.input_r2)):
            rng = read_rng(config.seed, i)
            label, subtype = assign_label(rng, config.params)
            cb = r1.sequence[cb_slice]
            umi = r1.sequence[umi_slice]
            if label == "clean":
                out = r2
                fields: dict = {}
                construct = "clean"
            else:
                ctx = ReadCtx(r1=r1, r2=r2, spec=spec, params=config.params, rng=rng,
                              pair_index=i, subtype=subtype, cb=cb, umi=umi, r2_len=len(r2.sequence))
                res = mode.build_r2(ctx)
                out = FastqRecord(name=r2.name, comment=r2.comment, sequence=res.sequence, quality=res.quality)
                fields = res.fields
                construct = res.construct
            counts[label] += 1
            rows.append({
                "read_id": r2.name, "pair_index": i, "label": label,
                "failure_mode": config.failure_mode if label != "clean" else "none",
                "affected": int(label != "clean"),
                "r1_len": len(r1.sequence), "r2_len": len(out.sequence),
                "cb": cb, "umi": umi,
                "insert_len": fields.get("insert_len", ""),
                "polyA_len": fields.get("polyA_len", ""),
                "pad_len": fields.get("pad_len", ""),
                "truncated": int(fields["truncated"]) if "truncated" in fields else "",
                "construct": construct,
            })
            yield out

    n_pairs = write_fastx_gz(config.out_r2, rewritten_r2())
    write_labels(config.out_labels, rows)

    r1_in_md5, r1_out_md5 = _md5(config.input_r1), _md5(config.out_r1)
    r1_identical = r1_in_md5 == r1_out_md5

    manifest = {
        "name": config.name,
        "sim_version": SIM_VERSION,
        "spec_id": spec.spec_id,
        "failure_mode": config.failure_mode,
        "seed": config.seed,
        "params": config.params,
        "n_pairs": n_pairs,
        "label_counts": dict(counts),
        "label_fractions": {k: round(v / n_pairs, 4) for k, v in counts.items()} if n_pairs else {},
        "inputs": {"r1": config.input_r1, "r2": config.input_r2},
        "outputs": {"r1": config.out_r1, "r2": config.out_r2, "labels": config.out_labels},
        "r1_input_md5": r1_in_md5,
        "r1_output_md5": r1_out_md5,
        "r1_byte_identical": r1_identical,
        "python": platform.python_version(),
    }
    Path(config.out_manifest).write_text(json.dumps(manifest, indent=2) + "\n")

    if not r1_identical:
        raise RuntimeError("R1 output is not byte-identical to input — invariant violated")
    return manifest
