"use client";

import {
  Download,
  Eye,
  FileJson,
  FileSpreadsheet,
  FileText,
  ScrollText,
  StickyNote,
} from "lucide-react";
import type { ProjectManifest, RunRecord } from "@/lib/types";

type Row = {
  icon: typeof FileText;
  label: string;
  sub?: string;
  viewHref?: string;
  downloadHref?: string;
};

function FileRow({ row }: { row: Row }) {
  const Icon = row.icon;
  return (
    <div className="border-border/60 flex items-center gap-2 border-b py-2 last:border-b-0">
      <Icon className="text-muted-foreground size-4 shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm">{row.label}</div>
        {row.sub && <div className="text-muted-foreground truncate font-mono text-[11px]">{row.sub}</div>}
      </div>
      {row.viewHref && (
        <a
          href={row.viewHref}
          target="_blank"
          rel="noreferrer"
          className="text-muted-foreground hover:text-foreground rounded p-1"
          title="View"
        >
          <Eye className="size-3.5" />
        </a>
      )}
      {row.downloadHref && (
        <a
          href={row.downloadHref}
          download
          className="text-muted-foreground hover:text-foreground rounded p-1"
          title="Download"
        >
          <Download className="size-3.5" />
        </a>
      )}
    </div>
  );
}

export function FilesPanel({ project, runs }: { project: ProjectManifest; runs: RunRecord[] }) {
  const fileHref = (rel: string) => `/api/projects/${project.id}/files/${rel}`;

  const rows: Row[] = [];
  if (project.inputs.protocolDoc) {
    rows.push({
      icon: FileText,
      label: "Protocol document",
      sub: project.inputs.protocolDoc.split("/").pop(),
      viewHref: fileHref(project.inputs.protocolDoc),
      downloadHref: `${fileHref(project.inputs.protocolDoc)}?download`,
    });
  }
  for (const t of project.inputs.tables ?? []) {
    rows.push({
      icon: FileSpreadsheet,
      label: "Design table",
      sub: t.split("/").pop(),
      viewHref: fileHref(t),
      downloadHref: `${fileHref(t)}?download`,
    });
  }
  if (project.inputs.notesPath) {
    rows.push({
      icon: StickyNote,
      label: "Lab notes",
      sub: project.inputs.notesPath.split("/").pop(),
      viewHref: fileHref(project.inputs.notesPath),
      downloadHref: `${fileHref(project.inputs.notesPath)}?download`,
    });
  }
  if (project.activeSpecPath) {
    rows.push({
      icon: ScrollText,
      label: "Extracted spec",
      sub: "expected read/library structure",
      viewHref: `/api/projects/${project.id}/spec`,
      downloadHref: `${fileHref(project.activeSpecPath)}?download`,
    });
  }
  for (const run of runs) {
    if (run.steps.qc?.status === "succeeded" || run.overall != null) {
      rows.push({
        icon: FileJson,
        label: "QC report",
        sub: `${run.id}${run.overall ? ` · ${run.overall.toUpperCase()}` : ""}`,
        viewHref: `/api/projects/${project.id}/runs/${run.id}/report`,
        downloadHref: `/api/projects/${project.id}/runs/${run.id}/report`,
      });
    }
  }

  if (rows.length === 0) {
    return (
      <div className="text-muted-foreground py-10 text-center text-sm">
        No files yet — attach a protocol, notes, or design tables in the chat.
      </div>
    );
  }

  return (
    <div className="border-border/60 rounded-lg border px-3">
      {rows.map((r, i) => (
        <FileRow key={i} row={r} />
      ))}
    </div>
  );
}
