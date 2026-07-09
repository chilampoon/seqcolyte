import { promises as fs } from "node:fs";
import crypto from "node:crypto";
import path from "node:path";
import { DEFAULT_ASSAY, DEFAULT_SPEC_ID, STORE_ROOT } from "./config";
import { assertSafeId, projectDir, runDir } from "./paths";
import type { ProjectManifest, RunRecord } from "./types";

// ---- low-level json io (atomic write via temp + rename) ----

async function ensureDir(p: string): Promise<void> {
  await fs.mkdir(p, { recursive: true });
}

export async function readJson<T>(p: string): Promise<T> {
  return JSON.parse(await fs.readFile(p, "utf8")) as T;
}

export async function writeJson(p: string, data: unknown): Promise<void> {
  await ensureDir(path.dirname(p));
  const tmp = `${p}.tmp-${crypto.randomBytes(4).toString("hex")}`;
  await fs.writeFile(tmp, JSON.stringify(data, null, 2) + "\n");
  await fs.rename(tmp, p);
}

async function pathExists(p: string): Promise<boolean> {
  try {
    await fs.access(p);
    return true;
  } catch {
    return false;
  }
}

// ---- id helpers ----

function slugify(name: string): string {
  const s = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
  return s || "project";
}

const shortId = (): string => crypto.randomBytes(3).toString("hex");

/** Sortable, filesystem-safe run id: 20260708T153500Z-a1b2c3 */
function newRunId(): string {
  const ts = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
  return `${ts}-${shortId()}`;
}

// ---- projects ----

export const manifestPath = (id: string): string =>
  path.join(projectDir(id), "project.json");

export async function listProjects(): Promise<ProjectManifest[]> {
  await ensureDir(STORE_ROOT);
  const entries = await fs.readdir(STORE_ROOT, { withFileTypes: true });
  const out: ProjectManifest[] = [];
  for (const e of entries) {
    if (!e.isDirectory()) continue;
    try {
      out.push(await readJson<ProjectManifest>(path.join(STORE_ROOT, e.name, "project.json")));
    } catch {
      // not a valid project dir; skip
    }
  }
  out.sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1));
  return out;
}

export async function createProject(input: { name: string }): Promise<ProjectManifest> {
  const now = new Date().toISOString();
  const id = assertSafeId(`${slugify(input.name)}-${shortId()}`);
  const dir = projectDir(id);
  for (const sub of ["inputs", "spec", "runs", "conversation", "conclusions"]) {
    await ensureDir(path.join(dir, sub));
  }
  const manifest: ProjectManifest = {
    schemaVersion: "studio.project.v1",
    id,
    name: input.name.trim() || id,
    assay: DEFAULT_ASSAY,
    specId: DEFAULT_SPEC_ID,
    createdAt: now,
    updatedAt: now,
    activeSpecPath: null,
    inputs: {
      protocolDoc: null,
      notesPath: "inputs/notes.md",
      fastq: { source: "sim", r1: null, r2: null },
    },
    latestRunId: null,
    runIds: [],
  };
  await writeJson(manifestPath(id), manifest);
  await fs.writeFile(path.join(dir, "inputs", "notes.md"), "");
  return manifest;
}

export async function getProject(id: string): Promise<ProjectManifest> {
  return readJson<ProjectManifest>(manifestPath(assertSafeId(id)));
}

export async function projectExists(id: string): Promise<boolean> {
  try {
    return await pathExists(manifestPath(assertSafeId(id)));
  } catch {
    return false;
  }
}

export async function updateProject(
  id: string,
  patch: Partial<ProjectManifest>,
): Promise<ProjectManifest> {
  const cur = await getProject(id);
  const next: ProjectManifest = {
    ...cur,
    ...patch,
    updatedAt: new Date().toISOString(),
  };
  await writeJson(manifestPath(id), next);
  return next;
}

// ---- runs ----

export const runRecordPath = (projectId: string, runId: string): string =>
  path.join(runDir(projectId, runId), "run.json");

export async function allocateRun(
  projectId: string,
  base: Omit<RunRecord, "id" | "projectId" | "createdAt" | "schemaVersion">,
): Promise<RunRecord> {
  const id = newRunId();
  const dir = runDir(projectId, id);
  await ensureDir(path.join(dir, "logs"));
  const run: RunRecord = {
    schemaVersion: "studio.run.v1",
    id,
    projectId,
    createdAt: new Date().toISOString(),
    ...base,
  };
  await writeJson(runRecordPath(projectId, id), run);
  const proj = await getProject(projectId);
  await updateProject(projectId, {
    latestRunId: id,
    runIds: [id, ...proj.runIds],
  });
  return run;
}

export async function getRun(projectId: string, runId: string): Promise<RunRecord> {
  return readJson<RunRecord>(runRecordPath(assertSafeId(projectId), assertSafeId(runId)));
}

export async function writeRun(run: RunRecord): Promise<void> {
  await writeJson(runRecordPath(run.projectId, run.id), run);
}

export async function updateRun(
  projectId: string,
  runId: string,
  mutate: (run: RunRecord) => RunRecord,
): Promise<RunRecord> {
  const cur = await getRun(projectId, runId);
  const next = mutate(cur);
  await writeRun(next);
  return next;
}

export async function listRuns(projectId: string): Promise<RunRecord[]> {
  const proj = await getProject(projectId);
  const out: RunRecord[] = [];
  for (const rid of proj.runIds) {
    try {
      out.push(await getRun(projectId, rid));
    } catch {
      // run dir gone; skip
    }
  }
  return out;
}
