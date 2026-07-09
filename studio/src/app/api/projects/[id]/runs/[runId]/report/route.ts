import { promises as fs } from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";
import { runDir } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ id: string; runId: string }> },
) {
  const { id, runId } = await ctx.params;
  try {
    const p = path.join(runDir(id, runId), "qc_report.json");
    const data = JSON.parse(await fs.readFile(p, "utf8"));
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: "report not available yet" }, { status: 404 });
  }
}
