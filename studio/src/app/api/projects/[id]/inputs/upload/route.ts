import { promises as fs, createWriteStream } from "node:fs";
import { Readable, Transform } from "node:stream";
import { pipeline } from "node:stream/promises";
import path from "node:path";
import { NextResponse } from "next/server";
import { inProject } from "@/lib/paths";
import { getProject, updateProject } from "@/lib/store";
import { appendConversation } from "@/lib/chat";
import { startExtract } from "@/lib/extractRunner";

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
 * Raw-streaming upload. The client POSTs the file as the request body
 * (`application/octet-stream`) with the original name in the `x-filename`
 * header — no multipart envelope to buffer. FASTQ mates land in `inputs/fastq/`
 * and are tracked on the manifest; protocol docs kick off extraction; design
 * tables are recorded.
 */
export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  let project;
  try {
    project = await getProject(id);
  } catch {
    return NextResponse.json({ error: "project not found" }, { status: 404 });
  }

  const rawName = req.headers.get("x-filename");
  if (!rawName) {
    return NextResponse.json({ error: "missing x-filename header" }, { status: 400 });
  }
  let filename: string;
  try {
    filename = sanitize(decodeURIComponent(rawName));
  } catch {
    filename = sanitize(rawName);
  }
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
  if (!req.body) {
    return NextResponse.json({ error: "empty request body" }, { status: 400 });
  }

  const cap = isFastq ? MAX_FASTQ_BYTES : MAX_DOC_BYTES;
  // Cheap up-front reject when the browser declares the size (it does for a File body).
  const declared = Number(req.headers.get("content-length"));
  if (Number.isFinite(declared) && declared > cap) {
    return NextResponse.json(
      { error: `file too large (${(declared / 1e6) | 0} MB > ${(cap / 1e6) | 0} MB) — subsample it first` },
      { status: 413 },
    );
  }

  const rel = isFastq ? `inputs/fastq/${filename}` : `inputs/${filename}`;
  await fs.mkdir(inProject(id, path.dirname(rel)), { recursive: true });
  const streamed = await streamToFile(req.body, inProject(id, rel), cap);
  if ("error" in streamed) {
    if (streamed.error === "TOO_LARGE") {
      return NextResponse.json(
        { error: `file too large (> ${(cap / 1e6) | 0} MB) — subsample it first` },
        { status: 413 },
      );
    }
    return NextResponse.json({ error: "upload failed while writing to disk" }, { status: 500 });
  }

  // ---- FASTQ reads: R1/R2 tracked on the manifest ----
  if (isFastq) {
    const fastq = { ...(project.inputs.fastq ?? { source: "upload", r1: null, r2: null }) };
    let slot = readSide(filename);
    if (fastq[slot]) slot = slot === "r1" ? "r2" : "r1"; // preferred mate taken -> fill the other
    fastq.source = "upload";
    fastq[slot] = rel;
    await updateProject(id, { inputs: { ...project.inputs, fastq, reads: "uploaded" } });

    const haveBoth = fastq.r1 && fastq.r2;
    await appendConversation(id, [
      {
        role: "user",
        text: `📎 Uploaded reads **${filename}** (${slot.toUpperCase()})`,
        ts: new Date().toISOString(),
      },
      ...(haveBoth
        ? [
            {
              role: "assistant" as const,
              text: "Both mates (R1 + R2) are in. Confirm the spec and I'll run QC on **your** reads.",
              ts: new Date().toISOString(),
            },
          ]
        : []),
    ]);
    return NextResponse.json({ ok: true, filename, kind: "reads", side: slot, haveBoth });
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
