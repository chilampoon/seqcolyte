import { NextResponse } from "next/server";
import { getProject } from "@/lib/store";
import { isExtracting, readExtractState, startExtract } from "@/lib/extractRunner";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const state = await readExtractState(id);
  return NextResponse.json({ ...(state ?? { status: "idle" }), running: isExtracting(id) });
}

/** Manually (re-)extract from the project's current protocol doc, or a given doc. */
export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  let project;
  try {
    project = await getProject(id);
  } catch {
    return NextResponse.json({ error: "project not found" }, { status: 404 });
  }
  const body = (await req.json().catch(() => ({}))) as { doc?: unknown };
  const doc = typeof body.doc === "string" ? body.doc : project.inputs.protocolDoc;
  if (!doc) {
    return NextResponse.json({ error: "no protocol doc to extract" }, { status: 400 });
  }
  if (isExtracting(id)) return NextResponse.json({ ok: true, alreadyRunning: true });
  await startExtract(id, doc);
  return NextResponse.json({ ok: true });
}
