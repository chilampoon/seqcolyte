"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Loader2 } from "lucide-react";
import { toast } from "sonner";
import type { ImperativePanelHandle } from "react-resizable-panels";
import type { ProjectManifest, RunRecord, StepStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { FilesPanel } from "./files/files-panel";
import { FileViewer, type OpenFile } from "./viewer/file-viewer";
import { Chat } from "./chat/chat";

const VIEWER_OPEN = 36;

export function Workspace({
  project,
  initialRuns,
  hasNotes,
  className,
}: {
  project: ProjectManifest;
  initialRuns: RunRecord[];
  hasNotes: boolean;
  className?: string;
}) {
  const router = useRouter();
  const [runs, setRuns] = useState<RunRecord[]>(initialRuns);
  const [railOpen, setRailOpen] = useState(true);
  const [openFile, setOpenFile] = useState<OpenFile | null>(null);
  const [traceRunId, setTraceRunId] = useState<string | null>(initialRuns[0]?.id ?? null);
  const [confirming, setConfirming] = useState(false);

  const railRef = useRef<ImperativePanelHandle>(null);
  const viewerRef = useRef<ImperativePanelHandle>(null);
  const openFileRef = useRef<OpenFile | null>(null);
  openFileRef.current = openFile;

  // A persisted layout can't leave the viewer expanded with no file to show.
  useEffect(() => {
    const v = viewerRef.current;
    if (v && !openFileRef.current && !v.isCollapsed()) v.collapse();
  }, []);

  const refreshRuns = useCallback(async () => {
    const res = await fetch(`/api/projects/${project.id}/runs`, { cache: "no-store" });
    if (res.ok) setRuns((await res.json()) as RunRecord[]);
  }, [project.id]);

  const showFile = useCallback((f: OpenFile) => {
    setOpenFile(f);
    const v = viewerRef.current;
    if (v && v.isCollapsed()) v.resize(VIEWER_OPEN);
  }, []);

  const closeFile = useCallback(() => {
    setOpenFile(null);
    viewerRef.current?.collapse();
  }, []);

  const toggleRail = useCallback(() => {
    const p = railRef.current;
    if (!p) return;
    if (p.isCollapsed()) p.expand();
    else p.collapse();
  }, []);

  const openSpec = useCallback(() => {
    showFile({ kind: "spec", title: "Extracted spec" });
  }, [showFile]);

  // After an uploaded protocol finishes extraction: reveal the spec + pick up the auto-name.
  const onExtractDone = useCallback(() => {
    void refreshRuns();
    router.refresh();
    openSpec();
  }, [refreshRuns, router, openSpec]);

  // Spec review gate → confirm → launch QC → stream the trace in the chat pane.
  const onConfirmSpec = useCallback(async () => {
    setConfirming(true);
    try {
      const res = await fetch(`/api/projects/${project.id}/confirm-spec`, { method: "POST" });
      const data = (await res.json().catch(() => ({}))) as {
        runId?: string;
        needReads?: boolean;
        error?: string;
      };
      if (!res.ok) {
        toast.error(data.error ?? "Could not confirm the spec");
        return;
      }
      // With reads → QC started (show its trace). Without reads → awaiting_reads
      // (the assistant asks the user to upload FASTQ; QC auto-starts on upload).
      if (data.runId) setTraceRunId(data.runId);
      router.refresh(); // updates phase → hides Confirm button, refreshes gating + chat
    } finally {
      setConfirming(false);
    }
  }, [project.id, router]);

  const onRunDone = useCallback(
    async (status: StepStatus, live: boolean) => {
      await refreshRuns();
      if (status !== "succeeded") return;
      // A run that just finished: reveal its HTML report in the viewer (request 1).
      if (live && traceRunId) {
        showFile({
          kind: "html",
          url: `/api/projects/${project.id}/runs/${traceRunId}/report?format=html`,
          title: "QC report",
        });
      }
      if (project.phase !== "complete") {
        await fetch(`/api/projects/${project.id}`, {
          method: "PATCH",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ phase: "complete" }),
        });
        router.refresh();
      }
    },
    [refreshRuns, project.id, project.phase, router, showFile, traceRunId],
  );

  // On first load, reveal the report of an already-finished run so it's visible without hunting for it
  // in the Files panel (demos load complete, so their report would otherwise stay hidden).
  const autoOpenedRef = useRef(false);
  useEffect(() => {
    if (autoOpenedRef.current) return;
    const latest = runs.find((r) => r.id === project.latestRunId) ?? runs[0];
    if (latest && latest.overallStatus === "succeeded") {
      autoOpenedRef.current = true;
      showFile({
        kind: "html",
        url: `/api/projects/${project.id}/runs/${latest.id}/report?format=html`,
        title: "QC report",
      });
    }
  }, [runs, project.latestRunId, project.id, showFile]);

  const specHeaderAction =
    openFile?.kind === "spec" && project.phase === "awaiting_spec_review" ? (
      <button
        onClick={onConfirmSpec}
        disabled={confirming}
        className="border-primary/40 bg-primary/10 text-primary hover:bg-primary/20 inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs font-medium disabled:opacity-50"
      >
        {confirming ? <Loader2 className="size-3 animate-spin" /> : <Check className="size-3" />}
        Confirm spec
      </button>
    ) : null;

  return (
    <div className={cn("flex min-h-0 flex-col", className)}>
      <ResizablePanelGroup
        direction="horizontal"
        autoSaveId="project-workspace"
        className="min-h-0 flex-1"
      >
      <ResizablePanel
        id="rail"
        order={1}
        ref={railRef}
        collapsible
        collapsedSize={0}
        defaultSize={22}
        minSize={14}
        maxSize={40}
        onCollapse={() => setRailOpen(false)}
        onExpand={() => setRailOpen(true)}
        className="min-w-0"
      >
        <div className="flex h-full min-h-0 flex-col overflow-hidden">
          <div className="border-border/60 flex shrink-0 items-center border-b px-3 py-2.5">
            <h2 className="text-sm font-medium">Files</h2>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-3">
            <FilesPanel project={project} runs={runs} hasNotes={hasNotes} onOpen={showFile} />
          </div>
        </div>
      </ResizablePanel>

      <ResizableHandle withHandle />

      <ResizablePanel
        id="viewer"
        order={2}
        ref={viewerRef}
        collapsible
        collapsedSize={0}
        defaultSize={0}
        minSize={20}
        onCollapse={() => setOpenFile(null)}
        className="min-w-0"
      >
        {openFile && (
          <FileViewer
            projectId={project.id}
            file={openFile}
            onClose={closeFile}
            headerAction={specHeaderAction}
          />
        )}
      </ResizablePanel>

      <ResizableHandle withHandle />

      <ResizablePanel id="chat" order={3} defaultSize={78} minSize={30} className="min-w-0">
        <Chat
          projectId={project.id}
          railOpen={railOpen}
          onToggleRail={toggleRail}
          onExtractDone={onExtractDone}
          onInputsChanged={() => router.refresh()}
          hasSpec={!!project.activeSpecPath}
          phase={project.phase ?? "awaiting_inputs"}
          scripts={project.scripts ?? []}
          onRunStarted={(rid) => {
            setTraceRunId(rid);
            router.refresh();
          }}
          traceRunId={traceRunId}
          onRunDone={onRunDone}
        />
      </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}
