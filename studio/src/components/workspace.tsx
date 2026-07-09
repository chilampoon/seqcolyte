"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import type { ProjectManifest, RunRecord } from "@/lib/types";
import { cn } from "@/lib/utils";
import { FilesPanel } from "./files/files-panel";
import { Chat } from "./chat/chat";

export function Workspace({
  project,
  initialRuns,
  className,
}: {
  project: ProjectManifest;
  initialRuns: RunRecord[];
  className?: string;
}) {
  const router = useRouter();
  const [runs, setRuns] = useState<RunRecord[]>(initialRuns);
  const [railOpen, setRailOpen] = useState(true);

  const refreshRuns = useCallback(async () => {
    const res = await fetch(`/api/projects/${project.id}/runs`, { cache: "no-store" });
    if (res.ok) setRuns((await res.json()) as RunRecord[]);
  }, [project.id]);

  // After an uploaded protocol finishes extraction: refresh so the new spec +
  // auto-name land (server re-render), and pick up any generated artifacts.
  const onExtractDone = useCallback(() => {
    void refreshRuns();
    router.refresh();
  }, [refreshRuns, router]);

  return (
    <div className={cn("flex min-h-0 overflow-hidden", className)}>
      {railOpen && (
        <aside className="border-border/60 flex min-h-0 w-[24rem] min-w-0 shrink-0 flex-col overflow-hidden border-r">
          <div className="border-border/60 flex shrink-0 items-center border-b px-3 py-2.5">
            <h2 className="text-sm font-medium">Files</h2>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-3">
            <FilesPanel project={project} runs={runs} />
          </div>
        </aside>
      )}

      <div className="min-h-0 min-w-0 flex-1 overflow-hidden">
        <Chat
          projectId={project.id}
          railOpen={railOpen}
          onToggleRail={() => setRailOpen((o) => !o)}
          onExtractDone={onExtractDone}
        />
      </div>
    </div>
  );
}
