"use client";

import { useEffect, useRef, useState } from "react";
import { CheckCircle2, ChevronRight, FileText, Loader2, Terminal, XCircle } from "lucide-react";
import type { RunRecord, StepStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import { RunLogs } from "@/components/pipeline/run-logs";

const base = (p?: string | null) => (p ? p.split("/").pop() : undefined);

/** The real qc invocation, reconstructed from the run's snapshot for display. */
function buildCommand(run: RunRecord | null): string {
  const s = run?.inputsSnapshot;
  if (run?.options.platform === "nanopore") {
    const parts = [
      "python -m qc.nanopore",
      `  --spec ${base(s?.specPath) ?? "spec.json"}`,
      `  --reads ${base(s?.r1) ?? "reads.fastq.gz"}`,
    ];
    if (s?.labels) parts.push(`  --labels ${base(s.labels)}`);
    if (run?.options.useLlm === false) parts.push("  --no-llm");
    return parts.join(" \\\n");
  }
  const parts = [
    "python -m qc run",
    `  --spec ${base(s?.specPath) ?? "spec.json"}`,
    `  --r1 ${base(s?.r1) ?? "R1.fastq.gz"} --r2 ${base(s?.r2) ?? "R2.fastq.gz"}`,
  ];
  if (s?.whitelist) parts.push(`  --whitelist ${base(s.whitelist)}`);
  if (s?.labels) parts.push(`  --labels ${base(s.labels)}`);
  if (run?.options.useLlm === false) parts.push("  --no-llm");
  return parts.join(" \\\n");
}

/**
 * Renders a QC run as a Claude-Code-style workflow trace inside the chat pane:
 * a step card (title + status + the real command + a collapsible streaming log),
 * culminating in the ranked diagnosis + findings + evidence chain (ResultsPanel).
 */
export function AnalysisTrace({
  projectId,
  runId,
  onRunDone,
}: {
  projectId: string;
  runId: string;
  /** Fires when the run reaches a terminal status; `live` = it finished while watching. */
  onRunDone?: (status: StepStatus, live: boolean) => void;
}) {
  const [run, setRun] = useState<RunRecord | null>(null);
  const [status, setStatus] = useState<StepStatus>("queued");
  const [done, setDone] = useState(false);
  const [showOutput, setShowOutput] = useState(true);
  // True when the run was still in flight on mount → its completion is a live event
  // (so the workspace auto-opens the report; revisiting a finished run does not).
  const liveRef = useRef(false);

  // Chat keys this component by runId, so a new run remounts it with fresh state —
  // the effect only needs to hydrate the initial status.
  useEffect(() => {
    let cancelled = false;
    fetch(`/api/projects/${projectId}/runs/${runId}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((rec: RunRecord | null) => {
        if (cancelled || !rec) return;
        setRun(rec);
        const s = rec.steps.qc?.status ?? rec.overallStatus;
        setStatus(s);
        if (["succeeded", "failed", "canceled", "skipped"].includes(s)) {
          setDone(true);
          setShowOutput(false);
        } else {
          liveRef.current = true;
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [projectId, runId]);

  const running = status === "running" || status === "queued";
  const StatusIcon = status === "succeeded" ? CheckCircle2 : status === "failed" ? XCircle : Terminal;
  const tone =
    status === "succeeded"
      ? "text-emerald-400"
      : status === "failed"
        ? "text-red-400"
        : running
          ? "text-sky-400"
          : "text-muted-foreground";

  return (
    <div className="space-y-3">
      <div className="border-border/60 overflow-hidden rounded-lg border">
        <div className="bg-muted/40 border-border/60 flex items-center gap-2 border-b px-3 py-2">
          {running ? (
            <Loader2 className="size-4 animate-spin text-sky-400" />
          ) : (
            <StatusIcon className={cn("size-4", tone)} />
          )}
          <span className="text-sm font-medium">Run QC pipeline</span>
          <span className={cn("ml-auto text-xs font-medium capitalize", tone)}>
            {running ? "running" : status}
          </span>
        </div>
        <div className="space-y-2 p-3">
          <pre className="border-border/60 overflow-x-auto rounded-md border bg-zinc-950 p-3 font-mono text-[11px] leading-relaxed text-zinc-200">
            <span className="text-zinc-500">$ </span>
            {buildCommand(run)}
          </pre>
          <button
            onClick={() => setShowOutput((o) => !o)}
            className="text-muted-foreground hover:text-foreground flex items-center gap-1 text-xs"
          >
            <ChevronRight className={cn("size-3 transition-transform", showOutput && "rotate-90")} />
            {showOutput ? "Hide output" : "Show output"}
          </button>
          {/* RunLogs stays mounted (so it streams + fires onDone) even when visually collapsed. */}
          <div className={cn(!showOutput && "hidden")}>
            <RunLogs
              projectId={projectId}
              runId={runId}
              step="qc"
              active
              onStatus={(s) => setStatus(s)}
              onDone={(s) => {
                setStatus(s);
                setDone(true);
                setShowOutput(false);
                onRunDone?.(s, liveRef.current);
              }}
            />
          </div>
        </div>
      </div>

      {done && status === "succeeded" && (
        <div className="text-muted-foreground flex items-center gap-2 text-xs">
          <FileText className="size-3.5 text-emerald-400" />
          QC complete — the full report (findings, diagnosis, eval) is available in the viewer
          (open <span className="font-medium">QC report</span> in the Files panel).
        </div>
      )}
    </div>
  );
}
