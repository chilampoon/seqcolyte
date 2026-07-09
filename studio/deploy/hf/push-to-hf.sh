#!/usr/bin/env bash
#
# Push Seqcolyte Studio to a Hugging Face Docker Space using the `hf` CLI, which
# stores binary data (FASTQ .gz) via Xet/LFS automatically — no git-lfs needed.
#
# Prereqs (once):
#   1. hf auth login                                   # write-scoped token
#   2. Create a Space (SDK = Docker) at https://huggingface.co/new-space
#      (requires a Hugging Face PRO plan for compute Spaces)
#
# Usage:
#   studio/deploy/hf/push-to-hf.sh <owner>/<space-name>
#   studio/deploy/hf/push-to-hf.sh https://huggingface.co/spaces/<owner>/<space-name>
set -euo pipefail

ARG="${1:-}"
if [[ -z "$ARG" ]]; then
  echo "usage: $0 <owner>/<space-name>   (or the full Space URL)" >&2
  exit 1
fi
# Accept either "owner/name" or a full Space URL.
REPO_ID="$ARG"
if [[ "$ARG" == http* ]]; then
  REPO_ID="${ARG#*huggingface.co/spaces/}"
  REPO_ID="${REPO_ID%.git}"
  REPO_ID="${REPO_ID%/}"
fi

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"   # seqcolyte repo root
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "repo:    $REPO"
echo "space:   $REPO_ID"
echo "staging: $WORK"

# NOTE: no bare `--exclude projects` — rsync would match it anywhere and drop the
# src/app/api/projects and src/app/projects ROUTES. The local store is removed
# explicitly below instead.
EXCLUDES=(--exclude node_modules --exclude .next --exclude target
          --exclude __pycache__ --exclude '*.pyc'
          --exclude '.env' --exclude '.env.local' --exclude '.git')

echo "assembling Space contents…"
mkdir -p "$WORK/data/sim" "$WORK/data/raw"
rsync -a "${EXCLUDES[@]}" "$REPO/studio"    "$WORK/"
rsync -a "${EXCLUDES[@]}" "$REPO/qc"        "$WORK/"
rsync -a "${EXCLUDES[@]}" "$REPO/seqcolyte" "$WORK/"
rsync -a "${EXCLUDES[@]}" "$REPO/sim"       "$WORK/"
rsync -a "${EXCLUDES[@]}" "$REPO/extract"   "$WORK/"
rsync -a "${EXCLUDES[@]}" "$REPO/spec"      "$WORK/"
rsync -a "${EXCLUDES[@]}" "$REPO/data/sim/adapter_dimer_f30" "$WORK/data/sim/"
cp "$REPO/data/raw/pbmc_1k_v3_sub_R1.fastq.gz" \
   "$REPO/data/raw/pbmc_1k_v3_sub_R2.fastq.gz" "$WORK/data/raw/"
mkdir -p "$WORK/whitelists"
cp "$REPO/whitelists/3M-february-2018.txt.gz" "$WORK/whitelists/"

# Drop the local project store (runs/chats/conclusions) — not part of the deploy.
rm -rf "$WORK/studio/projects"

# HF entry point: root Dockerfile + README (frontmatter) + LFS/Xet .gitattributes.
cp "$HERE/Dockerfile"     "$WORK/Dockerfile"
cp "$HERE/README.md"      "$WORK/README.md"
cp "$HERE/.gitattributes" "$WORK/.gitattributes"
cp "$HERE/.gitignore"     "$WORK/.gitignore"

echo "uploading to the Space (binaries go via Xet)…"
hf upload "$REPO_ID" "$WORK" . \
  --repo-type space \
  --delete "*" \
  --exclude "**/node_modules/**" "**/.next/**" "**/target/**" \
            "**/__pycache__/**" "**/*.pyc" "studio/projects/**" \
            "**/.env" "**/.env.local" \
  --commit-message "Deploy Seqcolyte Studio"

echo
echo "✅ uploaded. HF is now building your Space:"
echo "   https://huggingface.co/spaces/${REPO_ID}"
echo "Set ANTHROPIC_API_KEY (and optionally STUDIO_AUTH_USER/PASS) under"
echo "Settings → Variables and secrets, then wait for the build to finish."
