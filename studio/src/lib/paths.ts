import path from "node:path";
import { STORE_ROOT } from "./config";

/**
 * Path safety. Every id that reaches the filesystem comes (ultimately) from the
 * client, so we validate the shape and assert containment within the store root.
 */
const ID_RE = /^[A-Za-z0-9._-]+$/;

export function assertSafeId(id: string): string {
  if (
    typeof id !== "string" ||
    id.length === 0 ||
    id.length > 128 ||
    id === "." ||
    id === ".." ||
    id.includes("\0") ||
    !ID_RE.test(id)
  ) {
    throw new Error(`invalid id: ${JSON.stringify(id)}`);
  }
  return id;
}

/** Resolve `segments` under `root` and refuse anything that escapes it. */
export function resolveWithin(root: string, ...segments: string[]): string {
  const resolvedRoot = path.resolve(root);
  const p = path.resolve(resolvedRoot, ...segments);
  if (p !== resolvedRoot && !p.startsWith(resolvedRoot + path.sep)) {
    throw new Error("path traversal detected");
  }
  return p;
}

export function projectDir(projectId: string): string {
  return resolveWithin(STORE_ROOT, assertSafeId(projectId));
}

export function runDir(projectId: string, runId: string): string {
  return resolveWithin(projectDir(projectId), "runs", assertSafeId(runId));
}

/** Resolve a project-relative path (e.g. "inputs/notes.md") safely inside the project dir. */
export function inProject(projectId: string, rel: string): string {
  return resolveWithin(projectDir(projectId), rel);
}
