# Seqcolyte

**A protocol-aware sequencing diagnostic agent.** Give it a sequencing protocol + raw FASTQ; it
extracts the expected library/read structure, runs deterministic QC checks, and reports ranked,
severity-scored failures with an evidence chain.

> **Day 1 scope (this repo state):** the substrate only — a scaffold, a machine-checked
> **read-structure spec**, a real **known-good FASTQ**, and a **failure simulator** that injects a
> labeled adapter-dimer artifact. **Not yet built** (Day 2+): the QC check tools, the Claude
> orchestration/agent loop, ranking/severity scoring, and any web UI.

**Day-1 gate:** a correct structured spec for 10x 3' v3 + a known-good FASTQ + a simulated
adapter-dimer FASTQ derived from it, with per-read ground-truth labels. ✅

---

## Quickstart

```bash
make install          # conda env (bioconda: pysam, seqkit, seqtk, …) + pip install -e .
conda activate seqcolyte

make spec             # parse protocols/10xChromium3.html -> spec/tenx_3p_v3.json (offline, reproducible)
make test             # 34 unit tests, no network / no big data

# network + heavy (≈5.5 GB one-time download, subsampled to ~40k pairs then deleted):
make whitelist        # 3M-february-2018 cell-barcode whitelist (+ computed md5)
make data             # pbmc_1k_v3 -> data/raw/pbmc_1k_v3_sub_R{1,2}.fastq.gz
make sanity           # prove the control is clean (R1==28, whitelist hit-rate ≥0.85)
make sim              # inject adapter dimers -> data/sim/adapter_dimer_f30/ + labels
make summary          # print the Day-1 gate summary

# or the whole chain:
make pipeline
```

FASTQs and whitelists are **git-ignored**; the spec and labels are committed.

---

## What's here

```
extract/     protocol HTML -> consolidated spec (parse + cross-check + canonical JSON)
spec/        tenx_3p_v3.json  — the single source of truth (committed, byte-reproducible)
sim/         failure simulator, get_data, sanity checks, ground-truth labels
seqcolyte/   shared core: dna (revcomp), spec loader/model, FASTQ I/O
protocols/   10xChromium3.html (parsed source) + provenance notes
tests/       fixture-only unit tests
```

### The spec (`spec/tenx_3p_v3.json`)

One self-contained, demo-friendly document aligned with the prior groundtruth format:

- **`oligos[]`** — parts list with placeholder tokens (`[CELL_BARCODE:16]`, `[UMI:12]`,
  `[SAMPLE_INDEX:8]`), `components`, honest `provenance` (`document` vs `reagent`), and an
  `evidence[]` chain (source-doc locator + `verified_against` URLs).
- **`final_library`** — annotated sequence + `<p5><cbc><umi>…` tagged strands (renders as the
  library diagram) + scoring placeholders.
- **`read_structure.reads[]`** — per-read (R1/R2/I1) ordered segments the simulator + QC consume,
  plus R2's `readthrough_chain` (the recipe a short-insert read follows).
- **`whitelists`**, **`platform_params`**, **`source_docs`**, **`build`** (sha256, deterministic).

Built by **parsing `protocols/10xChromium3.html`** and **cross-checking every sequence** against
independently-verified authoritative values (`extract/verified_constants.py`); the build fails
loudly on any mismatch. `make spec` regenerates byte-identical output — `python -m extract check`
is a drift guard. See [`protocols/tenx_3p_v3.provenance.md`](protocols/tenx_3p_v3.provenance.md).

Target chemistry: **10x Chromium 3' Gene Expression v3/v3.1** — R1 = 16 bp cell barcode + 12 bp UMI
(28 bp); R2 = cDNA; i7 8 bp single index; whitelist `3M-february-2018`.

### The failure simulator (`sim/`)

Config-driven and reproducible from one YAML
([`sim/configs/adapter_dimer_f30.yaml`](sim/configs/adapter_dimer_f30.yaml)). It rewrites **only R2**
for a fraction of pairs (default 30% = ~20% read-through + ~10% pure dimer); **R1 is left
byte-identical** (a 28 bp R1 is exactly CB+UMI, so the library still demultiplexes). Both failure
types lead with the **TSO** (built from the spec's constants):

- **read-through** — `TSO + insert + poly(A) + revcomp(UMI) + revcomp(CB) + revcomp(R1 primer) +
  revcomp(P5)`, fit to the read length (→ adapter read-through + reverse-complemented barcode visible).
- **pure dimer** — `TSO + short poly(A) + poly-G` no-signal tail (the classic empty two-color product).

`revcomp(CB/UMI)` use *that pair's* barcode/UMI (never random); synthesized bases get a spuriously
high quality so a naive quality filter can't catch them. Deterministic per read via
`SeedSequence([seed, pair_index])` → byte-identical re-runs. Outputs:
`data/sim/adapter_dimer_f30/{R1,R2}.fastq.gz`, `sim/labels/adapter_dimer_f30.tsv` (per-read
`{clean|readthrough|pure_dimer}` + construct recipe), and a `run.json` manifest.

### Regenerating everything from config

`make sim` (or `python -m sim run --config <yaml>`) regenerates the failure FASTQs + labels
deterministically from the clean control + the config. Change `seed`, `affected_fraction`,
`dimer_fraction`, insert/poly(A) lengths, or `quality` in the YAML and re-run.

---

## Extensibility (designed in)

A second modality drops in **without refactor**: the spec separates platform-invariant read
structure (barcode/UMI/insert + named constants) from `platform`/`platform_params`, and failure
modes are registry plugins sharing `revcomp` + the spec's constants. E.g. a 10x 3' **Nanopore** spec
(`platform: nanopore`, `dark_base: null`) with a `tso_concatemer` failure mode = one new `sim/modes/`
file; the engine is untouched.

## Environment

Python 3.11+, `pysam`, `numpy`, `pyyaml`, `jsonschema`, `beautifulsoup4`/`lxml`; `seqkit` + `seqtk`
on `PATH` (discovered via `shutil.which`, so install method is up to you). `make install` pins them
via conda/bioconda (`environment.yml`).
