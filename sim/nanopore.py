"""Spec-driven single-cell Nanopore long-read simulator.

Builds raw Oxford-Nanopore reads of **full-length amplified 10x 3' cDNA** — the ONT branch input,
*before* Illumina fragmentation. Sequence construction is driven by the loaded spec (via
``seqcolyte.nanopore.NanoporeChem``), not by hard-coded constants duplicated here.

Canonical adapter1-first molecule (see ``seqcolyte.nanopore``)::

    [R1_HANDLE][CB:16][UMI:12][polyT:30][V][N][cDNA][TSO_RC]

Each read is emitted in a randomly chosen orientation (canonical or its reverse complement, ~50/50
by default) and passed through a configurable, seeded **synthetic ONT-like** error model
(substitutions, insertions, deletions, homopolymer contraction/expansion). Artifacts are injected
through a small modular registry. Output is streamed (bounded memory): FASTQ.gz + a rich labels TSV
+ a metadata JSON. This is a synthetic model, NOT a calibrated representation of any flow cell/basecaller.

CLI::

    python -m sim.nanopore --spec spec/nanopore_10x_3p.json --source synthetic --n 10000 --seed 42 \
        --out data/sim/nanopore_clean
    python -m sim.nanopore --spec spec/nanopore_10x_3p.json --source-bam in.bam --n 10000 \
        --concatemer-frac 0.10 --truncate-frac 0.05 --seed 42 --out data/sim/nanopore_mixed
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import random
from dataclasses import asdict, dataclass, field

from seqcolyte.nanopore import ADAPTER2_MOTIF, NanoporeChem, reverse_complement
from seqcolyte.spec.loader import load_spec

VERSION = "nanopore-sim-2.0"

# ---------------------------------------------------------------- error model


@dataclass(frozen=True)
class OntErrorModel:
    """Configurable, seeded synthetic ONT-like error model (not flow-cell calibrated)."""

    sub_rate: float = 0.015
    ins_rate: float = 0.010
    del_rate: float = 0.010
    hp_indel_rate: float = 0.25  # extra length change probability per homopolymer run (>= hp_min)
    hp_min: int = 5
    q_min: int = 8
    q_max: int = 20

    def apply(self, seq: str, rng: random.Random) -> str:
        # homopolymer contraction/expansion first (operates on runs)
        seq = self._homopolymer(seq, rng)
        out: list[str] = []
        for c in seq:
            r = rng.random()
            if r < self.del_rate:
                continue
            if r < self.del_rate + self.ins_rate:
                out.append(rng.choice("ACGT"))
                out.append(c)
            elif r < self.del_rate + self.ins_rate + self.sub_rate:
                out.append(rng.choice([b for b in "ACGT" if b != c] or ["A"]))
            else:
                out.append(c)
        return "".join(out)

    def _homopolymer(self, seq: str, rng: random.Random) -> str:
        out: list[str] = []
        i, n = 0, len(seq)
        while i < n:
            j = i
            while j < n and seq[j] == seq[i]:
                j += 1
            run = j - i
            if run >= self.hp_min and rng.random() < self.hp_indel_rate:
                run = max(1, run + rng.choice([-2, -1, 1, 2]))
            out.append(seq[i] * run)
            i = j
        return "".join(out)

    def quality(self, n: int, rng: random.Random) -> str:
        return "".join(chr(33 + rng.randint(self.q_min, self.q_max)) for _ in range(n))


# ---------------------------------------------------------------- failure modes
#
# Each mode is `(chem, src, rng, cfg) -> (forward_seq, label_extra)`, where forward_seq is the
# canonical-orientation molecule (orientation + errors are applied afterwards). `src` is a
# SourceMol; a mode may pull a second molecule from `cfg.pool` for fused/concatemer reads.


@dataclass
class SourceMol:
    mol_id: str
    cb: str
    umi: str
    cdna: str
    transcript_id: str | None = None


def _corrupt(seq: str, rng: random.Random, n: int) -> str:
    s = list(seq)
    for _ in range(n):
        if not s:
            break
        p = rng.randrange(len(s))
        op = rng.random()
        if op < 0.34:
            s[p] = rng.choice("ACGT")
        elif op < 0.67:
            s.insert(p, rng.choice("ACGT"))
        else:
            del s[p]
    return "".join(s)


def _clean(chem, src, rng, cfg):
    return chem.canonical_molecule(src.cb, src.umi, src.cdna), {"n_internal_signatures": 0, "both_flanks": True}


def _tso_concatemer(chem, src, rng, cfg):
    # two cDNAs joined through a tandem TSO_RC|TSO junction -> internal adapter2/TSO signatures
    other = cfg.pick(rng)
    half = src.cdna[: max(150, len(src.cdna) // 2)]
    frag2 = other.cdna[: rng.randint(150, min(800, len(other.cdna)))]
    seq = (chem.r1_handle + src.cb + src.umi + "T" * chem.polyt_len + "GN" + half
           + chem.tso_rc + chem.tso + frag2 + chem.tso_rc)
    return seq, {"n_internal_signatures": 2, "both_flanks": True, "n_source_molecules": 2}


def _fused_read(chem, src, rng, cfg):
    other = cfg.pick(rng)
    seq = chem.canonical_molecule(src.cb, src.umi, src.cdna) + chem.canonical_molecule(other.cb, other.umi, other.cdna)
    return seq, {"n_internal_signatures": 2, "both_flanks": True, "n_source_molecules": 2}


def _missing_adapter1(chem, src, rng, cfg):
    full = chem.canonical_molecule(src.cb, src.umi, src.cdna)
    return full[len(chem.r1_handle) + 4:], {"n_internal_signatures": 0, "both_flanks": False}


def _missing_tso(chem, src, rng, cfg):
    full = chem.canonical_molecule(src.cb, src.umi, src.cdna)
    return full[: -len(chem.tso_rc)], {"n_internal_signatures": 0, "both_flanks": False}


def _trunc5(chem, src, rng, cfg):
    full = chem.canonical_molecule(src.cb, src.umi, src.cdna)
    cut = rng.randint(len(chem.r1_handle), len(chem.r1_handle) + chem.cb_len + chem.umi_len + 20)
    return full[cut:], {"n_internal_signatures": 0, "both_flanks": False, "truncated": True}


def _trunc3(chem, src, rng, cfg):
    full = chem.canonical_molecule(src.cb, src.umi, src.cdna)
    return full[: rng.randint(len(chem.r1_handle) + 60, len(full) - 5)], {
        "n_internal_signatures": 0, "both_flanks": False, "truncated": True}


def _internal_polya(chem, src, rng, cfg):
    p = rng.randrange(1, max(2, len(src.cdna)))
    cdna = src.cdna[:p] + "A" * rng.randint(18, 30) + src.cdna[p:]
    return chem.canonical_molecule(src.cb, src.umi, cdna), {"n_internal_signatures": 0, "both_flanks": True}


def _cb_corrupt(chem, src, rng, cfg):
    return chem.canonical_molecule(_corrupt(src.cb, rng, 2), src.umi, src.cdna), {
        "n_internal_signatures": 0, "both_flanks": True}


def _umi_corrupt(chem, src, rng, cfg):
    return chem.canonical_molecule(src.cb, _corrupt(src.umi, rng, 2), src.cdna), {
        "n_internal_signatures": 0, "both_flanks": True}


def _polyt_collapse(chem, src, rng, cfg):
    seq = (chem.r1_handle + src.cb + src.umi + "T" * rng.randint(3, 8) + "GN" + src.cdna + chem.tso_rc)
    return seq, {"n_internal_signatures": 0, "both_flanks": True}


def _short_insert(chem, src, rng, cfg):
    return chem.canonical_molecule(src.cb, src.umi, src.cdna[: rng.randint(1, 40)]), {
        "n_internal_signatures": 0, "both_flanks": True}


def _adapter_only(chem, src, rng, cfg):
    return chem.canonical_molecule(src.cb, src.umi, ""), {"n_internal_signatures": 0, "both_flanks": True}


def _reverse(chem, src, rng, cfg):
    # forced reverse handled by the emitter; forward build is canonical.
    return chem.canonical_molecule(src.cb, src.umi, src.cdna), {"n_internal_signatures": 0, "both_flanks": True,
                                                                "force_reverse": True}


def _illumina_control(chem, src, rng, cfg):
    # negative control: an Illumina P5/P7 final-library molecule — ONLY via --input-stage illumina_final_library
    P5, P7 = "AATGATACGGCGACCACCGAGATCTACAC", "CAAGCAGAAGACGGCATACGAGAT"
    tr1 = "ACACTCTTTCCCTACACGACGCTCTTCCGATCT"
    tr2 = "AGATCGGAAGAGCACACGTCTGAACTCCAGTCAC"
    seq = (P5 + tr1[len("ACAC"):] + src.cb + src.umi + src.cdna[:120] + tr2
           + "".join(rng.choice("ACGT") for _ in range(8)) + reverse_complement(P7))
    return seq, {"n_internal_signatures": 0, "both_flanks": False, "illumina": True}


FAILURE_MODES = {
    "clean": _clean, "tso_concatemer": _tso_concatemer, "fused_read": _fused_read,
    "missing_adapter1": _missing_adapter1, "missing_tso": _missing_tso, "trunc5": _trunc5,
    "trunc3": _trunc3, "internal_polya": _internal_polya, "cb_corrupt": _cb_corrupt,
    "umi_corrupt": _umi_corrupt, "polyt_collapse": _polyt_collapse, "short_insert": _short_insert,
    "adapter_only": _adapter_only, "reverse": _reverse, "illumina_control": _illumina_control,
}


# ---------------------------------------------------------------- config + sources


@dataclass
class SimConfig:
    fracs: dict = field(default_factory=dict)  # mode -> fraction (remainder = clean)
    orient_prob: float = 0.5  # P(canonical forward)
    input_stage: str = "amplified_cdna"
    pool: list = field(default_factory=list)  # for fused/concatemer second molecules

    def pick(self, rng: random.Random) -> SourceMol:
        return self.pool[rng.randrange(len(self.pool))]

    def draw_mode(self, rng: random.Random) -> str:
        r = rng.random()
        acc = 0.0
        for mode, f in self.fracs.items():
            acc += f
            if r < acc:
                return mode
        return "clean"


def synthetic_source(n: int, rng: random.Random, chem: NanoporeChem):
    """Generate purely synthetic (cb, umi, cDNA) molecules — no external data."""
    for i in range(n):
        cb = "".join(rng.choice("ACGT") for _ in range(chem.cb_len))
        umi = "".join(rng.choice("ACGT") for _ in range(chem.umi_len))
        cdna = "".join(rng.choice("ACGT") for _ in range(rng.randint(200, 2500)))
        yield SourceMol(f"synth_{i:07d}", cb, umi, cdna)


def normalize_source_seq(seq: str, chem: NanoporeChem) -> str | None:
    """Normalize a BAM/FASTA cDNA to canonical orientation and strip existing terminal 10x motifs
    exactly once (so the simulator does not append a second handle/TSO). Returns the clean cDNA, or
    None if the result is out of the accepted length range."""
    tso_rc, r1, tso = chem.tso_rc, chem.r1_handle, chem.tso
    if _find(seq[:80], ADAPTER2_MOTIF, 4) is not None or _find(seq[:80], tso_rc, 6) is not None:
        seq = reverse_complement(seq)  # adapter2 at 5' -> flip to adapter1-first
    if _startswith_fuzzy(seq, r1, 6):
        seq = seq[len(r1):]
    if _startswith_fuzzy(seq, tso, 6):
        seq = seq[len(tso):]
    if _endswith_fuzzy(seq, tso_rc, 6):
        seq = seq[: -len(tso_rc)]
    return seq if 150 <= len(seq) <= 6000 else None


def bam_source(bam_path: str, n: int, rng: random.Random, chem: NanoporeChem):
    """Reservoir-sample n molecules from a wf-single-cell BAM (bounded memory).

    The BAM (e.g. the GoT-Splice / Cell Stem Cell dataset) is a *biological-template source*: only the
    cDNA insert content is borrowed. The reads' observed artifact frequencies, full-length fraction,
    strand bias and barcode-recovery rate are NOT inherited — the baseline simulator re-applies its own
    generic, configurable orientation/failure/error model on top of the borrowed inserts.

    Normalizes each read to canonical orientation, strips existing terminal 10x motifs exactly once,
    preserves CB/UB tags as ground truth, rejects records with incompatible CB/UMI lengths.
    """
    import pysam

    reservoir: list[SourceMol] = []
    seen = 0
    bam = pysam.AlignmentFile(bam_path, "rb", check_sq=False)
    for r in bam:
        if r.is_secondary or r.is_supplementary or not r.query_sequence:
            continue
        if not r.has_tag("CB") or not r.has_tag("UB"):
            continue
        cb, umi = str(r.get_tag("CB")), str(r.get_tag("UB"))
        if len(cb) != chem.cb_len or len(umi) != chem.umi_len:
            continue
        cdna = normalize_source_seq(r.query_sequence, chem)
        if cdna is None:
            continue
        mol = SourceMol(r.query_name.split()[0], cb, umi, cdna)
        seen += 1
        if len(reservoir) < n:
            reservoir.append(mol)
        else:
            j = rng.randrange(seen)
            if j < n:
                reservoir[j] = mol
    return reservoir


def _find(seq, target, k):
    L = len(target)
    for i in range(0, len(seq) - L + 1):
        if sum(a != b for a, b in zip(seq[i:i + L], target)) <= k:
            return i
    return None


def _startswith_fuzzy(seq, target, k):
    return len(seq) >= len(target) and sum(a != b for a, b in zip(seq[: len(target)], target)) <= k


def _endswith_fuzzy(seq, target, k):
    return len(seq) >= len(target) and sum(a != b for a, b in zip(seq[-len(target):], target)) <= k


# ---------------------------------------------------------------- emit


def emit(chem, mols, cfg, err, rng, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    counts: dict[str, int] = {}
    # mtime=0 → byte-for-byte deterministic gzip (no embedded timestamp)
    with io.TextIOWrapper(
        gzip.GzipFile(os.path.join(out_dir, "reads.fastq.gz"), "wb", mtime=0), encoding="utf-8"
    ) as fq, open(os.path.join(out_dir, "labels.tsv"), "w") as lab:
        cols = ["read_id", "source_molecule_id", "raw_orientation", "true_cb", "true_umi", "cdna_len",
                "n_source_molecules", "n_internal_signatures", "both_flanks_present", "truncated",
                "failure_mode", "affected", "transcript_id", "seq_len"]
        lab.write("\t".join(cols) + "\n")
        for i, src in enumerate(mols):
            mode = "clean" if cfg.input_stage != "illumina_final_library" else "illumina_control"
            if cfg.input_stage != "illumina_final_library":
                mode = cfg.draw_mode(rng)
            fwd, extra = FAILURE_MODES[mode](chem, src, rng, cfg)
            # orientation
            force_rev = extra.get("force_reverse", False)
            forward = (not force_rev) and (rng.random() < cfg.orient_prob)
            oriented = fwd if forward else reverse_complement(fwd)
            seq = err.apply(oriented, rng)
            qual = err.quality(len(seq), rng)
            rid = f"nano_{i:07d}"
            fq.write(f"@{rid}\n{seq}\n+\n{qual}\n")
            counts[mode] = counts.get(mode, 0) + 1
            row = [rid, src.mol_id, "forward" if forward else "reverse", src.cb, src.umi,
                   str(len(src.cdna)), str(extra.get("n_source_molecules", 1)),
                   str(extra.get("n_internal_signatures", 0)), str(int(extra.get("both_flanks", True))),
                   str(int(extra.get("truncated", False))), mode, str(int(mode != "clean")),
                   src.transcript_id or "", str(len(seq))]
            lab.write("\t".join(row) + "\n")
    return counts


def simulate(spec_path, out_dir, *, n, seed, source, source_bam, fracs, orient_prob,
             err: OntErrorModel, input_stage):
    spec = load_spec(spec_path)
    chem = NanoporeChem.from_spec(spec)
    rng = random.Random(seed)
    if source_bam:
        mols = bam_source(source_bam, n, rng, chem)
    else:
        mols = list(synthetic_source(n, rng, chem))
    cfg = SimConfig(fracs=fracs, orient_prob=orient_prob, input_stage=input_stage, pool=mols)
    counts = emit(chem, mols, cfg, err, rng, out_dir)

    import hashlib
    spec_sha = hashlib.sha256(open(spec_path, "rb").read()).hexdigest()
    meta = {
        "simulator_version": VERSION, "spec_id": spec.spec_id, "spec_path": spec_path,
        "protocol_profile": spec.data.get("protocol_profile", "baseline_direct_ligation"),
        "spec_sha256": spec_sha, "seed": seed, "n": len(mols),
        "source": "bam" if source_bam else source, "source_bam": source_bam,
        # A BAM source supplies cDNA *content* only (biological template). Every artifact rate,
        # orientation balance and error parameter below is a generic, run-time default — the source
        # dataset's observed statistics are NOT inherited.
        "source_role": "biological_template_only" if source_bam else "synthetic",
        "input_stage": input_stage, "orientation_prob": orient_prob,
        "error_model": asdict(err), "artifact_fracs": fracs, "mode_counts": counts,
    }
    json.dump(meta, open(os.path.join(out_dir, "metadata.json"), "w"), indent=2)
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spec", default="spec/nanopore_10x_3p.json")
    ap.add_argument("--source", choices=["synthetic"], default="synthetic")
    ap.add_argument("--source-bam", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--orientation-prob", type=float, default=0.5)
    ap.add_argument("--input-stage", choices=["amplified_cdna", "illumina_final_library"],
                    default="amplified_cdna")
    # artifact fractions — one flag per failure mode
    for m in FAILURE_MODES:
        if m in ("clean", "illumina_control"):
            continue
        ap.add_argument(f"--{m.replace('_', '-')}-frac", type=float, default=0.0)
    # convenience aliases from the documented interface
    ap.add_argument("--concatemer-frac", type=float, default=None, help="alias for --tso-concatemer-frac")
    ap.add_argument("--truncate-frac", type=float, default=None, help="split across --trunc5-frac + --trunc3-frac")
    # error model
    ap.add_argument("--sub-rate", type=float, default=0.015)
    ap.add_argument("--ins-rate", type=float, default=0.010)
    ap.add_argument("--del-rate", type=float, default=0.010)
    a = ap.parse_args()
    fracs = {m: getattr(a, f"{m}_frac") for m in FAILURE_MODES if m not in ("clean", "illumina_control")}
    if a.concatemer_frac is not None:
        fracs["tso_concatemer"] = a.concatemer_frac
    if a.truncate_frac is not None:
        fracs["trunc5"] = fracs.get("trunc5", 0.0) + a.truncate_frac / 2
        fracs["trunc3"] = fracs.get("trunc3", 0.0) + a.truncate_frac / 2
    fracs = {m: f for m, f in fracs.items() if f > 0}
    err = OntErrorModel(sub_rate=a.sub_rate, ins_rate=a.ins_rate, del_rate=a.del_rate)
    meta = simulate(a.spec, a.out, n=a.n, seed=a.seed, source=a.source, source_bam=a.source_bam,
                    fracs=fracs, orient_prob=a.orientation_prob, err=err, input_stage=a.input_stage)
    print(f"[nanopore-sim] {meta['n']} reads → {a.out}  modes={meta['mode_counts']}")


if __name__ == "__main__":
    main()
