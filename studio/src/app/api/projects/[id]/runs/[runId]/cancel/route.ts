import { NextResponse } from "next/server";
import { cancelRun } from "@/lib/runner";
import { assertSafeId } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(
  _req: Request,
  ctx: { params: Promise<{ id: string; runId: string }> },
) {
  const { id, runId } = await ctx.params;
  try {
    assertSafeId(id);
    assertSafeId(runId);
  } catch {
    return NextResponse.json({ error: "bad id" }, { status: 400 });
  }
  const killed = cancelRun(id, runId);
  return NextResponse.json({ ok: true, killed });
}
