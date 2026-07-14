import path from "node:path";
import { promises as fs } from "node:fs";
import { assets, DEFAULT_MODEL, PYTHON, REPO_ROOT } from "./config";
import { inProject, runDir } from "./paths";
import { allocateRun, getProject, getRun, updateRun } from "./store";
import { killGroup, spawnLogged } from "./spawn";
import { generateAllFixes } from "./remediate";
import { appendConversation } from "./chat";
import { knowledgeFor } from "./reportHtml";
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
  opts: {
    useLlm?: boolean;
    fastqSource?: "control" | "sim" | "upload" | "remediated";
    maxReads?: number | null;
  } = {},
): Promise<{ runId: string } | { error: string }> {
  let project;
  try {
    project = await getProject(projectId);
  } catch {
    return { error: "project not found" };
  }
  const useLlm = opts.useLlm !== false;
  const fastqSource = (
    ["control", "upload", "remediated"] as const
  ).includes(opts.fastqSource as never)
    ? (opts.fastqSource as "control" | "upload" | "remediated")
    : "sim";
  const maxReads =
    typeof opts.maxReads === "number" && opts.maxReads > 0 ? Math.floor(opts.maxReads) : null;

  // Spec: the project's extracted spec if present, else the packaged reference.
  const specSource =
    project.activeSpecPath && (await fileExists(inProject(projectId, project.activeSpecPath)))
      ? inProject(projectId, project.activeSpecPath)
      : assets.referenceSpec;

  // Nanopore = a single long-read file (no R2, no whitelist); short-read = paired R1/R2.
  const single = project.platform === "nanopore";
  let r1: string, r2: string;
  if (fastqSource === "upload") {
    const fq = project.inputs.fastq;
    if (!fq || fq.source !== "upload" || !fq.r1 || (!single && !fq.r2)) {
      return {
        error: single
          ? "upload your reads FASTQ before running"
          : "upload both R1 and R2 FASTQ before running on your reads",
      };
    }
    r1 = inProject(projectId, fq.r1);
    r2 = single ? "" : inProject(projectId, fq.r2!);
  } else if (fastqSource === "remediated") {
    // Cleaned reads written by a remediation script.
    r1 = inProject(projectId, single ? "remediated/reads.fastq.gz" : "remediated/R1.fastq.gz");
    r2 = single ? "" : inProject(projectId, "remediated/R2.fastq.gz");
  } else {
    r1 = fastqSource === "control" ? assets.control.r1 : assets.sim.r1;
    r2 = fastqSource === "control" ? assets.control.r2 : assets.sim.r2;
  }
  const whitelist = !single && (await fileExists(assets.whitelist)) ? assets.whitelist : null;
  // Ground-truth labels only exist for the simulated (short-read) dataset (enables the eval panel).
  const labels =
    !single && fastqSource === "sim" && (await fileExists(assets.sim.labels)) ? assets.sim.labels : null;
  if (!(await fileExists(r1)) || (!single && !(await fileExists(r2)))) {
    return { error: `reads not found for source "${fastqSource}"` };
  }

  const run = await allocateRun(projectId, {
    pipeline: ["qc"],
    options: {
      useLlm,
      maxReads,
      withLabels: !!labels,
      withWhitelist: !!whitelist,
      fastqSource,
      platform: project.platform,
    },
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
  const jsonOut = path.join(dir, "qc_report.json");
  switch (step) {
    case "qc":
      // Nanopore: the single-long-read QC engine (no --r2 / --whitelist / --max-reads).
      if (run.options.platform === "nanopore") {
        return [
          "-m",
          "qc.nanopore",
          "--spec",
          snap.specPath,
          "--reads",
          snap.r1,
          "--json-out",
          jsonOut,
          "--model",
          DEFAULT_MODEL,
          ...(snap.labels ? ["--labels", snap.labels] : []),
          ...(run.options.useLlm ? [] : ["--no-llm"]),
        ];
      }
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
        jsonOut,
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

/** A conversational diagnosis + suggested-fix summary from the report (posted after each QC run). */
function buildDiagnosisMessage(report: QcReport): string {
  const issues = (report.findings ?? []).filter((f) => f.verdict === "fail" || f.verdict === "warn");
  const verdict = (report.overall ?? "").toUpperCase();
  const lines: string[] = [`**QC complete — overall ${verdict || "done"}.**`];
  const plan = report.plan;
  if (plan?.diagnosis) lines.push(plan.diagnosis);
  else if (plan?.root_cause) lines.push(`Likely root cause: ${plan.root_cause}.`);
  if (issues.length) {
    lines.push("", "**Issues & suggested fixes:**");
    for (const f of issues.slice(0, 6)) {
      const inlineFix = /Fix:/i.test(f.detail);
      const fix = inlineFix ? null : knowledgeFor(f.check_id)?.fix ?? null;
      lines.push(`- **${f.title}** — ${f.detail}${fix ? `\n  _Suggested fix:_ ${fix}` : ""}`);
    }
  } else {
    lines.push("", "All checks passed — the reads are consistent with the expected structure.");
  }
  lines.push(
    "",
    "The full report (root cause + suggested fix per issue) is open in the viewer. Any " +
      "computationally-fixable issue also appears in the **Computational fixes** panel below — tick " +
      "them and Apply to clean the reads and re-score.",
  );
  return lines.join("\n");
}

async function finalize(projectId: string, runId: string, status: StepStatus): Promise<void> {
  if (status === "succeeded") {
    try {
      const report = JSON.parse(
        await fs.readFile(path.join(runDir(projectId, runId), "qc_report.json"), "utf8"),
      ) as QcReport;
      // Post the diagnosis + suggested fixes into the conversation (not only in the report). Awaited
      // BEFORE the status flips so the client's post-run hydrate always sees it.
      await appendConversation(projectId, [
        { role: "assistant", text: buildDiagnosisMessage(report), ts: now() },
      ]);
      // Eager remediation (fire-and-forget): only for a first-pass run, not a re-QC on cleaned reads.
      const cur = await getRun(projectId, runId);
      if (cur.options.fastqSource !== "remediated") generateAllFixes(projectId, report);
    } catch {
      /* best effort — diagnosis/remediation are optional */
    }
  }
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
