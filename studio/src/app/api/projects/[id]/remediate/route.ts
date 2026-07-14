import { promises as fs } from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";
import { runDir } from "@/lib/paths";
import { getProject } from "@/lib/store";
import { generateFixScript, isSolvable } from "@/lib/remediate";
import type { QcReport } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Manually (re)generate ONE fix script for a finding of the latest run. Scripts are normally authored
 * eagerly the moment a QC run finishes (see runner.ts finalize → generateAllFixes); this endpoint is
 * for an explicit regenerate. Returns once generation kicks off; the manifest `scripts[]` status
 * (generating → generated/failed) reflects progress.
 */
export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const body = (await req.json().catch(() => ({}))) as { checkId?: string };
  const checkId = body.checkId ?? "";
  if (!isSolvable(checkId)) {
    return NextResponse.json({ error: "this finding isn't computationally solvable" }, { status: 400 });
  }

  let project;
  try {
    project = await getProject(id);
  } catch {
    return NextResponse.json({ error: "project not found" }, { status: 404 });
  }
  if (!project.latestRunId) {
    return NextResponse.json({ error: "no QC run to remediate" }, { status: 400 });
  }

  let report: QcReport;
  try {
    report = JSON.parse(
      await fs.readFile(path.join(runDir(id, project.latestRunId), "qc_report.json"), "utf8"),
    ) as QcReport;
  } catch {
    return NextResponse.json({ error: "QC report not found" }, { status: 400 });
  }
  const finding = (report.findings ?? []).find((f) => f.check_id === checkId);
  if (!finding) {
    return NextResponse.json({ error: "finding not found" }, { status: 400 });
  }

  await generateFixScript(id, finding);
  return NextResponse.json({ ok: true });
}
