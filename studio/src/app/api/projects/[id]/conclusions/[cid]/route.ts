import { NextResponse } from "next/server";
import { deleteConclusion } from "@/lib/conclusions";
import { assertSafeId } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function DELETE(
  _req: Request,
  ctx: { params: Promise<{ id: string; cid: string }> },
) {
  const { id, cid } = await ctx.params;
  try {
    assertSafeId(id);
    assertSafeId(cid);
  } catch {
    return NextResponse.json({ error: "bad id" }, { status: 400 });
  }
  await deleteConclusion(id, cid);
  return NextResponse.json({ ok: true });
}
