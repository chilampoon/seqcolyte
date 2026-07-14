"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, Play, Wrench } from "lucide-react";
import { toast } from "sonner";
import type { QcFinding, ProjectManifest, ScriptRecord } from "@/lib/types";

/** Which failing checks a generated script can fix (MUST mirror remediate.ts isSolvable). */
const isSolvable = (id: string) =>
  id.endsWith("_adapter_readthrough") ||
  id.startsWith("anchor_") ||
  id === "tso_at_r2_start" ||
  id === "r2_polyg_tail" ||
  id === "tso_concatemer";

type FixStatus = ScriptRecord["status"];

/**
 * After a failing QC run, fix scripts are authored EAGERLY in the background (runner.ts finalize).
 * This panel polls their status, lets the user tick which to apply, and composes the selected fixes
 * into one cleaned dataset + one re-QC ("QC report (after fixes)").
 */
export function RemediationPanel({
  projectId,
  runId,
  scripts,
  onRunStarted,
  onChanged,
}: {
  projectId: string;
  runId: string;
  scripts: ScriptRecord[];
  onRunStarted: (runId: string) => void;
  onChanged: () => void;
}) {
  const [fixes, setFixes] = useState<QcFinding[]>([]);
  const [statuses, setStatuses] = useState<Record<string, FixStatus>>(
    Object.fromEntries(scripts.map((s) => [s.checkId, s.status])),
  );
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [applying, setApplying] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastStatusKey = useRef("");

  // Solvable findings from this run's report (fixed once).
  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const r = await fetch(`/api/projects/${projectId}/runs/${runId}/report`, { cache: "no-store" });
        if (!r.ok) return;
        const rep = (await r.json()) as { findings?: QcFinding[] };
        const solv = (rep.findings ?? []).filter(
          (f) => (f.verdict === "fail" || f.verdict === "warn") && isSolvable(f.check_id),
        );
        if (!cancel) setFixes(solv);
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancel = true;
    };
  }, [projectId, runId]);

  // Poll the manifest for script-generation status until every fix resolves.
  useEffect(() => {
    if (fixes.length === 0) return;
    const tick = async () => {
      try {
        const p = (await (
          await fetch(`/api/projects/${projectId}`, { cache: "no-store" })
        ).json()) as ProjectManifest;
        const map = Object.fromEntries((p.scripts ?? []).map((s) => [s.checkId, s.status]));
        const key = JSON.stringify(map);
        setStatuses(map);
        // A status change (…→generated) means a script file now exists — refresh the Files panel.
        if (key !== lastStatusKey.current) {
          lastStatusKey.current = key;
          onChanged();
        }
        const allResolved = fixes.every((f) => {
          const st = map[f.check_id];
          return st === "generated" || st === "ran" || st === "failed";
        });
        if (allResolved && pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch {
        /* transient */
      }
    };
    void tick();
    pollRef.current = setInterval(tick, 3000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = null;
    };
  }, [projectId, fixes]);

  if (fixes.length === 0) return null;

  const statusOf = (id: string): FixStatus => statuses[id] ?? "generating";
  const readyIds = fixes.filter((f) => statusOf(f.check_id) === "generated").map((f) => f.check_id);
  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const apply = async () => {
    const checkIds = [...selected].filter((id) => statusOf(id) === "generated");
    if (checkIds.length === 0) return;
    setApplying(true);
    try {
      const r = await fetch(`/api/projects/${projectId}/scripts/apply`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ checkIds }),
      });
      const d = (await r.json().catch(() => ({}))) as { error?: string; runId?: string };
      if (!r.ok || !d.runId) toast.error(d.error ?? "Could not apply the fixes");
      else {
        onChanged();
        onRunStarted(d.runId);
      }
    } finally {
      setApplying(false);
    }
  };

  const chip = (st: FixStatus) =>
    st === "ran"
      ? { text: "applied", cls: "text-emerald-600 dark:text-emerald-400" }
      : st === "generated"
        ? { text: "ready", cls: "text-emerald-600 dark:text-emerald-400" }
        : st === "failed"
          ? { text: "failed", cls: "text-destructive" }
          : { text: "generating…", cls: "text-muted-foreground" };

  const nSel = [...selected].filter((id) => statusOf(id) === "generated").length;

  // Every solvable finding here has already been fixed and re-scored (e.g. re-opening a completed
  // run whose panel attaches to the after-fixes re-QC). Show that, not a picker of locked checkboxes.
  if (fixes.every((f) => statusOf(f.check_id) === "ran")) {
    return (
      <div className="flex justify-start">
        <div className="bg-muted/50 max-w-[85%] space-y-1.5 rounded-lg px-3 py-2 text-sm">
          <div className="flex items-center gap-1.5 font-medium">
            <Wrench className="size-3.5" /> Computational fixes
          </div>
          <div className="text-muted-foreground text-xs">
            ✓ The suggested fixes were applied — the reads were cleaned and re-scored. Open{" "}
            <span className="font-medium">“QC report (after fixes)”</span> in the Files panel to
            compare against the original.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="bg-muted/50 max-w-[85%] space-y-2 rounded-lg px-3 py-2 text-sm">
        <div className="flex items-center gap-1.5 font-medium">
          <Wrench className="size-3.5" /> Computational fixes
        </div>
        <div className="text-muted-foreground text-xs">
          Fix scripts are generated automatically (in Files — review any of them). Tick the issues to
          fix, then apply them together to clean the reads and re-score.
        </div>
        {fixes.map((f) => {
          const st = statusOf(f.check_id);
          const c = chip(st);
          const ready = st === "generated";
          return (
            <label
              key={f.check_id}
              className={
                "border-border/60 flex items-center gap-2 rounded-md border px-2 py-1.5 " +
                (ready ? "cursor-pointer" : "opacity-70")
              }
            >
              <input
                type="checkbox"
                disabled={!ready || applying}
                checked={selected.has(f.check_id)}
                onChange={() => toggle(f.check_id)}
                className="size-3.5 shrink-0"
              />
              <span className="min-w-0 flex-1 truncate text-xs" title={f.title}>
                {f.title}
              </span>
              <span className={`flex shrink-0 items-center gap-1 text-[11px] ${c.cls}`}>
                {st === "generating" && <Loader2 className="size-3 animate-spin" />}
                {c.text}
              </span>
            </label>
          );
        })}
        <button
          onClick={apply}
          disabled={applying || nSel === 0}
          className="border-primary/40 bg-primary/10 text-primary hover:bg-primary/20 inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs font-medium disabled:opacity-50"
        >
          {applying ? <Loader2 className="size-3 animate-spin" /> : <Play className="size-3" />}
          {applying ? "Applying…" : `Apply ${nSel || ""} fix${nSel === 1 ? "" : "es"} & re-QC`}
        </button>
        {readyIds.length < fixes.length && (
          <div className="text-muted-foreground text-[11px]">Some scripts are still generating…</div>
        )}
      </div>
    </div>
  );
}
