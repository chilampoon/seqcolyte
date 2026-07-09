import { NextResponse } from "next/server";
import { addConclusion, readConclusions } from "@/lib/conclusions";
import { getProject } from "@/lib/store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  try {
    return NextResponse.json({ items: await readConclusions(id) });
  } catch {
    return NextResponse.json({ error: "project not found" }, { status: 404 });
  }
}

export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  try {
    await getProject(id);
  } catch {
    return NextResponse.json({ error: "project not found" }, { status: 404 });
  }
  const body = (await req.json().catch(() => ({}))) as {
    title?: unknown;
    body?: unknown;
    runId?: unknown;
    source?: unknown;
  };
  const title = typeof body.title === "string" ? body.title.trim() : "";
  const text = typeof body.body === "string" ? body.body : "";
  if (!title && !text) {
    return NextResponse.json({ error: "title or body required" }, { status: 400 });
  }
  const conclusion = await addConclusion(id, {
    title: title || "Conclusion",
    body: text,
    runId: typeof body.runId === "string" ? body.runId : null,
    source: body.source === "diagnosis" ? "diagnosis" : "manual",
  });
  return NextResponse.json(conclusion, { status: 201 });
}
