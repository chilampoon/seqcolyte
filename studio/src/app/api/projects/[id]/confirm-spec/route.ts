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

  // The spec is confirmed. QC runs only on the user's own reads — if they aren't
  // uploaded yet, hold at `awaiting_reads` and ask for them (uploading both mates
  // then auto-starts the run via the upload route).
  const single = project.platform === "nanopore";
  const fq = project.inputs.fastq;
  const hasUpload = fq?.source === "upload" && !!fq.r1 && (single || !!fq.r2);

  if (!hasUpload) {
    await updateProject(id, { specConfirmed: true, phase: "awaiting_reads" });
    await appendConversation(id, [
      {
        role: "assistant",
        text:
          "Spec confirmed ✓ — now upload your sequencing reads (R1 + R2 FASTQ, `.fastq.gz`) with the " +
          "📎 button or by dragging them in. QC starts automatically as soon as both mates are in.",
        ts: new Date().toISOString(),
      },
    ]);
    return NextResponse.json({ ok: true, needReads: true });
  }

  await updateProject(id, {
    specConfirmed: true,
    phase: "spec_confirmed",
    inputs: { ...project.inputs, reads: "uploaded" },
  });

  const result = await startQcRun(id, { useLlm: true, fastqSource: "upload" });
  if ("error" in result) {
    await updateProject(id, { phase: "awaiting_reads" });
    return NextResponse.json({ error: result.error }, { status: 400 });
  }

  await updateProject(id, { phase: "analyzing" });
  await appendConversation(id, [
    {
      role: "assistant",
      text:
        "Spec confirmed ✓ — running the QC pipeline on **your uploaded reads** now. I'll stream each " +
        "stage below; the ranked diagnosis and evidence chain land when it finishes.",
      ts: new Date().toISOString(),
    },
  ]);

  return NextResponse.json({ ok: true, runId: result.runId });
}
