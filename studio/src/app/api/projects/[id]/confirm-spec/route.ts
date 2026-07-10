import { NextResponse } from "next/server";
import { getProject, updateProject } from "@/lib/store";
import { appendConversation } from "@/lib/chat";
import { startQcRun } from "@/lib/runner";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Confirm the extracted spec (the review gate) and kick off the QC analysis on
 * the built-in demo dataset. Advances the phase awaiting_spec_review → analyzing.
 */
export async function POST(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;

  let project;
  try {
    project = await getProject(id);
  } catch {
    return NextResponse.json({ error: "project not found" }, { status: 404 });
  }
  if (!project.activeSpecPath) {
    return NextResponse.json({ error: "no extracted spec to confirm" }, { status: 400 });
  }

  await updateProject(id, {
    specConfirmed: true,
    phase: "spec_confirmed",
    inputs: { ...project.inputs, reads: "demo" },
  });

  // Analysis runs on the labeled demo dataset (enables the eval / confusion matrix).
  const result = await startQcRun(id, { useLlm: true, fastqSource: "sim" });
  if ("error" in result) {
    await updateProject(id, { phase: "awaiting_spec_review" });
    return NextResponse.json({ error: result.error }, { status: 400 });
  }

  await updateProject(id, { phase: "analyzing" });
  await appendConversation(id, [
    {
      role: "assistant",
      text:
        "Spec confirmed ✓ — running the QC pipeline on the labeled demo dataset now. " +
        "I'll stream each stage below; the ranked diagnosis and evidence chain land when it finishes.",
      ts: new Date().toISOString(),
    },
  ]);

  return NextResponse.json({ ok: true, runId: result.runId });
}
