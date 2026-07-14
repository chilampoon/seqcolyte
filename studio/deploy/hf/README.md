---
title: Seqcolyte Studio
emoji: 🧬
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
short_description: Protocol-aware sequencing-QC workspace + AI chat
---

# Seqcolyte Studio

**A protocol-aware sequencing-QC workspace.** Describe your library in plain
English, and the assistant infers the *expected* read/library structure, runs
spec-driven QC on your reads, explains what went wrong (and why) in chat with a
clickable evidence chain, then writes and applies in-silico fixes and re-scores
the cleaned data — all in one conversation.

Unlike a fixed QC report, every check here is derived from *your* assay's spec
(oligos, read structure, anchors), so it works across chemistries and platforms
— short-read 10x and Nanopore long-read included.

This Space runs the whole stack in one container: a Next.js UI over a Python +
Rust QC pipeline, with three worked examples baked in.

## Try it (no setup)

Three **Examples** are on the landing page:

| Example | What it shows |
| --- | --- |
| **10x Chromium 3′ — adapter dimers** | A finished walk-through: QC flags TSO-at-R2 read-through + poly-G tails, the assistant explains the root cause, then generates and **applies fixes** and re-scores — ending in a "QC report (after fixes)". Open the conversation, the reports, and the R1/R2 FASTQ in the Files panel. |
| **10x Chromium 3′ — clean library** | The healthy baseline — every check lands in range. Read it side-by-side with the problem run. |
| **sc-Nanopore 3′ — TSO concatemers (try it)** | A **half-built, ready-to-run** starter: the reads are already uploaded and the spec is built. Click **Confirm spec** to run QC live — it flags TSO concatemers (fused reads), which the **Computational fixes** panel then splits and re-scores. |

### The end-to-end flow, in 5 steps

1. **Describe the assay** — paste a plain-English description of the library
   (chemistry, read layout, adapters). The assistant extracts an expected spec.
2. **Review + Confirm the spec** — open **Extracted spec** in the viewer to check
   the inferred read/library structure, then click **Confirm spec**.
3. **Drop in FASTQ** — upload your reads (paired R1/R2 for short-read, a single
   long-read file for Nanopore). QC starts automatically once reads + spec are in.
4. **QC + diagnosis** — spec-driven checks run, then the assistant posts a ranked
   diagnosis: the verdict, the flagged findings, and the likely root cause.
5. **Computational fixes → Apply & re-QC** — for solvable findings the assistant
   authors focused fix scripts (in the Files panel). Tick the ones to apply; they
   compose into one cleaned dataset and a fresh **"QC report (after fixes)"**.

## Setup

Set these in **Settings → Variables and secrets**:

- `ANTHROPIC_API_KEY` *(secret, required)* — powers the AI diagnosis, chat, and
  fix-script generation (billed per token; set a spend limit on the key).
- `STUDIO_AUTH_USER` / `STUDIO_AUTH_PASS` *(secrets, recommended)* — a basic-auth
  gate so only people you share the password with can run it.

Then open one of the **Examples** above, or start a **New project** and follow the
5-step flow with your own description + FASTQ.

## Roadmap / next steps

- **Sandboxed remediation** — run the AI-authored fix scripts in an isolated
  sandbox (currently gated behind basic-auth).
- **More chemistries & platforms** — broaden beyond 10x 3′ and Nanopore to other
  single-cell, spatial, and bulk protocols.
- **Richer custom-adapter checks** — deeper per-oligo QC and adapter-contamination
  profiling driven directly from the spec.
- **Persistent per-visitor storage** — save projects, runs, and history per user
  across sessions.
