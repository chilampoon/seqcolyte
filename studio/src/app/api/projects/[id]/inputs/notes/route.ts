import { promises as fs } from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";
import { inProject } from "@/lib/paths";
import { getProject, updateProject } from "@/lib/store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  try {
    const text = await fs.readFile(inProject(id, "inputs/notes.md"), "utf8");
    return NextResponse.json({ notes: text });
  } catch {
    return NextResponse.json({ notes: "" });
  }
}

export async function PUT(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  try {
    await getProject(id);
  } catch {
    return NextResponse.json({ error: "project not found" }, { status: 404 });
  }
  const body = (await req.json().catch(() => ({}))) as { notes?: unknown };
  const notes = typeof body.notes === "string" ? body.notes : "";
  if (notes.length > 100_000) {
    return NextResponse.json({ error: "notes too long" }, { status: 400 });
  }
  const notesPath = inProject(id, "inputs/notes.md");
  await fs.mkdir(path.dirname(notesPath), { recursive: true });
  await fs.writeFile(notesPath, notes);
  await updateProject(id, {}); // bump updatedAt
  return NextResponse.json({ ok: true });
}
