# syntax=docker/dockerfile:1
#
# Seqcolyte Studio — self-hosted container image.
# Build context MUST be the seqcolyte repo root (the app shells out to the
# sibling Python/Rust pipeline), e.g.:  docker build -f studio/Dockerfile .
#
# Bundles: the Next.js app (standalone) + Python pipeline + a Linux-built qc-core
# + the Claude CLI + the demo data. Auth to Claude is via ANTHROPIC_API_KEY at runtime.

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

# ---- Stage 3: runtime ----
FROM node:22-bookworm-slim AS runtime
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    SEQCOLYTE_PYTHON=python3 \
    SEQCOLYTE_REPO=/srv/repo \
    SEQCOLYTE_QC_BIN=/srv/repo/qc/core/target/release/qc-core \
    SEQCOLYTE_STUDIO_DATA=/data/projects

# System deps: Python (pipeline) + the Claude CLI (diagnosis + chat).
# docling is intentionally omitted — it's imported lazily and only for PDF
# extraction, which this deployment does not run.
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-pip ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && npm install -g @anthropic-ai/claude-code \
 && pip3 install --no-cache-dir --break-system-packages \
      numpy pyyaml jsonschema beautifulsoup4 lxml

# Pipeline: Python packages + spec + demo data + the Linux qc-core binary.
WORKDIR /srv/repo
COPY qc/ ./qc/
COPY seqcolyte/ ./seqcolyte/
COPY sim/ ./sim/
COPY extract/ ./extract/
COPY spec/ ./spec/
COPY data/sim/adapter_dimer_f30/ ./data/sim/adapter_dimer_f30/
COPY data/raw/pbmc_1k_v3_sub_R1.fastq.gz data/raw/pbmc_1k_v3_sub_R2.fastq.gz ./data/raw/
COPY whitelists/3M-february-2018.txt.gz ./whitelists/
COPY --from=rust-build /build/qc/core/target/release/qc-core ./qc/core/target/release/qc-core

# Next.js standalone server.
WORKDIR /srv
COPY --from=web-build /app/.next/standalone ./
COPY --from=web-build /app/.next/static ./.next/static
COPY --from=web-build /app/public ./public

# Project store lives on a persistent volume.
RUN mkdir -p /data/projects
VOLUME ["/data"]

EXPOSE 3000
CMD ["node", "server.js"]
