import { promises as fs } from "node:fs";
import { NextResponse } from "next/server";
import { assets } from "@/lib/config";
import { inProject } from "@/lib/paths";
import { getProject } from "@/lib/store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** The project's active spec (extracted, if any) — else the reference spec. */
export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  try {
    const project = await getProject(id);
    const p = project.activeSpecPath
      ? inProject(id, project.activeSpecPath)
      : assets.referenceSpec;
    return NextResponse.json(JSON.parse(await fs.readFile(p, "utf8")));
  } catch {
    return NextResponse.json({ error: "spec not available" }, { status: 404 });
  }
}
