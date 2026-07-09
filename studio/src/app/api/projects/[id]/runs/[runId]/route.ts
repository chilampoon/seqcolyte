import { NextResponse } from "next/server";
import { getRun } from "@/lib/store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ id: string; runId: string }> },
) {
  const { id, runId } = await ctx.params;
  try {
    return NextResponse.json(await getRun(id, runId));
  } catch {
    return NextResponse.json({ error: "run not found" }, { status: 404 });
  }
}
