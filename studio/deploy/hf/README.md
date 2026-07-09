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

A protocol-aware sequencing-QC workspace: load a protocol, run QC on 10x reads,
inspect findings with a clickable evidence chain back to the expected read
structure, and ask a grounded assistant about the results.

This Space runs the whole thing in one container — a Next.js UI over a Python +
Rust QC pipeline, with the demo dataset (a labeled adapter-dimer simulation)
baked in.

## Setup

Set these in **Settings → Variables and secrets**:

- `ANTHROPIC_API_KEY` *(secret, required)* — powers the AI diagnosis + chat
  (billed per token; set a spend limit on the key).
- `STUDIO_AUTH_USER` / `STUDIO_AUTH_PASS` *(secrets, recommended)* — a basic-auth
  gate so only people you share the password with can run it.

Then open a project, pick the **adapter-dimer simulation** reads, and click **Run QC**.
