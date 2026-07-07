# Seqcolyte

**A protocol-aware QC agent for single-cell sequencing.**

Point it at a library-prep **protocol** and your **raw FASTQ**. It figures out what the reads are
*supposed* to look like from the protocol, then checks whether they actually do — and tells you, in
plain terms, what went wrong and why.

Today it targets **10x Chromium 3′ Gene Expression (v3/v3.1)** on Illumina. Oxford Nanopore is a
planned second modality.

---

## The idea, in three steps

```
   1. PROTOCOL                2. EXPECTED STRUCTURE            3. QC THE READS
  ┌──────────────┐          ┌───────────────────────┐       ┌──────────────────────┐
  │  10x PDF     │  ──────▶ │  oligos               │ ────▶ │  decide which checks  │
  │  (or the     │          │  library generation   │       │  to run, run them,    │
  │   scg HTML)  │          │  library sequencing   │       │  rank + diagnose the  │
  │              │          │  (how R1/R2/I1 read)  │       │  failures             │
  └──────────────┘          └───────────────────────┘       └──────────────────────┘
        ✅                          ✅                                ✅
                                                                        ▲
                                    raw FASTQ ─────────────────────────┘
                                (real control + simulated failures)
```

**What's built:**

| Step | Piece | Status |
|------|-------|:------:|
| 1 | Ingest a protocol PDF | ✅ |
| 2 | Extract **oligos** | ✅ |
| 2 | Extract **step-by-step library generation** (the 8-step build) | ✅ |
| 2 | Extract **library sequencing** (R1 = barcode+UMI, R2 = cDNA, I1 = index) | ✅ |
| — | **Simulate raw data** (clean control + labeled adapter-dimer failures) | ✅ |
| 3 | **Decide & run QC checks**, rank + diagnose failures | ✅ |

All three steps run end to end. Because the simulator emits ground-truth labels, the QC even
**scores itself** — on the adapter-dimer test set it catches every injected failure
(recall 1.0, precision ~0.91). Oxford Nanopore is the next modality; only new spec fields + a
failure-mode plugin are needed, not an engine rewrite.

---

## Quickstart

```bash
make install          # creates the conda env (bioinformatics tools + deps)
conda activate seqcolyte
make test             # 39 unit tests, offline, ~1s
```

**Build the expected-structure spec** (two ways):

```bash
# a) deterministic — parse the curated scg_lib_structs HTML (byte-reproducible)
make spec                                            # -> spec/tenx_3p_v3.json

# b) from a real protocol PDF — Claude reads it and fills the same schema
python -m extract from-doc --doc your_protocol.pdf --spec tenx_3p_v3 --eval
                                                     # -> spec/tenx_3p_v3.pdf.json
```

**Make the test data, then QC it (the whole chain):**

```bash
make pipeline         # control FASTQ -> subsample -> sanity -> simulate failures -> QC -> summary
```

That downloads a real 10x dataset (~5.5 GB, once), subsamples it to ~40k read pairs, verifies it's
genuinely clean, injects adapter-dimer failures with per-read ground-truth labels, and QCs the
result.

**Run QC on any FASTQ pair yourself:**

```bash
python -m qc run \
  --spec spec/tenx_3p_v3.json \
  --r1 R1.fastq.gz --r2 R2.fastq.gz \
  --whitelist whitelists/3M-february-2018.txt.gz \
  --labels labels.tsv        # optional — enables the self-scoring eval
                             # add --no-llm for a fast, offline, deterministic report
```

---

## The pieces

**The spec — `spec/tenx_3p_v3.json`.** One JSON file that captures the expected library: the
**oligos** (with placeholder tokens like `[CELL_BARCODE:16]`), the **final library structure**
(renders as the classic library diagram), and the **read structure** (what R1/R2/I1 should contain).
Every sequence carries an honest source (`document` vs `reagent`) and an evidence link. It's the
single source of truth everything else reads.

**Two extractors, one schema.**
- *Deterministic* (`make spec`) parses the checked-in `protocols/10xChromium3.html` and cross-checks
  every sequence against independently-verified values — the build fails loudly if anything drifts.
- *LLM* (`extract from-doc`) reads an arbitrary **PDF** with **docling** (tables + text layer) and
  has Claude fill the same schema. It runs through your authenticated `claude` CLI — no API key.
  On the 10x v3 PDF it currently gets oligo recall ~0.73 and an exact match on the library structure,
  with the deterministic constants as a guardrail. (This is the seed of the Step-3 agent.)

**The simulator (`sim/`).** Turns the clean control into labeled failures, reproducibly from one
config. For each failure it rewrites only R2 (leaving R1 untouched so the library still
demultiplexes) into either a **read-through** (`TSO + short insert + poly(A) + …adapter`) or a
**pure adapter-dimer** (`TSO + poly(A) + poly-G` tail). Output: `data/sim/…/{R1,R2}.fastq.gz`, a
labels TSV (`clean` / `readthrough` / `pure_dimer` per read), and a run manifest. Re-running gives
byte-identical output.

**The QC — `qc/` (Step 3).** Reads the spec + a FASTQ pair, runs a **deterministic check toolbox**
whose expectations come from the spec (R1 length, whitelist hit-rate, TSO-at-R2-start, adapter
read-through, poly-G tail), then Claude **ranks the findings and writes a plain-language diagnosis**
with an evidence chain back to the spec — the "hybrid": reproducible checks, an agent deciding what
matters. Every finding says what it means and links to the spec fact it violates. With `--labels`
it scores its own read-level detection against the ground truth. `--no-llm` gives a fast,
fully-deterministic report (the checks and eval never need the model).

---

## Project layout

```
extract/      Steps 1-2: protocol -> spec.  HTML parser (deterministic) + PDF/LLM extractor
spec/         tenx_3p_v3.json — the expected-structure spec (committed)
sim/          failure simulator, data download, sanity checks, ground-truth labels
qc/           Step 3: checks + LLM ranking/diagnosis + label-based self-eval
seqcolyte/    shared core: DNA utils, spec loader, FASTQ I/O
protocols/    the source documents + provenance notes
tests/        47 offline unit tests
```

---

## Good to know

- **Big files stay out of git.** FASTQs, the barcode whitelist, and generated labels are
  `.gitignore`d — they all regenerate from `make pipeline` + the committed config.
- **Reproducible by design.** The deterministic spec and every simulated FASTQ are byte-identical
  across runs (fixed seeds, no timestamps). The LLM-extracted spec (`*.pdf.json`) is the one
  exception — it's model output, kept separate.
- **Environment.** Python 3.11+ via conda (`environment.yml`); needs `seqkit`/`seqtk` on `PATH`.
  The PDF extractor pulls in `docling` (heavy — torch); it's optional and only used by `from-doc`.
- **Built for a second modality.** The spec separates platform-invariant read structure from
  platform specifics, and failure modes are plugins — so 10x-on-Nanopore (with a TSO-concatemer
  failure) slots in without a rewrite.
