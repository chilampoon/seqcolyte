"""``seqcolyte`` — one CLI for the whole protocol-aware QC workflow.

Wraps the per-module entry points (extract / sim / qc + the Rust core build) behind clean,
step-oriented subcommands, so you don't have to remember the ``python -m …`` / ``make`` spells:

    seqcolyte extract  --doc protocol.pdf --eval    # 1+2  protocol PDF -> spec  (via Claude Code)
    seqcolyte extract                               # 1+2  deterministic build from the curated HTML
    seqcolyte fetch                                 #      download the barcode whitelist + 10x control
    seqcolyte simulate                              #      inject labeled failure modes into the control
    seqcolyte qc --r1 R1.fq.gz --r2 R2.fq.gz        # 3    QC the reads + Claude diagnosis
    seqcolyte core                                  #      build the qc-core Rust compute binary
    seqcolyte pipeline                              #      run 1 -> 2 -> 3 end to end

Two of these call Claude Code (your authenticated ``claude`` CLI): ``extract --doc`` reads the
protocol, and ``qc`` (without ``--no-llm``) ranks + diagnoses the findings.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SPEC_ID_DEFAULT = "10x_3p_v3"
SPEC_DEFAULT = REPO / "spec" / f"{SPEC_ID_DEFAULT}.json"
WL_DEFAULT = REPO / "whitelists" / "3M-february-2018.txt.gz"
CONFIG_DEFAULT = REPO / "sim" / "configs" / "adapter_dimer_f30.yaml"
LABELS_DEFAULT = REPO / "sim" / "labels" / "adapter_dimer_f30.tsv"
SIM_R1 = REPO / "data" / "sim" / "adapter_dimer_f30" / "R1.fastq.gz"
SIM_R2 = REPO / "data" / "sim" / "adapter_dimer_f30" / "R2.fastq.gz"
MODEL_DEFAULT = "claude-opus-4-8"


# --------------------------------------------------------------------------------------
# step handlers — each returns a process-style int return code (0 == ok)
# --------------------------------------------------------------------------------------

def _extract(*, doc, spec_id=SPEC_ID_DEFAULT, do_eval=False, model=MODEL_DEFAULT) -> int:
    from extract.cli import main as extract_main
    argv = ["from-doc", "--doc", doc, "--spec", spec_id, "--model", model]
    if do_eval:
        argv.append("--eval")
    return extract_main(argv) or 0


def _fetch(*, whitelist=True, control=True) -> int:
    from sim.get_data import main as getdata_main
    rc = 0
    if whitelist:
        rc = getdata_main(["whitelist"]) or rc
    if control:
        rc = getdata_main(["data"]) or rc
    return rc


def _simulate(*, config=str(CONFIG_DEFAULT), check=False) -> int:
    if check:  # gate: don't derive failures from a control that failed its read-structure check
        from sim.sanity import main as sanity_main
        rc = sanity_main([]) or 0
        if rc:
            print("sanity check failed — control is not a clean library; skipping simulate", file=sys.stderr)
            return rc
    from sim.cli import main as sim_main
    return sim_main(["run", "--config", config]) or 0


def _qc(*, r1, r2, spec=str(SPEC_DEFAULT), whitelist=None, labels=None, no_llm=False,
        model=MODEL_DEFAULT, max_reads=None, json_out=None) -> int:
    from qc.cli import main as qc_main
    argv = ["run", "--spec", spec, "--r1", r1, "--r2", r2, "--model", model]
    wl = whitelist if whitelist is not None else (str(WL_DEFAULT) if WL_DEFAULT.exists() else None)
    if wl:
        argv += ["--whitelist", wl]
    if labels:
        argv += ["--labels", labels]
    if no_llm:
        argv.append("--no-llm")
    if max_reads is not None:
        argv += ["--max-reads", str(max_reads)]
    if json_out:
        argv += ["--json-out", json_out]
    return qc_main(argv) or 0


def _core() -> int:
    cargo = shutil.which("cargo")
    if not cargo:
        print("error: cargo not found on PATH — install Rust from https://rustup.rs", file=sys.stderr)
        return 2
    manifest = REPO / "qc" / "core" / "Cargo.toml"
    print("building qc-core (release)…", file=sys.stderr)
    return subprocess.run([cargo, "build", "--release", "--manifest-path", str(manifest)]).returncode


def _pipeline(*, doc=None, no_llm=False) -> int:
    print("== [0/4] build qc-core ==", file=sys.stderr)
    if _core():
        return 1
    if doc:
        print("== [1/4] protocol document -> spec ==", file=sys.stderr)
        if _extract(doc=doc):  # no --eval: an arbitrary protocol lacks a co-located groundtruth
            return 1
        spec = str(REPO / "spec" / f"{SPEC_ID_DEFAULT}.pdf.json")
    else:
        spec = str(SPEC_DEFAULT)
        if not Path(spec).exists():
            print(f"error: reference spec {spec} not found — pass --doc <document> to extract one",
                  file=sys.stderr)
            return 1
        print(f"== [1/4] using reference spec {Path(spec).name} (pass --doc to extract from a protocol) ==",
              file=sys.stderr)
    print("== [2/4] fetch whitelist + control ==", file=sys.stderr)
    if _fetch():
        return 1
    print("== [3/4] simulate labeled failures ==", file=sys.stderr)
    if _simulate(check=True):
        return 1
    print("== [4/4] QC the reads ==", file=sys.stderr)
    return _qc(r1=str(SIM_R1), r2=str(SIM_R2), spec=spec, labels=str(LABELS_DEFAULT), no_llm=no_llm)


# --------------------------------------------------------------------------------------
# argument parsing
# --------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="seqcolyte",
        description="Protocol-aware sequencing QC — one CLI for the whole workflow (extract -> simulate -> qc).",
    )
    sub = ap.add_subparsers(dest="command", required=True, metavar="<command>")

    e = sub.add_parser("extract", help="protocol document (PDF / text / Excel) -> spec (step 1+2)")
    e.add_argument("--doc", required=True, help="protocol document — PDF, text, or Excel — read by Claude Code")
    e.add_argument("--eval", action="store_true", help="score the extraction against a co-located groundtruth")
    e.add_argument("--spec", default=SPEC_ID_DEFAULT, dest="spec_id", help="spec id (default: %(default)s)")
    e.add_argument("--model", default=MODEL_DEFAULT)
    e.set_defaults(func=lambda a: _extract(doc=a.doc, spec_id=a.spec_id, do_eval=a.eval, model=a.model))

    f = sub.add_parser("fetch", help="download the barcode whitelist + real 10x control FASTQ")
    fg = f.add_mutually_exclusive_group()
    fg.add_argument("--whitelist-only", action="store_true", help="fetch only the whitelist")
    fg.add_argument("--control-only", action="store_true", help="fetch only the control FASTQ")
    f.set_defaults(func=lambda a: _fetch(whitelist=not a.control_only, control=not a.whitelist_only))

    s = sub.add_parser("simulate", help="inject labeled failure modes into the control")
    s.add_argument("--config", default=str(CONFIG_DEFAULT), help="failure-mode YAML (default: adapter_dimer_f30)")
    s.add_argument("--check", action="store_true", help="run the read-structure sanity check first")
    s.set_defaults(func=lambda a: _simulate(config=a.config, check=a.check))

    q = sub.add_parser("qc", help="QC a FASTQ pair against a spec + diagnose (step 3)")
    q.add_argument("--r1", required=True, help="R1 FASTQ (.fastq.gz)")
    q.add_argument("--r2", required=True, help="R2 FASTQ (.fastq.gz)")
    q.add_argument("--spec", default=str(SPEC_DEFAULT), help="expected-structure spec (default: %(default)s)")
    q.add_argument("--whitelist", default=None, help="barcode whitelist (default: the 3M list if present)")
    q.add_argument("--labels", default=None, help="ground-truth labels TSV -> enables the self-scoring eval")
    q.add_argument("--no-llm", action="store_true", dest="no_llm", help="skip Claude ranking (deterministic report)")
    q.add_argument("--max-reads", type=int, default=None, dest="max_reads")
    q.add_argument("--json-out", default=None, dest="json_out")
    q.add_argument("--model", default=MODEL_DEFAULT)
    q.set_defaults(func=lambda a: _qc(r1=a.r1, r2=a.r2, spec=a.spec, whitelist=a.whitelist, labels=a.labels,
                                      no_llm=a.no_llm, model=a.model, max_reads=a.max_reads, json_out=a.json_out))

    c = sub.add_parser("core", help="build the qc-core Rust compute binary (needs cargo)")
    c.set_defaults(func=lambda a: _core())

    p = sub.add_parser("pipeline", help="run the whole chain end to end (1 -> 2 -> 3)")
    p.add_argument("--doc", help="use Claude PDF extraction for step 1+2 (else the deterministic HTML build)")
    p.add_argument("--no-llm", action="store_true", dest="no_llm", help="deterministic QC in step 3")
    p.set_defaults(func=lambda a: _pipeline(doc=a.doc, no_llm=a.no_llm))

    args = ap.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
