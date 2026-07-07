# Seqcolyte

seqcolyte = sequencing acolyte

Give it a library-prep **protocol** and your **raw FASTQ**. It works out what the reads should look
like from the protocol, checks whether they do, and tells you — in plain terms — what went wrong.

Targets **10x Chromium 3′ Gene Expression (v3/v3.1)** on Illumina today; Nanopore is next.

---

## Three steps

```
  1. PROTOCOL  ──▶  2. EXPECTED STRUCTURE  ──▶  3. QC THE READS
   10x PDF          oligos · library build      run spec-derived checks,
                    · read structure            rank + diagnose failures
                          spec ▲                       ▲ raw FASTQ
                                                (control + simulated failures)
```

All three run end to end. Because the simulator emits ground-truth labels, the QC **scores itself** —
on the adapter-dimer test set it catches every injected failure (recall 1.0, precision ~0.91).

---

## Run it

```bash
make install            # one-time: conda env + package  (or do it by hand, see below)
conda activate seqcolyte
```

The interface is three commands — one per step:

```bash
# 1+2  protocol -> spec (expected structure)
python -m extract build                              # from the curated HTML (deterministic)
python -m extract from-doc --doc protocol.pdf --eval # from any PDF (Claude reads it)

# make test data (a real 10x control + injected adapter-dimer failures with labels)
python -m sim.get_data data && python -m sim run --config sim/configs/adapter_dimer_f30.yaml

# 3  QC a FASTQ pair against the spec
python -m qc run --spec spec/tenx_3p_v3.json \
  --r1 R1.fastq.gz --r2 R2.fastq.gz \
  --whitelist whitelists/3M-february-2018.txt.gz \
  --labels labels.tsv        # optional: enables the self-scoring eval
                             # --no-llm: fast, offline, deterministic report
```

`make pipeline` runs that whole chain in one go; `make test` runs the 47 unit tests. Make is just a
shortcut — everything is a plain `python -m …` command.

---

## What's in the box

- **`spec/tenx_3p_v3.json`** — the expected library: oligos (with `[CELL_BARCODE:16]` tokens), the
  step-by-step build, and the read structure. The single source of truth every step reads.
- **`extract/`** — two paths to that spec: a deterministic HTML parser (cross-checked, byte-reproducible)
  and an LLM PDF extractor (docling + Claude, run through your `claude` CLI — no API key).
- **`sim/`** — turns a clean control into labeled adapter-dimer / read-through failures, reproducibly.
- **`qc/`** — Step 3: deterministic checks derived from the spec (R1 length, whitelist rate, TSO-at-R2-start,
  adapter read-through, poly-G tail), then Claude ranks + diagnoses them with an evidence chain.

```
extract/  spec/  sim/  qc/  seqcolyte/(core)  protocols/  tests/
```

---

## Notes

- FASTQs, the whitelist, and generated labels are git-ignored — they regenerate from `make pipeline`.
- Deterministic where it counts: the spec and every simulated FASTQ are byte-identical across runs.
  The LLM-extracted spec (`*.pdf.json`) is the one exception — it's model output.
- Extensible: read structure is separated from platform specifics and failure modes are plugins, so
  a Nanopore modality slots in without an engine rewrite.
