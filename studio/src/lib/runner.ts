import path from "node:path";
import { promises as fs } from "node:fs";
import { assets, DEFAULT_MODEL, PYTHON, REPO_ROOT } from "./config";
import { inProject, runDir } from "./paths";
import { allocateRun, getProject, getRun, updateRun } from "./store";
import { killGroup, spawnLogged } from "./spawn";
import type { QcReport, RunRecord, StepName, StepStatus } from "./types";

async function fileExists(p: string): Promise<boolean> {
  try {
    await fs.access(p);
    return true;
  } catch {
    return false;
  }
}

/**
 * Allocate + launch a QC run against the project's confirmed spec and reads.
 * Shared by POST /runs and POST /confirm-spec. Returns the new runId, or an error.
 */
export async function startQcRun(
  projectId: string,
  opts: { useLlm?: boolean; fastqSource?: "control" | "sim"; maxReads?: number | null } = {},
): Promise<{ runId: string } | { error: string }> {
  let project;
  try {
    project = await getProject(projectId);
  } catch {
    return { error: "project not found" };
  }
  const useLlm = opts.useLlm !== false;
  const fastqSource: "control" | "sim" = opts.fastqSource === "control" ? "control" : "sim";
  const maxReads =
    typeof opts.maxReads === "number" && opts.maxReads > 0 ? Math.floor(opts.maxReads) : null;

  // Spec: the project's extracted spec if present, else the packaged reference.
  const specSource =
    project.activeSpecPath && (await fileExists(inProject(projectId, project.activeSpecPath)))
      ? inProject(projectId, project.activeSpecPath)
      : assets.referenceSpec;
  const r1 = fastqSource === "control" ? assets.control.r1 : assets.sim.r1;
  const r2 = fastqSource === "control" ? assets.control.r2 : assets.sim.r2;
  const whitelist = (await fileExists(assets.whitelist)) ? assets.whitelist : null;
  // Ground-truth labels only exist for the simulated dataset (enables the eval panel).
  const labels =
    fastqSource === "sim" && (await fileExists(assets.sim.labels)) ? assets.sim.labels : null;
  if (!(await fileExists(r1)) || !(await fileExists(r2))) {
    return { error: `reads not found for source "${fastqSource}"` };
  }

  const run = await allocateRun(projectId, {
    pipeline: ["qc"],
    options: { useLlm, maxReads, withLabels: !!labels, withWhitelist: !!whitelist, fastqSource },
    inputsSnapshot: { specPath: "", r1, r2, whitelist, labels },
    steps: { qc: { name: "qc", status: "queued", log: "logs/qc.log" } },
    overallStatus: "queued",
  });

  // Snapshot the spec into the run dir for immutable provenance, then record its path.
  const snapshot = path.join(runDir(projectId, run.id), "spec.json");
  await fs.copyFile(specSource, snapshot);
  await updateRun(projectId, run.id, (r) => ({
    ...r,
    inputsSnapshot: { ...r.inputsSnapshot, specPath: snapshot },
  }));

  launchRun(projectId, run.id);
  return { runId: run.id };
}

/** In-memory live-process registry (for cancel) — run.json remains the durable truth. */
const livePids = new Map<string, number>(); // `${projectId}:${runId}:${step}` -> pid
const canceled = new Set<string>(); // `${projectId}:${runId}`

const stepKey = (p: string, r: string, s: string) => `${p}:${r}:${s}`;
const runKey = (p: string, r: string) => `${p}:${r}`;
const now = () => new Date().toISOString();

// ---- crude global concurrency cap (pipeline steps stream whole FASTQs + cost money) ----
const MAX_ACTIVE = 2;
let active = 0;
const waiters: Array<() => void> = [];

async function acquire(): Promise<void> {
  if (active < MAX_ACTIVE) {
    active++;
    return;
  }
  await new Promise<void>((res) => waiters.push(res)); // slot handed over on release
}
function release(): void {
  const w = waiters.shift();
  if (w) w();
  else active--;
}

// ---- argv construction per step (uses the granular module CLIs, never the wrapper) ----

function buildArgs(step: StepName, run: RunRecord, dir: string): string[] {
  const snap = run.inputsSnapshot;
  switch (step) {
    case "qc":
      return [
        "-m",
        "qc",
        "run",
        "--spec",
        snap.specPath,
        "--r1",
        snap.r1,
        "--r2",
        snap.r2,
        "--json-out",
        path.join(dir, "qc_report.json"),
        "--model",
        DEFAULT_MODEL,
        ...(snap.whitelist ? ["--whitelist", snap.whitelist] : []),
        ...(snap.labels ? ["--labels", snap.labels] : []),
        ...(run.options.useLlm ? [] : ["--no-llm"]),
        ...(run.options.maxReads ? ["--max-reads", String(run.options.maxReads)] : []),
      ];
    default:
      // extract / simulate wired in Phase 2
      throw new Error(`step not implemented: ${step}`);
  }
}

async function readQcOverall(dir: string): Promise<QcReport["overall"] | null> {
  try {
    const report = JSON.parse(
      await fs.readFile(path.join(dir, "qc_report.json"), "utf8"),
    ) as QcReport;
    return report.overall ?? null;
  } catch {
    return null;
  }
}

async function runStep(
  projectId: string,
  runId: string,
  step: StepName,
): Promise<StepStatus> {
  const dir = runDir(projectId, runId);
  const logFile = path.join(dir, "logs", `${step}.log`);
  const run = await getRun(projectId, runId);
  const args = buildArgs(step, run, dir);

  await updateRun(projectId, runId, (r) => ({
    ...r,
    steps: {
      ...r.steps,
      [step]: { ...r.steps[step]!, status: "running", startedAt: now() },
    },
  }));

  const started = Date.now();
  const proc = spawnLogged({ cmd: PYTHON, args, cwd: REPO_ROOT, logFile });
  livePids.set(stepKey(projectId, runId, step), proc.pid);
  await updateRun(projectId, runId, (r) => ({
    ...r,
    steps: { ...r.steps, [step]: { ...r.steps[step]!, pid: proc.pid } },
  }));

  const code = await proc.done;
  livePids.delete(stepKey(projectId, runId, step));
  const durationMs = Date.now() - started;

  const wasCanceled = canceled.has(runKey(projectId, runId));
  const status: StepStatus = wasCanceled ? "canceled" : code === 0 ? "succeeded" : "failed";

  const overall = step === "qc" && status === "succeeded" ? await readQcOverall(dir) : undefined;

  await updateRun(projectId, runId, (r) => ({
    ...r,
    overall: overall !== undefined ? overall : r.overall,
    steps: {
      ...r.steps,
      [step]: {
        ...r.steps[step]!,
        status,
        exitCode: code,
        finishedAt: now(),
        durationMs,
        error:
          status === "failed"
            ? `${step} exited with code ${code} — see the log`
            : undefined,
      },
    },
  }));

  return status;
}

async function driveRun(projectId: string, runId: string): Promise<void> {
  await acquire();
  try {
    const run = await updateRun(projectId, runId, (r) => ({
      ...r,
      overallStatus: "running",
      startedAt: now(),
    }));

    for (const step of run.pipeline) {
      if (canceled.has(runKey(projectId, runId))) {
        await finalize(projectId, runId, "canceled");
        return;
      }
      const status = await runStep(projectId, runId, step);
      if (status !== "succeeded") {
        await finalize(projectId, runId, status === "canceled" ? "canceled" : "failed");
        return;
      }
    }
    await finalize(projectId, runId, "succeeded");
  } finally {
    canceled.delete(runKey(projectId, runId));
    release();
  }
}

async function finalize(projectId: string, runId: string, status: StepStatus): Promise<void> {
  await updateRun(projectId, runId, (r) => ({
    ...r,
    overallStatus: status,
    finishedAt: now(),
  }));
}

/** Fire-and-forget launcher. The HTTP request returns immediately; this drives to completion. */
export function launchRun(projectId: string, runId: string): void {
  void driveRun(projectId, runId).catch(async (err) => {
    try {
      await updateRun(projectId, runId, (r) => ({
        ...r,
        overallStatus: "failed",
        finishedAt: now(),
      }));
    } catch {
      /* best effort */
    }
    console.error(`run ${projectId}/${runId} crashed:`, err);
  });
}

/** Request cancellation: flag the run and kill any live step's process group. */
export function cancelRun(projectId: string, runId: string): boolean {
  canceled.add(runKey(projectId, runId));
  let killed = false;
  for (const [k, pid] of livePids) {
    if (k.startsWith(`${projectId}:${runId}:`)) {
      killGroup(pid);
      killed = true;
    }
  }
  return killed;
}
