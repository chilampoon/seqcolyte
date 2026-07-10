# Seqcolyte

seqcolyte = sequencing acolyte

Give it a library-prep **protocol** and your **raw FASTQ**. It works out what the reads should look
like from the protocol, checks whether they do, and tells you — in plain terms — what went wrong beyond what cell ranger can tell.

Demos include **10x Chromium 3′ Gene Expression (v3/v3.1)** on Illumina and nanopore platforms.

---

## Three steps

```
  1. PROTOCOL  ──▶  2. EXPECTED STRUCTURE  ──▶  3. QC THE READS
   text/PDF/table      oligos · library build      run spec-derived checks,
                       · read structure            rank + diagnose failures
                          spec ▲                       ▲ raw FASTQ
                                                (control + simulated failures)
```

All three run end to end. Because the simulator emits ground-truth labels, the QC **scores itself** —
on the adapter-dimer test set it catches every injected failure (recall 1.0, precision ~0.91).

---

## Run it

```bash
pip install -e .
```

Only `seqcolyte fetch` (downloading the real 10x control) needs an extra tool, `seqkit`, on PATH
(`brew install seqkit`). Prefer conda? `conda env create -f environment.yml && pip install -e .`
also works and bundles `seqkit` for you.

Everything is one CLI — `seqcolyte <command>`, one command per step:

```bash
seqcolyte core                                   # build the qc-core Rust binary (needs cargo)

# protocol parsing  (input is a protocol document: PDF / text / Excel)
seqcolyte extract --doc protocol.pdf     # Claude Code reads it 🔶

# raw data QC
seqcolyte qc --r1 R1.fastq.gz --r2 R2.fastq.gz --json-out qc_report.json
        # --no-llm: fast, offline, deterministic report
```

---

## What's in the box

- **`spec/10x_3p_v3.json`** — the expected library: oligos (with `[CELL_BARCODE:16]` tokens), the
  step-by-step build, and the read structure. The single source of truth every step reads.
- **`extract/`** — the protocol reader: an LLM document extractor (PDF / text / Excel via docling + Claude,
  through your `claude` CLI — no API key). The checked-in **reference** spec is built separately by a
  deterministic HTML parser and used to cross-check extractions — reference only, not a user input.
- **`sim/`** — turns a clean control into labeled adapter-dimer / read-through failures, reproducibly.
- **`qc/`** — Step 3. The compute core is `qc/core/` — a streaming Rust CLI (`qc-core`) that profiles the
  FASTQ and runs the spec-derived checks (R1 length, whitelist rate, TSO-at-R2-start, adapter read-through,
  poly-G tail) plus the label eval in one pass. The Python around it shells out to that binary, then
  Claude ranks + diagnoses the findings with a spec-linked evidence chain and (given labels) scores itself.

```
extract/  spec/  sim/  qc/(+ core/ rust compute)  seqcolyte/(core)  protocols/  tests/
```

---

## Notes

- FASTQs, the whitelist, and generated labels are git-ignored — they regenerate from `make pipeline`.
- Deterministic where it counts: the spec and every simulated FASTQ are byte-identical across runs.
  The LLM-extracted spec (`*.pdf.json`) is the one exception — it's model output.
- Extensible: read structure is separated from platform specifics and failure modes are plugins, so
  a Nanopore modality slots in without an engine rewrite.
