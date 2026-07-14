import { promises as fs } from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";
import { runDir } from "@/lib/paths";
import { getProject, getRun } from "@/lib/store";
import { renderQcReportHtml } from "@/lib/reportHtml";
import type { QcReport } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  req: Request,
  ctx: { params: Promise<{ id: string; runId: string }> },
) {
  const { id, runId } = await ctx.params;
  const url = new URL(req.url);
  const asHtml = url.searchParams.get("format") === "html";

  let report: QcReport;
  try {
    const p = path.join(runDir(id, runId), "qc_report.json");
    report = JSON.parse(await fs.readFile(p, "utf8")) as QcReport;
  } catch {
    return NextResponse.json({ error: "report not available yet" }, { status: 404 });
  }

  if (!asHtml) return NextResponse.json(report);

  let projectName = id;
  try {
    projectName = (await getProject(id)).name;
  } catch {
    /* fall back to id */
  }
  let afterFixes = false;
  try {
    afterFixes = (await getRun(id, runId)).options?.fastqSource === "remediated";
  } catch {
    /* not a remediated run */
  }
  const html = renderQcReportHtml(report, { runId, projectName, afterFixes });
  const download = url.searchParams.get("download") != null;
  return new Response(html, {
    headers: {
      "content-type": "text/html; charset=utf-8",
      "content-disposition": `${download ? "attachment" : "inline"}; filename="qc_report_${runId}.html"`,
      "cache-control": "no-store",
    },
  });
}
