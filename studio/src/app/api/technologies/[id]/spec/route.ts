import { promises as fs } from "node:fs";
import { NextResponse } from "next/server";
import { techSpecPath } from "@/lib/technologies";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** One technology's full extracted spec (served to the SpecPanel). */
export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  try {
    return NextResponse.json(JSON.parse(await fs.readFile(techSpecPath(id), "utf8")));
  } catch {
    return NextResponse.json({ error: "technology spec not found" }, { status: 404 });
  }
}
