import { promises as fs } from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { CLAUDE_BIN, DEFAULT_MODEL, PYTHON, REPO_ROOT } from "./config";
import { assertSafeId, inProject } from "./paths";
import { techSpecPath } from "./technologies";
import { getProject, updateProject } from "./store";
import { appendConversation, readConversation } from "./chat";
import { spawnLogged } from "./spawn";
import type { ProjectManifest, SpecDoc } from "./types";

/**
 * Is this spec id a *known* library structure — one the /technologies gallery
 * lists, or a packaged reference spec? If so a project adopts it as its tag;
 * otherwise the extracted structure is custom and the project stays "new".
 */
async function isKnownStructure(specId: string): Promise<boolean> {
  const exists = async (p: string) => {
    try {
      await fs.access(p);
      return true;
    } catch {
      return false;
    }
  };
  try {
    if (await exists(techSpecPath(specId))) return true; // spec/technologies/{id}.json
    if (await exists(path.join(REPO_ROOT, "spec", `${assertSafeId(specId)}.json`))) return true;
  } catch {
    /* assertSafeId rejected an unsafe id → treat as unknown */
  }
  return false;
}

/**
 * Extract a spec from an uploaded protocol doc via `python -m extract from-doc`.
 * A one-off (not the QC RunRecord model): mirrors runner.ts's spawn/log/update
 * pattern, writing spec/spec.json + a streamable spec/extract.log.
 */

export interface ExtractState {
  status: "running" | "succeeded" | "failed";
  doc: string; // project-relative
  startedAt: string;
  finishedAt?: string;
  specPath?: string; // project-relative
  error?: string;
}

const statePath = (projectId: string) => inProject(projectId, "spec/extract.json");
export const extractLogRel = "spec/extract.log";

const live = new Set<string>();

export async function readExtractState(projectId: string): Promise<ExtractState | null> {
  try {
    return JSON.parse(await fs.readFile(statePath(projectId), "utf8")) as ExtractState;
  } catch {
    return null;
  }
}

async function writeExtractState(projectId: string, s: ExtractState): Promise<void> {
  await fs.mkdir(inProject(projectId, "spec"), { recursive: true });
  await fs.writeFile(statePath(projectId), JSON.stringify(s, null, 2) + "\n");
}

export function isExtracting(projectId: string): boolean {
  return live.has(projectId);
}

/** The user's free-text description (their chat turns, minus the upload markers). */
async function userDescription(projectId: string): Promise<string> {
  const conv = await readConversation(projectId);
  return conv
    .filter((e) => e.role === "user" && !e.text.startsWith("📎 Uploaded"))
    .map((e) => e.text)
    .join("\n")
    .trim();
}

function cleanTitle(raw: string): string {
  return raw
    .trim()
    .split("\n")[0]
    .replace(/^["'`*]+|["'`*.]+$/g, "")
    .trim()
    .slice(0, 120);
}

/**
 * Compose a "{sample} · {assay}" project title from the user's description + the
 * extracted assay via a quick headless claude call. Returns null on any failure
 * (caller falls back to the assay alone). Skips the call when there's no description.
 */
async function composeTitle(assay: string, description: string): Promise<string | null> {
  const desc = description.slice(0, 800).trim();
  if (!desc) return null;
  const prompt =
    `Name a sequencing-QC project. Assay: "${assay}".\n` +
    `The user described their sample/experiment:\n"""\n${desc}\n"""\n\n` +
    `Reply with ONLY a short one-line title (≤6 words) combining the sample with the assay, ` +
    `e.g. "PBMC 1k · 10x 3' GEX". No quotes, no trailing punctuation. ` +
    `If the description names no concrete sample, reply with exactly: ${assay}`;

  return new Promise((resolve) => {
    const child = spawn(
      CLAUDE_BIN,
      [
        "-p",
        prompt,
        "--output-format",
        "json",
        "--model",
        DEFAULT_MODEL,
        // Pure text task — deny every tool.
        "--disallowedTools",
        "Bash",
        "Write",
        "Edit",
        "NotebookEdit",
        "Task",
        "WebFetch",
        "WebSearch",
        "Read",
        "Grep",
        "Glob",
      ],
      { cwd: REPO_ROOT, env: process.env },
    );
    let out = "";
    child.stdout?.on("data", (d: Buffer) => (out += d.toString()));
    const timer = setTimeout(() => {
      try {
        child.kill("SIGTERM");
      } catch {
        /* already gone */
      }
      resolve(null);
    }, 60_000);
    child.on("error", () => {
      clearTimeout(timer);
      resolve(null);
    });
    child.on("exit", (code) => {
      clearTimeout(timer);
      if (code !== 0) return resolve(null);
      try {
        const j = JSON.parse(out) as { result?: unknown };
        const text = typeof j.result === "string" ? cleanTitle(j.result) : "";
        resolve(text || null);
      } catch {
        resolve(null);
      }
    });
  });
}

function summarizeSpec(spec: SpecDoc): string {
  const lines: string[] = [
    "I extracted the expected read/library structure from your protocol — open **Extracted spec** in the Files panel to review it. Here's the gist:",
    "",
  ];
  if (spec.assay) {
    lines.push(`- **Assay:** ${spec.assay}${spec.chemistry_version ? ` (${spec.chemistry_version})` : ""}`);
  }
  const reads = spec.read_structure?.reads ?? [];
  const r1 = reads.find((r) => r.read === "R1");
  if (r1?.segments?.length) {
    const seg = r1.segments
      .map((s) => `${s.name}${s.length ? ` ${s.length} bp` : ""}`)
      .join(" + ");
    lines.push(`- **Read structure:** R1 = ${seg}`);
  }
  if (spec.oligos?.length) {
    const ids = spec.oligos.slice(0, 4).map((o) => o.oligo_id).join(", ");
    lines.push(`- **Oligos:** ${spec.oligos.length} parts${ids ? ` (${ids}…)` : ""}`);
  }
  if (spec.library_generation?.length) {
    lines.push(`- **Library build:** ${spec.library_generation.length} wet-lab steps`);
  }
  lines.push("");
  lines.push(
    "Open **Extracted spec** in the Files panel to inspect the oligos, read structure, and build steps — or just ask me anything about it here.",
  );
  return lines.join("\n");
}

export async function startExtract(projectId: string, docRel: string): Promise<void> {
  if (live.has(projectId)) return;
  live.add(projectId);
  const startedAt = new Date().toISOString();
  const specRel = "spec/spec.json";
  const specAbs = inProject(projectId, specRel);
  const docAbs = inProject(projectId, docRel);
  const logFile = inProject(projectId, extractLogRel);

  await fs.mkdir(inProject(projectId, "spec"), { recursive: true });
  await fs.writeFile(logFile, ""); // truncate previous log
  await writeExtractState(projectId, { status: "running", doc: docRel, startedAt });
  await updateProject(projectId, { phase: "extracting" });

  const args = [
    "-m",
    "extract",
    "from-doc",
    "--doc",
    docAbs,
    // Technology-agnostic inference — respect the protocol's real read structure
    // (custom/novel assays included), not a forced 10x template.
    "--spec",
    "generic",
    "--model",
    DEFAULT_MODEL,
    "--out",
    specAbs,
  ];

  void driveExtract(projectId, docRel, specRel, specAbs, logFile, args, startedAt).finally(() =>
    live.delete(projectId),
  );
}

async function fail(
  projectId: string,
  docRel: string,
  startedAt: string,
  logFile: string,
  reason: string,
): Promise<void> {
  const finishedAt = new Date().toISOString();
  let tail = "";
  try {
    tail = (await fs.readFile(logFile, "utf8")).trim().split("\n").slice(-4).join("\n");
  } catch {
    /* no log */
  }
  await writeExtractState(projectId, {
    status: "failed",
    doc: docRel,
    startedAt,
    finishedAt,
    error: reason,
  });
  await updateProject(projectId, { phase: "awaiting_inputs" });
  await appendConversation(projectId, [
    {
      role: "assistant",
      text:
        `I couldn't extract a spec from that protocol (${reason}). Extraction runs Claude locally, ` +
        `so it needs Claude configured.` +
        (tail ? `\n\nLog tail:\n\n\`\`\`\n${tail}\n\`\`\`` : ""),
      ts: finishedAt,
    },
  ]);
}

async function driveExtract(
  projectId: string,
  docRel: string,
  specRel: string,
  specAbs: string,
  logFile: string,
  args: string[],
  startedAt: string,
): Promise<void> {
  const proc = spawnLogged({ cmd: PYTHON, args, cwd: REPO_ROOT, logFile });
  const code = await proc.done;

  if (code !== 0) {
    await fail(projectId, docRel, startedAt, logFile, `extraction exited with code ${code}`);
    return;
  }

  let spec: SpecDoc | null = null;
  try {
    spec = JSON.parse(await fs.readFile(specAbs, "utf8")) as SpecDoc;
  } catch {
    spec = null;
  }
  if (!spec) {
    await fail(projectId, docRel, startedAt, logFile, "the extractor produced no readable spec");
    return;
  }

  const patch: Partial<ProjectManifest> = {
    activeSpecPath: specRel,
    phase: "awaiting_spec_review",
    specConfirmed: false,
  };
  if (spec.assay) patch.assay = spec.assay;
  if (spec.platform) patch.platform = spec.platform; // nanopore ⇒ single-read flow
  // Adopt the identified id only when it's a known structure; a custom library
  // keeps the neutral "new" tag rather than inventing a fake catalog id.
  if (spec.spec_id && (await isKnownStructure(spec.spec_id))) patch.specId = spec.spec_id;

  // Auto-name only while still "Untitled": "{sample} · {assay}" when the user
  // described a sample, else the assay alone.
  const project = await getProject(projectId);
  if (project.name === "Untitled" && spec.assay) {
    const description = await userDescription(projectId);
    patch.name = (await composeTitle(spec.assay, description)) || spec.assay;
  }
  await updateProject(projectId, patch);

  await writeExtractState(projectId, {
    status: "succeeded",
    doc: docRel,
    startedAt,
    finishedAt: new Date().toISOString(),
    specPath: specRel,
  });
  await appendConversation(projectId, [
    { role: "assistant", text: summarizeSpec(spec), ts: new Date().toISOString() },
  ]);
}
