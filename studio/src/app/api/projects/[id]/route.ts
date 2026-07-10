import { NextResponse } from "next/server";
import { getProject, updateProject } from "@/lib/store";
import type { ProjectManifest, ProjectPhase } from "@/lib/types";

const PHASES: ProjectPhase[] = [
  "awaiting_inputs",
  "extracting",
  "awaiting_spec_review",
  "spec_confirmed",
  "analyzing",
  "complete",
];

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  try {
    return NextResponse.json(await getProject(id));
  } catch {
    return NextResponse.json({ error: "project not found" }, { status: 404 });
  }
}

/** Rename (and other manifest patches). Changes manifest fields only, never the id. */
export async function PATCH(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const body = (await req.json().catch(() => ({}))) as { name?: unknown; phase?: unknown };
  const patch: Partial<ProjectManifest> = {};
  if (typeof body.name === "string" && body.name.trim()) patch.name = body.name.trim();
  if (typeof body.phase === "string" && PHASES.includes(body.phase as ProjectPhase)) {
    patch.phase = body.phase as ProjectPhase;
  }
  if (Object.keys(patch).length === 0) {
    return NextResponse.json({ error: "nothing to update" }, { status: 400 });
  }
  try {
    return NextResponse.json(await updateProject(id, patch));
  } catch {
    return NextResponse.json({ error: "project not found" }, { status: 404 });
  }
}
