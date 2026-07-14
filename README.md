# Seqcolyte

seqcolyte = sequencing acolyte

Give it a library-prep **protocol** (or just a plain-English description) and your **raw FASTQ**. It
works out what the reads *should* look like, checks whether they do, and tells you — in plain terms —
what went wrong, beyond what Cell Ranger can tell you.

---

## What it does

Most QC tools run a fixed battery of checks. Seqcolyte instead **derives the checks from your assay**:
it infers the expected read/library structure (oligos, barcode/UMI layout, adapters, anchors) from a
protocol or description, then runs spec-driven QC against *that*. So the same engine works across
chemistries and platforms — short-read 10x and Nanopore long-read included.

The loop, end to end:

1. **Describe the assay** — a protocol PDF or a plain-English blurb → an inferred **spec** (expected
   read/library structure).
2. **QC the reads** — a Python + Rust core checks the FASTQ against the spec (barcode/UMI layout,
   whitelist hit-rate, adapter read-through, TSO/anchor placement, poly-G tails, long-read concatemers…).
3. **Diagnose** — a grounded assistant ranks the findings, explains the likely **root cause**, and
   points each flag back to the expected structure.
4. **Fix + re-score** — for solvable findings it authors focused in-silico **fix scripts**, applies the
   ones you pick, and re-runs QC on the cleaned data for a before/after comparison.

## Two ways to use it

### Seqcolyte Studio (UI)

A protocol-aware QC **workspace** that runs the whole loop as a conversation — describe the assay,
review + confirm the inferred spec, drop in FASTQ, read the diagnosis in chat, then apply computational
fixes and re-QC. Deployed on Hugging Face:
**[🤗 seqmachines/seqcolyte](https://huggingface.co/spaces/seqmachines/seqcolyte)**.

Three worked **Examples** are on the landing page — start there:

- **10x Chromium 3′ — clean library** — the healthy baseline; every check lands in range.
- **10x Chromium 3′ — adapter dimers** — a full walk-through: QC flags the TSO-at-R2 read-through, the
  assistant explains it, then **generates + applies fixes** and re-scores.
- **sc-Nanopore 3′ — TSO concatemers (try it)** — a half-built starter with reads already uploaded and
  the spec built: click **Confirm spec** to run it live and split the concatemers.

Run the Studio locally from `studio/` (`npm install && npm run dev`); see `studio/deploy/hf/` for the
container + deploy.

### CLI

```bash
pip install -e .
```

Only `seqcolyte fetch` (downloading the real 10x control) needs an extra tool, `seqkit`.

```bash
seqcolyte core                                   # build the qc-core Rust binary (needs cargo)

# protocol parsing  (input is a protocol document: PDF / text / Excel)
seqcolyte extract --doc protocol.pdf     # Claude Code reads it 🔶

# raw data QC
seqcolyte qc --r1 R1.fastq.gz --r2 R2.fastq.gz --json-out qc_report.json
        # --no-llm: fast, offline, deterministic report

# Nanopore long-read QC (single FASTQ)
python -m qc.nanopore --spec spec.json --reads reads.fastq.gz --json-out qc_report.json
```

## Next steps / roadmap

- **Sandboxed remediation** — run the AI-authored fix scripts in an isolated sandbox.
- **More chemistries & platforms** — broaden beyond 10x 3′ and Nanopore to other single-cell, spatial,
  and bulk protocols.
- **Richer custom-adapter checks** — deeper per-oligo QC and adapter-contamination profiling driven
  straight from the spec.
- **Persistent per-visitor storage** — save projects, runs, and history across sessions in Studio.
