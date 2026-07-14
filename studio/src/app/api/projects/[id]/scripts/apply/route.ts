import { promises as fs } from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";
import { PYTHON } from "@/lib/config";
import { inProject, projectDir } from "@/lib/paths";
import { getProject, updateProject } from "@/lib/store";
import { appendConversation } from "@/lib/chat";
import { spawnLogged } from "@/lib/spawn";
import { startQcRun } from "@/lib/runner";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Stable apply order: structure/anchor filters → TSO 5' → 3' adapter → poly-G. */
const rank = (id: string) =>
  id.startsWith("anchor_") ? 0 : id === "tso_at_r2_start" ? 1 : id.endsWith("_adapter_readthrough") ? 2 : 3;

/**
 * Apply one or more generated fix scripts, COMPOSED: each script cleans the previous one's output
 * (argv-chained inputs/fastq → … → remediated/R1,R2.fastq.gz), then a single re-QC runs on the
 * cleaned reads. Shell-free (`spawnLogged`), time-capped, explicit/user-triggered.
 */
export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const body = (await req.json().catch(() => ({}))) as { checkIds?: string[] };
  const checkIds = Array.isArray(body.checkIds) ? body.checkIds : [];

  let project;
  try {
    project = await getProject(id);
  } catch {
    return NextResponse.json({ error: "project not found" }, { status: 404 });
  }
  // Nanopore = single long-read file (2 argv paths); short-read = paired (4 argv paths).
  const single = project.platform === "nanopore";
  const fq = project.inputs.fastq;
  if (!fq || fq.source !== "upload" || !fq.r1 || (!single && !fq.r2)) {
    return NextResponse.json({ error: "applying fixes needs your uploaded reads" }, { status: 400 });
  }

  const chosen = (project.scripts ?? [])
    .filter((s) => checkIds.includes(s.checkId) && s.status === "generated")
    .sort((a, b) => rank(a.checkId) - rank(b.checkId));
  if (chosen.length === 0) {
    return NextResponse.json({ error: "select at least one ready fix" }, { status: 400 });
  }

  await fs.mkdir(inProject(id, "remediated"), { recursive: true });
  const tmp: string[] = [];
  let inR1 = fq.r1;
  let inR2 = fq.r2;

  for (let i = 0; i < chosen.length; i++) {
    const last = i === chosen.length - 1;
    const outR1 = single
      ? last
        ? "remediated/reads.fastq.gz"
        : `remediated/.s${i}_reads.fastq.gz`
      : last
        ? "remediated/R1.fastq.gz"
        : `remediated/.s${i}_R1.fastq.gz`;
    const outR2 = single ? "" : last ? "remediated/R2.fastq.gz" : `remediated/.s${i}_R2.fastq.gz`;
    if (!last) tmp.push(outR1, ...(single ? [] : [outR2]));
    const logFile = inProject(id, `scripts/${path.basename(chosen[i].path, ".py")}.log`);
    const proc = spawnLogged({
      cmd: PYTHON,
      args: single
        ? [inProject(id, chosen[i].path), inR1!, outR1]
        : [inProject(id, chosen[i].path), inR1!, inR2!, outR1, outR2],
      cwd: projectDir(id),
      logFile,
    });
    const timer = setTimeout(() => {
      try {
        process.kill(-proc.pid, "SIGTERM");
      } catch {
        /* gone */
      }
    }, 300_000);
    const code = await proc.done;
    clearTimeout(timer);
    if (code !== 0) {
      let tail = "";
      try {
        tail = (await fs.readFile(logFile, "utf8")).trim().split("\n").slice(-3).join("\n");
      } catch {
        /* no log */
      }
      const scripts = (project.scripts ?? []).map((s) =>
        s.checkId === chosen[i].checkId ? { ...s, status: "failed" as const } : s,
      );
      await updateProject(id, { scripts });
      await appendConversation(id, [
        {
          role: "assistant",
          text: `A fix script (**${chosen[i].label.replace(/^Fix: /, "")}**) failed (exit ${code}).${tail ? `\n\n\`\`\`\n${tail}\n\`\`\`` : ""}`,
          ts: new Date().toISOString(),
        },
      ]);
      return NextResponse.json({ error: "a fix script failed — see the chat" }, { status: 400 });
    }
    inR1 = outR1;
    inR2 = outR2;
  }

  // Clean up the intermediate stage files.
  await Promise.all(tmp.map((rel) => fs.rm(inProject(id, rel), { force: true }).catch(() => {})));

  const chosenIds = new Set(chosen.map((s) => s.checkId));
  const scripts = (project.scripts ?? []).map((s) =>
    chosenIds.has(s.checkId) ? { ...s, status: "ran" as const } : s,
  );
  await updateProject(id, { scripts });

  const result = await startQcRun(id, { useLlm: true, fastqSource: "remediated" });
  if ("error" in result) {
    return NextResponse.json({ error: `cleaned reads written, but re-QC failed: ${result.error}` }, { status: 400 });
  }

  await appendConversation(id, [
    {
      role: "assistant",
      text:
        `Applied ${chosen.length} fix${chosen.length > 1 ? "es" : ""} (${chosen
          .map((s) => s.label.replace(/^Fix: /, ""))
          .join(", ")}) ✓ — re-running QC on the cleaned reads now. The **QC report (after fixes)** ` +
        `will show the improvement.`,
      ts: new Date().toISOString(),
    },
  ]);

  return NextResponse.json({ ok: true, runId: result.runId });
}
