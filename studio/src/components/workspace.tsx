"use client";

import { useCallback, useState } from "react";
import { toast } from "sonner";
import type { ProjectManifest, RunRecord, StepStatus } from "@/lib/types";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { InputsPanel } from "./inputs/inputs-panel";
import { PipelinePanel } from "./pipeline/pipeline-panel";
import { ResultsPanel } from "./qc/results-panel";
import { SpecPanel } from "./spec/spec-panel";
import { ConclusionsPanel } from "./conclusions/conclusions-panel";
import { ChatDock } from "./chat/chat-dock";

export function Workspace({
  project,
  initialRuns,
}: {
  project: ProjectManifest;
  initialRuns: RunRecord[];
}) {
  const [runs, setRuns] = useState<RunRecord[]>(initialRuns);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(
    initialRuns[0]?.id ?? null,
  );
  const [tab, setTab] = useState<string>(initialRuns[0]?.overall ? "results" : "pipeline");
  const [reloadToken, setReloadToken] = useState(0);
  const [specHighlight, setSpecHighlight] = useState<string | null>(null);
  const [specToken, setSpecToken] = useState(0);
  const [conclusionsToken, setConclusionsToken] = useState(0);

  const navigateToSpec = useCallback((anchorId: string) => {
    setSpecHighlight(anchorId);
    setSpecToken((t) => t + 1);
    setTab("spec");
  }, []);

  const selectedRun = runs.find((r) => r.id === selectedRunId) ?? null;
  const busy = runs.some(
    (r) => r.overallStatus === "running" || r.overallStatus === "queued",
  );

  const refreshRuns = useCallback(async () => {
    const res = await fetch(`/api/projects/${project.id}/runs`, { cache: "no-store" });
    if (res.ok) setRuns((await res.json()) as RunRecord[]);
  }, [project.id]);

  const startRun = useCallback(
    async (opts: { useLlm: boolean; fastqSource: "sim" | "control" }) => {
      const res = await fetch(`/api/projects/${project.id}/runs`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(opts),
      });
      if (!res.ok) {
        const { error } = await res.json().catch(() => ({ error: "unknown error" }));
        toast.error(`Could not start run: ${error}`);
        return;
      }
      const { runId } = (await res.json()) as { runId: string };
      setSelectedRunId(runId);
      setTab("pipeline");
      await refreshRuns();
    },
    [project.id, refreshRuns],
  );

  const onRunDone = useCallback(
    async (status: StepStatus) => {
      await refreshRuns();
      setReloadToken((t) => t + 1);
      if (status === "succeeded") {
        setTab("results");
        toast.success("QC run complete");
      } else if (status === "failed") {
        toast.error("QC run failed — check the log");
      }
    },
    [refreshRuns],
  );

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
      <div className="min-w-0">
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="inputs">Inputs</TabsTrigger>
            <TabsTrigger value="pipeline">Pipeline</TabsTrigger>
            <TabsTrigger value="results">Results</TabsTrigger>
            <TabsTrigger value="spec">Spec</TabsTrigger>
            <TabsTrigger value="conclusions">Conclusions</TabsTrigger>
          </TabsList>

          <TabsContent value="inputs" className="mt-4">
            <InputsPanel project={project} />
          </TabsContent>

          <TabsContent value="pipeline" className="mt-4">
            <PipelinePanel
              projectId={project.id}
              run={selectedRun}
              busy={busy}
              onStart={startRun}
              onStatus={refreshRuns}
              onDone={onRunDone}
            />
          </TabsContent>

          <TabsContent value="results" className="mt-4">
            <ResultsPanel
              projectId={project.id}
              runId={selectedRunId}
              reloadToken={reloadToken}
              onNavigateSpec={navigateToSpec}
              onConclusionAdded={() => setConclusionsToken((t) => t + 1)}
            />
          </TabsContent>

          <TabsContent value="spec" className="mt-4">
            <SpecPanel
              projectId={project.id}
              runId={selectedRunId}
              highlight={specHighlight}
              highlightToken={specToken}
            />
          </TabsContent>

          <TabsContent value="conclusions" className="mt-4">
            <ConclusionsPanel projectId={project.id} reloadToken={conclusionsToken} />
          </TabsContent>
        </Tabs>
      </div>

      <ChatDock projectId={project.id} />
    </div>
  );
}
