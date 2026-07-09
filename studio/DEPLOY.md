# Deploying Seqcolyte Studio

Studio is a **self-hosted container**, not a Vercel/serverless app. It shells out to
a real Python + Rust pipeline, spawns long-lived jobs, streams logs over SSE, and
persists projects to disk — all of which need a normal server with a writable
filesystem, exactly what a container gives you (and what serverless does not).

This is the same model as a typical Flask+Docker app: build one image, run it on any
host with Docker, and authenticate to the AI with an **API key** in `.env`.

## Prerequisites

- **Docker** (with `docker compose`).
- An **Anthropic API key** — https://console.anthropic.com/. In a container the
  Claude CLI can't use your laptop's `claude` subscription login, so diagnosis + chat
  authenticate via `ANTHROPIC_API_KEY` and **bill per token**.

## Run it locally

```bash
cd studio
cp .env.example .env          # then set ANTHROPIC_API_KEY
docker compose up -d --build  # first build takes a few minutes (compiles Rust, builds Next)
# open http://localhost:3000
```

The build bundles everything: the Next app, the Python pipeline, a Linux-compiled
`qc-core`, the Claude CLI, and the demo data (10x control + adapter-dimer sim +
whitelist). Projects/runs/chats persist in the `studio-data` Docker volume.

## Deploy to a host

Any Docker host works — a VM (EC2/GCE/DigitalOcean), Fly.io, Railway, Render, or a
container service. Two ways:

1. **Build on the host**: copy the repo, `cd studio`, set `.env`, `docker compose up -d --build`.
2. **Build once, push a tag**: `docker build -f studio/Dockerfile -t <registry>/seqcolyte-studio .`
   from the repo root, push it, and run that image on the host with the same env + a
   volume mounted at `/data`.

Put a TLS-terminating reverse proxy (Caddy/nginx) or the platform's routing in front
for HTTPS.

## Security (important for public URLs)

The app spawns **paid Claude calls** and runs a pipeline, and the chat agent can read
files in the project store. Before exposing it to the internet, set the built-in
basic-auth gate:

```
STUDIO_AUTH_USER=you
STUDIO_AUTH_PASS=a-long-random-string
```

With both set, every request needs those credentials (browser handles it for fetch +
SSE). Leave them blank only on a trusted private network. Consider also setting a
spend limit on your Anthropic key.

## Environment variables

| Var | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | yes | Claude auth for diagnosis + chat (per-token billing) |
| `SEQCOLYTE_MODEL` | no | Model (default `claude-opus-4-8`) |
| `STUDIO_AUTH_USER` / `STUDIO_AUTH_PASS` | for public | Basic-auth gate |
| `SEQCOLYTE_STUDIO_DATA` | no | Project store path (default `/data/projects`, on the volume) |

## Notes & limits

- **Not Vercel serverless** — the filesystem store, detached pipeline processes, and
  SSE-from-subprocess require a long-running server. Use a container host.
- **Scope**: this image serves QC + inspect + grounded chat. Running the full pipeline
  from an uploaded protocol PDF (extract → simulate) is not wired into the UI yet and
  its heavy `docling` dependency is omitted to keep the image lean.
- **First Claude call in-container**: the Claude CLI may need to accept the working
  directory on first use; if diagnosis/chat error on a fresh deploy, verify the
  `ANTHROPIC_API_KEY` is set and reachable from the container.
