import path from "node:path";
import { promises as fs } from "node:fs";
import { REPO_ROOT } from "./config";
import { assertSafeId } from "./paths";

/** A lightweight card summary for the /technologies gallery (from spec/technologies/index.json). */
export interface TechIndexEntry {
  id: string;
  title?: string;
  platform?: string;
  chemistry_version?: string;
  modality?: string | null;
  method_type?: string | null;
  description?: string;
  big_conflict?: boolean;
  oligo_seq_recall?: number | null;
  /** Roadmap state. Absent → treat as "supported" (has a spec file, links to /technologies/{id}). */
  status?: "supported" | "in_progress" | "tbd";
  /** For roadmap (tbd/in_progress) cards: the source paper URL (cards don't link into the wiki). */
  source_url?: string | null;
}

/** Repo-level shared wiki spec collection: <REPO_ROOT>/spec/technologies/. */
export function techDir(): string {
  return path.join(REPO_ROOT, "spec", "technologies");
}

export async function listTechnologies(): Promise<TechIndexEntry[]> {
  try {
    return JSON.parse(await fs.readFile(path.join(techDir(), "index.json"), "utf8"));
  } catch {
    return [];
  }
}

/** Path to one technology's full spec JSON (id validated to prevent traversal). */
export function techSpecPath(id: string): string {
  return path.join(techDir(), `${assertSafeId(id)}.json`);
}
