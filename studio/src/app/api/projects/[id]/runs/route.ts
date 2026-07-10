import { NextResponse } from "next/server";
import { listRuns } from "@/lib/store";
import { startQcRun } from "@/lib/runner";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  try {
    return NextResponse.json(await listRuns(id));
  } catch {
    return NextResponse.json({ error: "project not found" }, { status: 404 });
  }
}

export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const body = (await req.json().catch(() => ({}))) as {
    useLlm?: boolean;
    maxReads?: number;
    fastqSource?: "control" | "sim";
  };

  const result = await startQcRun(id, {
    useLlm: body.useLlm,
    fastqSource: body.fastqSource,
    maxReads: body.maxReads,
  });
  if ("error" in result) {
    const status = result.error === "project not found" ? 404 : 400;
    return NextResponse.json({ error: result.error }, { status });
  }
  return NextResponse.json(result, { status: 201 });
}
