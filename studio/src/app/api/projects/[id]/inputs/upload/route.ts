import { promises as fs, createWriteStream } from "node:fs";
import { Readable, Transform } from "node:stream";
import { pipeline } from "node:stream/promises";
import path from "node:path";
import { NextResponse } from "next/server";
import { inProject } from "@/lib/paths";
import { getProject, updateProject } from "@/lib/store";
import { appendConversation } from "@/lib/chat";
import { startExtract } from "@/lib/extractRunner";
import { startQcRun } from "@/lib/runner";
import { authChallenge, basicAuthOk } from "@/lib/auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const DOC_EXT = new Set([".pdf", ".txt", ".md"]);
const TABLE_EXT = new Set([".csv", ".tsv", ".xlsx", ".xls"]);
const FASTQ_RE = /\.(fastq|fq)(\.gz)?$/i;
const BLOCKED_EXT = new Set([".bam", ".sam", ".cram"]);
const MAX_FASTQ_BYTES = 800 * 1024 * 1024;
const MAX_DOC_BYTES = 100 * 1024 * 1024;

function sanitize(name: string): string {
  const base = name.split(/[\\/]/).pop() ?? "file";
  const s = base.replace(/[^A-Za-z0-9._-]/g, "_").replace(/^\.+/, "").slice(0, 100);
  return s || "file";
}

/** Guess which mate an uploaded FASTQ is (R1/R2 / _1/_2 / read1/read2); default R1. */
function readSide(name: string): "r1" | "r2" {
  return /(^|[._-])(r?2|read[._-]?2)([._-]|$)/i.test(name) ? "r2" : "r1";
}

/**
 * Stream a raw request body straight to disk: flat memory, the write overlaps
 * with the receive, and nothing is buffered (unlike `req.formData()`, which
 * materializes the whole file first). A mid-stream cap enforces the size limit
 * even when Content-Length lies or is absent; on overflow or a dropped
 * connection the partial file is removed so we never leave a truncated read.
 */
async function streamToFile(
  body: ReadableStream<Uint8Array>,
  dest: string,
  maxBytes: number,
): Promise<{ bytes: number } | { error: "TOO_LARGE" | "IO" }> {
  let bytes = 0;
  const cap = new Transform({
    transform(chunk: Buffer, _enc, cb) {
      bytes += chunk.length;
      if (bytes > maxBytes) cb(new Error("TOO_LARGE"));
      else cb(null, chunk);
    },
  });
  try {
    await pipeline(
      Readable.fromWeb(body as Parameters<typeof Readable.fromWeb>[0]),
      cap,
      createWriteStream(dest),
    );
    return { bytes };
  } catch (err) {
    await fs.rm(dest, { force: true }).catch(() => {});
    return { error: (err as Error).message === "TOO_LARGE" ? "TOO_LARGE" : "IO" };
  }
}

/**
 * Pull the filename + a body stream from either upload format:
 *  - raw streaming (current client): `x-filename` header + the octet-stream body;
 *  - multipart/form-data (older cached clients, `curl -F`, other callers): the
 *    `file` part.
 * Accepting both means a deploy that changes the client wire format can never
 * strand a browser running stale JS — the exact failure that made uploads look
 * like "nothing happened". `multipart` lets the caller skip the Content-Length
 * pre-check (that length includes the envelope, and the body is already read).
 */
async function readUpload(
  req: Request,
): Promise<
  { filename: string; body: ReadableStream<Uint8Array>; multipart: boolean } | { error: string }
> {
  const ct = req.headers.get("content-type") ?? "";
  if (ct.includes("multipart/form-data")) {
    const form = await req.formData().catch(() => null);
    const file = form?.get("file");
    if (!(file instanceof File)) return { error: "no file in form data" };
    return { filename: file.name, body: file.stream() as ReadableStream<Uint8Array>, multipart: true };
  }
  const rawName = req.headers.get("x-filename");
  if (!rawName) return { error: "missing file (send x-filename header or multipart form-data)" };
  if (!req.body) return { error: "empty request body" };
  let filename: string;
  try {
    filename = decodeURIComponent(rawName);
  } catch {
    filename = rawName;
  }
  return { filename, body: req.body, multipart: false };
}

/**
 * Upload endpoint. Streams the file straight to disk (flat memory) from either a
 * raw octet body or a multipart form. FASTQ mates land in `inputs/fastq/` and are
 * tracked on the manifest; protocol docs kick off extraction; design tables are
 * recorded.
 */
export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  // This route is excluded from the auth middleware (to avoid its 10 MiB body cap), so gate here.
  if (!basicAuthOk(req)) return authChallenge();
  const { id } = await ctx.params;
  let project;
  try {
    project = await getProject(id);
  } catch {
    return NextResponse.json({ error: "project not found" }, { status: 404 });
  }

  const src = await readUpload(req);
  if ("error" in src) {
    return NextResponse.json({ error: src.error }, { status: 400 });
  }
  const filename = sanitize(src.filename);
  const ext = path.extname(filename).toLowerCase();

  if (BLOCKED_EXT.has(ext)) {
    return NextResponse.json(
      { error: "aligned reads (BAM/SAM/CRAM) aren't supported here — upload FASTQ (R1 + R2)" },
      { status: 400 },
    );
  }

  const isFastq = FASTQ_RE.test(filename);
  const kind = isFastq ? "reads" : DOC_EXT.has(ext) ? "doc" : TABLE_EXT.has(ext) ? "table" : null;
  if (!kind) {
    return NextResponse.json({ error: `unsupported file type ${ext || "(none)"}` }, { status: 400 });
  }

  const cap = isFastq ? MAX_FASTQ_BYTES : MAX_DOC_BYTES;
  // Cheap up-front reject when the size is declared (raw File body sets Content-Length).
  const declared = Number(req.headers.get("content-length"));
  if (!src.multipart && Number.isFinite(declared) && declared > cap) {
    return NextResponse.json(
      { error: `file too large (${(declared / 1e6) | 0} MB > ${(cap / 1e6) | 0} MB) — subsample it first` },
      { status: 413 },
    );
  }

  const rel = isFastq ? `inputs/fastq/${filename}` : `inputs/${filename}`;
  await fs.mkdir(inProject(id, path.dirname(rel)), { recursive: true });
  const streamed = await streamToFile(src.body, inProject(id, rel), cap);
  if ("error" in streamed) {
    if (streamed.error === "TOO_LARGE") {
      return NextResponse.json(
        { error: `file too large (> ${(cap / 1e6) | 0} MB) — subsample it first` },
        { status: 413 },
      );
    }
    return NextResponse.json({ error: "upload failed while writing to disk" }, { status: 500 });
  }

  // ---- FASTQ reads: single long-read (nanopore) or paired R1/R2 (short-read) ----
  if (isFastq) {
    const single = project.platform === "nanopore";
    const fastq = { ...(project.inputs.fastq ?? { source: "upload", r1: null, r2: null }) };
    fastq.source = "upload";
    let slot: "r1" | "r2" = "r1";
    if (single) {
      fastq.r1 = rel; // nanopore: one long-read file, no mate
      fastq.r2 = null;
    } else {
      slot = readSide(filename);
      if (fastq[slot]) slot = slot === "r1" ? "r2" : "r1"; // preferred mate taken -> fill the other
      fastq[slot] = rel;
    }
    await updateProject(id, { inputs: { ...project.inputs, fastq, reads: "uploaded" } });

    const haveReads = single ? !!fastq.r1 : !!(fastq.r1 && fastq.r2);
    await appendConversation(id, [
      {
        role: "user",
        text: `📎 Uploaded reads **${filename}**${single ? "" : ` (${slot.toUpperCase()})`}`,
        ts: new Date().toISOString(),
      },
    ]);

    // If the spec is already confirmed and the reads are complete, QC auto-starts.
    if (haveReads && project.specConfirmed && !project.latestRunId) {
      const result = await startQcRun(id, { useLlm: true, fastqSource: "upload" });
      if (!("error" in result)) {
        await updateProject(id, { phase: "analyzing" });
        await appendConversation(id, [
          {
            role: "assistant",
            text:
              "Reads are in — running the QC pipeline on **your reads** now. I'll stream each " +
              "stage below; the ranked diagnosis and evidence chain land when it finishes.",
            ts: new Date().toISOString(),
          },
        ]);
        return NextResponse.json({ ok: true, filename, kind: "reads", side: slot, haveBoth: haveReads, runId: result.runId });
      }
    }

    if (haveReads) {
      await appendConversation(id, [
        {
          role: "assistant",
          text: single
            ? "Your reads are in. Confirm the spec and I'll run QC on **your reads**."
            : "Both mates (R1 + R2) are in. Confirm the spec and I'll run QC on **your reads**.",
          ts: new Date().toISOString(),
        },
      ]);
    }
    return NextResponse.json({ ok: true, filename, kind: "reads", side: slot, haveBoth: haveReads });
  }

  // ---- protocol doc / design table ----
  const inputs = { ...project.inputs };
  if (kind === "doc") inputs.protocolDoc = rel;
  else inputs.tables = [...(project.inputs.tables ?? []), rel];
  await updateProject(id, { inputs });

  await appendConversation(id, [
    { role: "user", text: `📎 Uploaded **${filename}**`, ts: new Date().toISOString() },
  ]);

  if (kind === "doc") await startExtract(id, rel);

  return NextResponse.json({ ok: true, filename, kind, extract: kind === "doc" });
}
