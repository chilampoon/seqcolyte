# syntax=docker/dockerfile:1
#
# Seqcolyte Studio — Hugging Face Docker Space image.
# Differences from studio/Dockerfile: runs as UID 1000 (HF requirement), listens
# on 7860, and downloads the barcode whitelist at build time (so no Git LFS).
# Build context MUST be the seqcolyte repo root.

# ---- Stage 1: build the Rust QC compute core for Linux ----
FROM rust:1-bookworm AS rust-build
WORKDIR /build
COPY qc/core/Cargo.toml qc/core/Cargo.lock ./qc/core/
COPY qc/core/src ./qc/core/src
RUN cargo build --release --manifest-path qc/core/Cargo.toml

# ---- Stage 2: build the Next.js app (standalone output) ----
FROM node:22-bookworm-slim AS web-build
WORKDIR /app
COPY studio/package.json studio/package-lock.json ./
RUN npm ci
COPY studio/ ./
RUN npm run build

# ---- Stage 3: runtime (runs as UID 1000, per HF Spaces) ----
FROM node:22-bookworm-slim AS runtime

# System deps (as root): Python + the Claude CLI + wget for the whitelist.
# docling's heavy ML stack is omitted; pypdfium2 gives a lightweight PDF text layer so uploaded
# protocol PDFs still extract (extract/pdf_text.py falls back to it when docling is absent).
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-pip ca-certificates git \
 && rm -rf /var/lib/apt/lists/* \
 && npm install -g @anthropic-ai/claude-code \
 && pip3 install --no-cache-dir --break-system-packages \
      numpy pyyaml jsonschema beautifulsoup4 lxml pypdfium2

# HF Spaces require UID 1000 at runtime. The node base image already provides the
# `node` user at UID 1000, so reuse it (creating a new UID-1000 user would collide).
RUN mkdir -p /home/node/repo /home/node/app /home/node/data/projects \
 && chown -R node:node /home/node
USER node
ENV HOME=/home/node \
    PATH=/home/node/.local/bin:$PATH \
    NODE_ENV=production \
    PORT=7860 \
    HOSTNAME=0.0.0.0 \
    SEQCOLYTE_PYTHON=python3 \
    SEQCOLYTE_REPO=/home/node/repo \
    SEQCOLYTE_QC_BIN=/home/node/repo/qc/core/target/release/qc-core \
    SEQCOLYTE_STUDIO_DATA=/home/node/data/projects

# Pipeline: Python packages + spec + demo data + the Linux qc-core binary.
WORKDIR /home/node/repo
COPY --chown=node qc/ ./qc/
COPY --chown=node seqcolyte/ ./seqcolyte/
COPY --chown=node sim/ ./sim/
COPY --chown=node extract/ ./extract/
COPY --chown=node spec/ ./spec/
COPY --chown=node data/sim/adapter_dimer_f30/ ./data/sim/adapter_dimer_f30/
COPY --chown=node data/raw/pbmc_1k_v3_sub_R1.fastq.gz data/raw/pbmc_1k_v3_sub_R2.fastq.gz ./data/raw/
COPY --chown=node --from=rust-build /build/qc/core/target/release/qc-core ./qc/core/target/release/qc-core
# Whitelist committed to the Space via Xet (a build-time download from GitHub raw
# was rate-limited/blocked on HF's build network).
COPY --chown=node whitelists/3M-february-2018.txt.gz ./whitelists/3M-february-2018.txt.gz

# Next.js standalone server.
WORKDIR /home/node/app
COPY --chown=node --from=web-build /app/.next/standalone ./
COPY --chown=node --from=web-build /app/.next/static ./.next/static
COPY --chown=node --from=web-build /app/public ./public

# Seed a pre-computed demo project into the (ephemeral) store so the Space is
# populated on every start — a deterministic adapter-dimer QC run.
COPY --chown=node studio/deploy/hf/demo-seed/ /home/node/data/projects/

EXPOSE 7860
CMD ["node", "server.js"]
