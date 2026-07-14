# Seqcolyte

seqcolyte = sequencing acolyte

**Seqcolyte Studio**: https://huggingface.co/spaces/seqmachines/seqcolyte

Please try the 'sc-Nanopore 3′ — TSO concatemers (try it)' example!

## What it does

Most quality control (QC) tools run a fixed battery of checks. Seqcolyte instead **derives the checks from your assay**:
it infers the expected read/library structure (oligos, barcode/UMI layout, adapters, anchors) from a
protocol or description, then runs spec-driven QC against *that*. So the same engine works across
chemistries and platforms for short and long reads.

The agentic loop, end to end:

1. **Describe the assay**
2. **QC the reads**
3. **Diagnose**
4. **Fix + re-score**

## Next steps

- **Collect more technologies**
    - More modalities: spatial, RNA modification, ...
    - More platforms: ONT, PacBio, Ultima Genomics, ...
- **Collect more issues from failure sequencing runs**
- Agent knowledgebase building with these technologies and issues
- More benchmarks and engineering to increase agent accuracy

---

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
