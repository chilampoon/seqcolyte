"use client";

import { useEffect, useRef, useState } from "react";
import type { StepStatus } from "@/lib/types";

/**
 * Streams a run step's log over SSE and renders it terminal-style.
 * The server closes the stream on a terminal status; `onDone` fires then.
 */
export function RunLogs({
  projectId,
  runId,
  step,
  active,
  onStatus,
  onDone,
}: {
  projectId: string;
  runId: string;
  step: string;
  active: boolean;
  onStatus?: (s: StepStatus) => void;
  onDone?: (s: StepStatus) => void;
}) {
  const [log, setLog] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const onStatusRef = useRef(onStatus);
  const onDoneRef = useRef(onDone);
  onStatusRef.current = onStatus;
  onDoneRef.current = onDone;

  useEffect(() => {
    if (!active) return;
    setLog("");
    const url = `/api/projects/${projectId}/runs/${runId}/logs/${step}`;
    const es = new EventSource(url);
    es.addEventListener("log", (ev) => {
      const d = JSON.parse((ev as MessageEvent).data) as { text: string };
      setLog((prev) => prev + d.text);
    });
    es.addEventListener("status", (ev) => {
      const d = JSON.parse((ev as MessageEvent).data) as { status?: StepStatus };
      if (d.status) onStatusRef.current?.(d.status);
    });
    es.addEventListener("done", (ev) => {
      const d = JSON.parse((ev as MessageEvent).data) as { status: StepStatus };
      es.close();
      onDoneRef.current?.(d.status);
    });
    es.onerror = () => {
      // browser auto-retries; the server closes cleanly on `done`.
    };
    return () => es.close();
  }, [projectId, runId, step, active]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [log]);

  return (
    <div
      ref={scrollRef}
      className="border-border/60 max-h-96 overflow-auto rounded-md border bg-zinc-950 p-3 font-mono text-xs leading-relaxed text-zinc-200"
    >
      {log ? (
        <pre className="break-words whitespace-pre-wrap">{log}</pre>
      ) : (
        <span className="text-muted-foreground">Waiting for output…</span>
      )}
    </div>
  );
}
