import { spawn } from "node:child_process";
import { promises as fs } from "node:fs";
import { CLAUDE_BIN, DEFAULT_MODEL } from "./config";
import { inProject } from "./paths";
import { getProject, updateProject } from "./store";
import type { ProjectManifest, QcFinding, QcReport, ScriptRecord } from "./types";

/** A check family that a generated script can fix (fail/warn only). */
export function isSolvable(checkId: string): boolean {
  return (
    checkId.endsWith("_adapter_readthrough") ||
    checkId.startsWith("anchor_") ||
    checkId === "tso_at_r2_start" ||
    checkId === "r2_polyg_tail" ||
    checkId === "tso_concatemer"
  );
}

/** The fail/warn findings a script can remediate, in a stable apply order (structure → 3' trims). */
export function solvableFindings(report: QcReport): QcFinding[] {
  const rank = (id: string) =>
    id === "tso_concatemer" ? 0 : id.startsWith("anchor_") ? 0 : id === "tso_at_r2_start" ? 1 : id.endsWith("_adapter_readthrough") ? 2 : 3;
  return (report.findings ?? [])
    .filter((f) => (f.verdict === "fail" || f.verdict === "warn") && isSolvable(f.check_id))
    .sort((a, b) => rank(a.check_id) - rank(b.check_id));
}

// ---- serialize manifest script-record writes (parallel generation races updateProject) ----
const locks = new Map<string, Promise<unknown>>();
async function withProjectLock<T>(id: string, fn: () => Promise<T>): Promise<T> {
  const prev = locks.get(id) ?? Promise.resolve();
  let release!: () => void;
  const gate = new Promise<void>((r) => (release = r));
  locks.set(id, prev.then(() => gate).catch(() => gate));
  await prev.catch(() => {});
  try {
    return await fn();
  } finally {
    release();
  }
}

async function upsertScript(projectId: string, rec: ScriptRecord): Promise<void> {
  await withProjectLock(projectId, async () => {
    const p = await getProject(projectId);
    const scripts = [...(p.scripts ?? []).filter((s) => s.checkId !== rec.checkId), rec];
    await updateProject(projectId, { scripts });
  });
}

/**
 * Robustly recover the Python source from a possibly-noisy `claude -p` reply (it sometimes prepends
 * prose or even workflow-authoring ramble like `export const meta`). Prefer a fenced block; else
 * start at the first real code line and drop a trailing fence. Returns null if it doesn't look like a
 * remediation script.
 */
export function extractPythonScript(raw: string): string | null {
  let t = (raw ?? "").trim();
  const fence = t.match(/```(?:python|py)?\s*\n([\s\S]*?)```/i);
  if (fence) {
    t = fence[1].trim();
  } else {
    const lines = t.split("\n");
    const start = lines.findIndex(
      (l) =>
        /^#!/.test(l) ||
        /^\s*(import |from |def |class )/.test(l) ||
        /^[A-Za-z_][A-Za-z0-9_]*\s*=/.test(l),
    );
    if (start > 0) t = lines.slice(start).join("\n");
    t = t.replace(/\n?```[\s\S]*$/, "").trim();
  }
  if (!/\b(import|def)\b/.test(t)) return null;
  if (!/(remediated|sys\.argv|R1_OUT|R2_OUT|READS_OUT)/.test(t)) return null;
  return t;
}

/** Spawn `claude -p` (all tools denied) and return its result text, or null. */
function claudeText(prompt: string): Promise<string | null> {
  return new Promise((resolve) => {
    const child = spawn(
      CLAUDE_BIN,
      [
        "-p", prompt, "--model", DEFAULT_MODEL, "--output-format", "json",
        "--disallowedTools", "Bash", "Write", "Edit", "NotebookEdit", "Task", "WebFetch", "WebSearch", "Read", "Grep", "Glob",
      ],
      { env: process.env },
    );
    let out = "";
    child.stdout?.on("data", (d: Buffer) => (out += d.toString()));
    const timer = setTimeout(() => {
      try {
        child.kill("SIGTERM");
      } catch {
        /* gone */
      }
      resolve(null);
    }, 180_000);
    child.on("error", () => {
      clearTimeout(timer);
      resolve(null);
    });
    child.on("exit", (code) => {
      clearTimeout(timer);
      if (code !== 0) return resolve(null);
      try {
        const j = JSON.parse(out) as { result?: string; is_error?: boolean };
        resolve(j.is_error ? null : typeof j.result === "string" ? j.result : null);
      } catch {
        resolve(null);
      }
    });
  });
}

/** Per-finding fix recipe — FOCUSED (only this fix) so scripts chain/compose cleanly. */
function recipe(f: QcFinding): string {
  const id = f.check_id;
  if (id.endsWith("_adapter_readthrough")) {
    const mate = id.startsWith("r1_") ? "R1" : "R2";
    return (
      `Trim ONLY the 3' read-through adapter from ${mate}: find the adapter stem (>=8 bp overlap, ` +
      `allow 1 mismatch) and cut it plus everything 3' of it; leave reads without it unchanged; do NOT ` +
      `modify the other mate or any 5' bases. Drop a PAIR if either mate falls below 20 bp after trimming.`
    );
  }
  if (id.startsWith("anchor_")) {
    const m = f.detail.match(/carry ([ACGTN]+) at position (\d+)/i);
    const anchor = m?.[1] ?? "the constant anchor";
    const pos = m?.[2] ? Number(m[2]) : 1;
    const read = id.includes("_r2_") ? "R2" : "R1";
    return (
      `Keep ONLY read pairs whose ${read} carries the constant anchor ${anchor} at 1-based position ` +
      `${pos} (0-based offset ${pos - 1}), allowing 1 mismatch; DROP pairs that don't. Do NOT trim or ` +
      `alter the kept reads — keep the anchor and full sequence intact (this fixes the on-target rate).`
    );
  }
  if (id === "tso_at_r2_start")
    return "Trim the leading TSO handle from the 5' start of R2 when present (allow 1 mismatch); leave R1 and adapter-free reads unchanged. Drop a pair if either mate < 20 bp.";
  if (id === "r2_polyg_tail")
    return "Trim 3' poly-G tails from R2 (>=10 G near the 3' end, tolerate a couple of non-G); leave R1 unchanged. Drop a pair if either mate < 20 bp.";
  if (id === "tso_concatemer")
    return "This is a Nanopore long-read library. Reads carrying an INTERNAL copy of the TSO/adapter2 motif (and/or its reverse-complement) are template-switch concatemers / fused molecules. SPLIT each such read at every internal adapter2/TSO junction into its component sub-reads and emit each piece as its own read (append '_1','_2',… to the read id); emit reads without an internal copy unchanged. Use the adapter2/TSO sequence from the spec; ignore terminal (near-either-end) copies (those are the normal flanks, not internal). Drop pieces < 50 bp.";
  return "Apply the appropriate in-silico correction for this finding.";
}

function buildPrompt(f: QcFinding, r1: string, r2: string, specJson: string, single: boolean): string {
  const io = single
    ? `The script runs with cwd = the project directory and MUST read two optional argv paths:\n` +
      `  READS_IN  = sys.argv[1] if len(sys.argv)>1 else "${r1}"\n` +
      `  READS_OUT = sys.argv[2] if len(sys.argv)>2 else "remediated/reads.fastq.gz"\n` +
      `Create the READS_OUT parent dir. Single long-read FASTQ (NOT paired). Print ONE summary line: ` +
      `reads in, reads out, what changed.`
    : `The script runs with cwd = the project directory and MUST read four optional argv paths:\n` +
      `  R1_IN  = sys.argv[1] if len(sys.argv)>1 else "${r1}"\n` +
      `  R2_IN  = sys.argv[2] if len(sys.argv)>2 else "${r2}"\n` +
      `  R1_OUT = sys.argv[3] if len(sys.argv)>3 else "remediated/R1.fastq.gz"\n` +
      `  R2_OUT = sys.argv[4] if len(sys.argv)>4 else "remediated/R2.fastq.gz"\n` +
      `Create the R1_OUT/R2_OUT parent dir. Keep R1/R2 PAIRED (emit both mates for every kept pair, in ` +
      `lockstep). Print ONE summary line: pairs in, pairs out, what changed.`;
  return (
    `You are writing a bioinformatics remediation script. You are NOT authoring a workflow and must ` +
    `NOT use any tool. Output RAW Python 3 source ONLY — the FIRST line must be ` +
    `"#!/usr/bin/env python3"; NO prose, NO markdown fences, NO \`export\`/JS, nothing but the script.\n\n` +
    `Standard library ONLY (gzip + string ops; no numpy/pandas/pysam/cutadapt). ${io} Be deterministic + ` +
    `safe to re-run (overwrite outputs).\n\n` +
    `THE FIX (do ONLY this, nothing else): ${recipe(f)}\n\n` +
    `QC finding (check_id ${f.check_id}): "${f.detail}".\n` +
    `Use the EXACT sequences from this library spec (its oligos + read_structure):\n${specJson.slice(0, 3500)}`
  );
}

/**
 * Author + save one fix script for a finding. Writes a `generating` placeholder immediately, then
 * flips to `generated` (script saved) or `failed`. Safe to call in parallel across findings.
 */
export async function generateFixScript(projectId: string, finding: QcFinding): Promise<void> {
  const checkId = finding.check_id;
  const scriptRel = `scripts/fix_${checkId.replace(/[^a-z0-9_]/gi, "_")}.py`;
  const now = () => new Date().toISOString();
  const base: ScriptRecord = {
    path: scriptRel,
    checkId,
    label: `Fix: ${finding.title}`,
    status: "generating",
    createdAt: now(),
  };
  await upsertScript(projectId, base);

  let project: ProjectManifest;
  try {
    project = await getProject(projectId);
  } catch {
    return;
  }
  const single = project.platform === "nanopore";
  const fq = project.inputs.fastq;
  if (!fq || fq.source !== "upload" || !fq.r1 || (!single && !fq.r2)) {
    await upsertScript(projectId, { ...base, status: "failed" });
    return;
  }
  const specJson = project.activeSpecPath
    ? await fs.readFile(inProject(projectId, project.activeSpecPath), "utf8").catch(() => "")
    : "";

  const raw = await claudeText(buildPrompt(finding, fq.r1, single ? "" : fq.r2 ?? "", specJson, single));
  const script = raw ? extractPythonScript(raw) : null;
  if (!script) {
    await upsertScript(projectId, { ...base, status: "failed" });
    return;
  }
  await fs.mkdir(inProject(projectId, "scripts"), { recursive: true });
  await fs.writeFile(inProject(projectId, scriptRel), script + "\n", "utf8");
  await upsertScript(projectId, { ...base, status: "generated" });
}

/** Fire-and-forget: generate scripts for every solvable finding of a completed run, in parallel. */
export function generateAllFixes(projectId: string, report: QcReport): void {
  for (const f of solvableFindings(report)) {
    void generateFixScript(projectId, f).catch(() => {});
  }
}
