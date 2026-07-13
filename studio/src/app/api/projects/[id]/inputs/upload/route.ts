import { promises as fs, createWriteStream } from "node:fs";
import { Readable } from "node:stream";
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

function sanitize(name: string): string {
  const base = name.split(/[\\/]/).pop() ?? "file";
  const s = base.replace(/[^A-Za-z0-9._-]/g, "_").replace(/^\.+/, "").slice(0, 100);
  return s || "file";
}

/** Guess which mate an uploaded FASTQ is (R1/R2 / _1/_2 / read1/read2); default R1. */
function readSide(name: string): "r1" | "r2" {
  return /(^|[._-])(r?2|read[._-]?2)([._-]|$)/i.test(name) ? "r2" : "r1";
}

export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  let project;
  try {
    project = await getProject(id);
  } catch {
    return NextResponse.json({ error: "project not found" }, { status: 404 });
  }

  const form = await req.formData().catch(() => null);
  const file = form?.get("file");
  if (!(file instanceof File)) {
    return NextResponse.json({ error: "no file" }, { status: 400 });
  }

  const filename = sanitize(file.name);
  const ext = path.extname(filename).toLowerCase();
  if (BLOCKED_EXT.has(ext)) {
    return NextResponse.json(
      { error: "aligned reads (BAM/SAM/CRAM) aren't supported here — upload FASTQ (R1 + R2)" },
      { status: 400 },
    );
  }

  // ---- FASTQ reads: streamed to disk (never buffered), R1/R2 tracked on the manifest ----
  if (FASTQ_RE.test(filename)) {
    if (file.size > MAX_FASTQ_BYTES) {
      return NextResponse.json(
        { error: `FASTQ too large (${(file.size / 1e6) | 0} MB > 800 MB) — subsample it first` },
        { status: 413 },
      );
    }
    const rel = `inputs/fastq/${filename}`;
    await fs.mkdir(inProject(id, "inputs/fastq"), { recursive: true });
    await pipeline(
      Readable.fromWeb(file.stream() as Parameters<typeof Readable.fromWeb>[0]),
      createWriteStream(inProject(id, rel)),
    );

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

  const kind = DOC_EXT.has(ext) ? "doc" : TABLE_EXT.has(ext) ? "table" : null;
  if (!kind) {
    return NextResponse.json({ error: `unsupported file type ${ext || "(none)"}` }, { status: 400 });
  }

  const rel = `inputs/${filename}`;
  await fs.mkdir(inProject(id, "inputs"), { recursive: true });
  await fs.writeFile(inProject(id, rel), Buffer.from(await file.arrayBuffer()));

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
