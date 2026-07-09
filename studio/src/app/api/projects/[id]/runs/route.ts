import { promises as fs } from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";
import { assets } from "@/lib/config";
import { inProject, runDir } from "@/lib/paths";
import { allocateRun, getProject, listRuns, updateRun } from "@/lib/store";
import { launchRun } from "@/lib/runner";
import type { RunRecord } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function exists(p: string): Promise<boolean> {
  try {
    await fs.access(p);
    return true;
  } catch {
    return false;
  }
}

export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  try {
    return NextResponse.json(await listRuns(id));
  } catch {
    return NextResponse.json({ error: "project not found" }, { status: 404 });
  }
}

export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;

  let project;
  try {
    project = await getProject(id);
  } catch {
    return NextResponse.json({ error: "project not found" }, { status: 404 });
  }

  const body = (await req.json().catch(() => ({}))) as {
    useLlm?: boolean;
    maxReads?: number;
    fastqSource?: "control" | "sim";
  };
  const useLlm = body.useLlm !== false; // default on — the LLM diagnosis is the headline
  const maxReads =
    typeof body.maxReads === "number" && body.maxReads > 0 ? Math.floor(body.maxReads) : null;
  const fastqSource: "control" | "sim" = body.fastqSource === "control" ? "control" : "sim";

  // Resolve inputs. Spec: project's extracted spec if present, else the reference.
  const specSource =
    project.activeSpecPath && (await exists(inProject(id, project.activeSpecPath)))
      ? inProject(id, project.activeSpecPath)
      : assets.referenceSpec;
  const r1 = fastqSource === "control" ? assets.control.r1 : assets.sim.r1;
  const r2 = fastqSource === "control" ? assets.control.r2 : assets.sim.r2;
  const whitelist = (await exists(assets.whitelist)) ? assets.whitelist : null;
  // Ground-truth labels only exist for the simulated dataset (enables the eval panel).
  const labels = fastqSource === "sim" && (await exists(assets.sim.labels)) ? assets.sim.labels : null;

  if (!(await exists(r1)) || !(await exists(r2))) {
    return NextResponse.json(
      { error: `reads not found for source "${fastqSource}"` },
      { status: 400 },
    );
  }

  const base: Omit<RunRecord, "id" | "projectId" | "createdAt" | "schemaVersion"> = {
    pipeline: ["qc"],
    options: {
      useLlm,
      maxReads,
      withLabels: !!labels,
      withWhitelist: !!whitelist,
      fastqSource,
    },
    inputsSnapshot: { specPath: "", r1, r2, whitelist, labels },
    steps: { qc: { name: "qc", status: "queued", log: "logs/qc.log" } },
    overallStatus: "queued",
  };

  const run = await allocateRun(id, base);

  // Snapshot the spec into the run dir for immutable provenance, then record its path.
  const snapshot = path.join(runDir(id, run.id), "spec.json");
  await fs.copyFile(specSource, snapshot);
  await updateRun(id, run.id, (r) => ({
    ...r,
    inputsSnapshot: { ...r.inputsSnapshot, specPath: snapshot },
  }));

  launchRun(id, run.id);
  return NextResponse.json({ runId: run.id }, { status: 201 });
}
