# Deploy Seqcolyte Studio to a Hugging Face Space

A free, shareable URL for others to try — Docker Space with 16 GB RAM (plenty for
the whitelist step). The `hf` CLI is already installed here.

## 1. Log in

```bash
hf auth login          # paste a token (create one at https://huggingface.co/settings/tokens, "write" scope)
```

## 2. Create the Space

Go to https://huggingface.co/new-space and choose:
- **Owner**: you · **Space name**: e.g. `seqcolyte`
- **SDK**: **Docker** → **Blank**
- **Hardware**: CPU basic (free, 16 GB) · Visibility: your call

That gives you a git URL like `https://huggingface.co/spaces/<you>/seqcolyte`.

## 3. Push

```bash
studio/deploy/hf/push-to-hf.sh https://huggingface.co/spaces/<you>/seqcolyte
```

This assembles just the files the build needs (UI + pipeline + demo data — no
`node_modules`/`.next`/`target`), drops in the HF Dockerfile + README, and pushes.
HF then builds the image (a few minutes: it compiles the Rust core, builds Next,
and downloads the barcode whitelist).

## 4. Add secrets

In the Space's **Settings → Variables and secrets**:

| Name | Type | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | secret | **Required.** Powers diagnosis + chat. **Set a spend limit** on the key. |
| `STUDIO_AUTH_USER` | secret | Recommended for public Spaces — basic-auth username. |
| `STUDIO_AUTH_PASS` | secret | Recommended for public Spaces — basic-auth password. |

After adding secrets, the Space restarts. Open the Space URL, create a project,
pick the **adapter-dimer simulation** reads, and **Run QC** → you'll see findings,
the AI diagnosis, the eval scores, the evidence-chain drill-down, and the chat.

## Notes

- **Cost/security**: a public Space means strangers can spend your API key. The
  spend limit + the `STUDIO_AUTH_*` gate are your safeguards.
- **Persistence**: the project store is ephemeral (resets when the Space sleeps or
  restarts). To keep projects, attach HF persistent storage and set a Space
  variable `SEQCOLYTE_STUDIO_DATA=/data/projects`.
- **Local stays on your subscription**: `cd studio && npm run dev` keeps using your
  Claude Code login; only the Space uses the API key.
- Re-deploy anytime by re-running `push-to-hf.sh`.
