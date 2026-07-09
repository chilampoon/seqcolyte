import crypto from "node:crypto";
import path from "node:path";
import { projectDir } from "./paths";
import { readJson, writeJson } from "./store";
import type { Conclusion } from "./types";

const file = (projectId: string) =>
  path.join(projectDir(projectId), "conclusions", "conclusions.json");

export async function readConclusions(projectId: string): Promise<Conclusion[]> {
  try {
    const d = await readJson<{ items: Conclusion[] }>(file(projectId));
    return d.items ?? [];
  } catch {
    return [];
  }
}

export async function addConclusion(
  projectId: string,
  input: Omit<Conclusion, "id" | "createdAt">,
): Promise<Conclusion> {
  const items = await readConclusions(projectId);
  const c: Conclusion = {
    id: crypto.randomBytes(4).toString("hex"),
    createdAt: new Date().toISOString(),
    ...input,
  };
  await writeJson(file(projectId), { items: [c, ...items] });
  return c;
}

export async function deleteConclusion(projectId: string, cid: string): Promise<void> {
  const items = await readConclusions(projectId);
  await writeJson(file(projectId), { items: items.filter((c) => c.id !== cid) });
}
