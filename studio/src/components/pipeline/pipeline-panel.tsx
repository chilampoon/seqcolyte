"use client";

import { useState } from "react";
import {
  Ban,
  CheckCircle2,
  Clock,
  Loader2,
  Play,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import type { RunRecord, StepRecord, StepStatus } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { RunLogs } from "./run-logs";

const STATUS_META: Record<
  StepStatus,
  { label: string; icon: typeof Clock; tone: string }
> = {
  queued: { label: "Queued", icon: Clock, tone: "text-muted-foreground" },
  running: { label: "Running", icon: Loader2, tone: "text-sky-400" },
  succeeded: { label: "Succeeded", icon: CheckCircle2, tone: "text-emerald-400" },
  failed: { label: "Failed", icon: XCircle, tone: "text-red-400" },
  canceled: { label: "Canceled", icon: Ban, tone: "text-muted-foreground" },
  skipped: { label: "Skipped", icon: Ban, tone: "text-muted-foreground" },
};

function StatusChip({ status }: { status: StepStatus }) {
  const m = STATUS_META[status];
  const Icon = m.icon;
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs font-medium", m.tone)}>
      <Icon className={cn("size-3.5", status === "running" && "animate-spin")} />
      {m.label}
    </span>
  );
}

function fmtDuration(ms?: number | null): string {
  if (!ms) return "";
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export function PipelinePanel({
  projectId,
  run,
  busy,
  onStart,
  onStatus,
  onDone,
}: {
  projectId: string;
  run: RunRecord | null;
  busy: boolean;
  onStart: (opts: { useLlm: boolean; fastqSource: "sim" | "control" }) => Promise<void>;
  onStatus: () => void;
  onDone: (status: StepStatus) => void;
}) {
  const [useLlm, setUseLlm] = useState(true);
  const [fastqSource, setFastqSource] = useState<"sim" | "control">("sim");
  const [starting, setStarting] = useState(false);

  const inProgress =
    run?.overallStatus === "running" || run?.overallStatus === "queued";

  async function start() {
    setStarting(true);
    try {
      await onStart({ useLlm, fastqSource });
    } finally {
      setStarting(false);
    }
  }

  async function cancel() {
    if (!run) return;
    await fetch(`/api/projects/${projectId}/runs/${run.id}/cancel`, { method: "POST" });
    toast.info("Cancellation requested");
    onStatus();
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Run the QC pipeline</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-2">
            <Label className="text-xs uppercase tracking-wide text-muted-foreground">
              Reads
            </Label>
            <RadioGroup
              value={fastqSource}
              onValueChange={(v) => setFastqSource(v as "sim" | "control")}
              className="gap-2"
            >
              <label className="border-border hover:bg-muted/40 flex cursor-pointer items-start gap-3 rounded-md border p-3">
                <RadioGroupItem value="sim" id="src-sim" className="mt-0.5" />
                <div>
                  <div className="text-sm font-medium">Adapter-dimer simulation</div>
                  <div className="text-muted-foreground text-xs">
                    Labeled failures injected into the 10x control — enables eval scoring
                    (precision / recall / F1).
                  </div>
                </div>
              </label>
              <label className="border-border hover:bg-muted/40 flex cursor-pointer items-start gap-3 rounded-md border p-3">
                <RadioGroupItem value="control" id="src-control" className="mt-0.5" />
                <div>
                  <div className="text-sm font-medium">Clean control</div>
                  <div className="text-muted-foreground text-xs">
                    The known-good 10x PBMC v3 control (no injected failures).
                  </div>
                </div>
              </label>
            </RadioGroup>
          </div>

          <div className="flex items-center justify-between">
            <div>
              <Label htmlFor="use-llm" className="text-sm">
                AI diagnosis
              </Label>
              <p className="text-muted-foreground text-xs">
                Claude ranks the findings and writes a root-cause narrative (~30s). Off = fast
                deterministic ranking.
              </p>
            </div>
            <Switch id="use-llm" checked={useLlm} onCheckedChange={setUseLlm} />
          </div>

          <Button onClick={start} disabled={busy || starting} className="w-full">
            {busy || starting ? (
              <>
                <Loader2 className="size-4 animate-spin" /> Running…
              </>
            ) : (
              <>
                <Play className="size-4" /> Run QC
              </>
            )}
          </Button>
        </CardContent>
      </Card>

      {run && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="text-sm">
                Run <code className="text-muted-foreground font-mono text-xs">{run.id}</code>
              </CardTitle>
              {inProgress && (
                <Button size="sm" variant="outline" onClick={cancel}>
                  <Ban className="size-3.5" /> Cancel
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {run.pipeline.map((stepName) => {
              const step: StepRecord | undefined = run.steps[stepName];
              if (!step) return null;
              return (
                <div key={stepName} className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium capitalize">{stepName}</span>
                    <div className="flex items-center gap-3">
                      {step.durationMs ? (
                        <span className="text-muted-foreground font-mono text-[11px]">
                          {fmtDuration(step.durationMs)}
                        </span>
                      ) : null}
                      <StatusChip status={step.status} />
                    </div>
                  </div>
                  <RunLogs
                    projectId={projectId}
                    runId={run.id}
                    step={stepName}
                    active
                    onStatus={onStatus}
                    onDone={onDone}
                  />
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
