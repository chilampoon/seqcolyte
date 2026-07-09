import { promises as fs } from "node:fs";
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
const BLOCKED_EXT = new Set([".fastq", ".fq", ".gz", ".bam", ".sam", ".cram"]);

function sanitize(name: string): string {
  const base = name.split(/[\\/]/).pop() ?? "file";
  const s = base.replace(/[^A-Za-z0-9._-]/g, "_").replace(/^\.+/, "").slice(0, 100);
  return s || "file";
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
      { error: "raw reads aren't uploaded here — pick your reads at run time" },
      { status: 400 },
    );
  }
  const kind = DOC_EXT.has(ext) ? "doc" : TABLE_EXT.has(ext) ? "table" : null;
  if (!kind) {
    return NextResponse.json({ error: `unsupported file type ${ext || "(none)"}` }, { status: 400 });
  }

  const rel = `inputs/${filename}`;
  await fs.mkdir(inProject(id, "inputs"), { recursive: true });
  await fs.writeFile(inProject(id, rel), Buffer.from(await file.arrayBuffer()));

  // Update the manifest (shallow-merge replaces `inputs`, so spread the current one).
  const inputs = { ...project.inputs };
  if (kind === "doc") inputs.protocolDoc = rel;
  else inputs.tables = [...(project.inputs.tables ?? []), rel];
  await updateProject(id, { inputs });

  await appendConversation(id, [
    { role: "user", text: `📎 Uploaded **${filename}**`, ts: new Date().toISOString() },
  ]);

  // Protocol docs auto-kick extraction (Task 4).
  if (kind === "doc") await startExtract(id, rel);

  return NextResponse.json({ ok: true, filename, kind, extract: kind === "doc" });
}
