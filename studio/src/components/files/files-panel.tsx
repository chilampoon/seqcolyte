"use client";

import {
  Dna,
  Download,
  Eye,
  FileCode,
  FileJson,
  FileSpreadsheet,
  FileText,
  ScrollText,
  StickyNote,
} from "lucide-react";
import type { ProjectManifest, RunRecord } from "@/lib/types";
import type { OpenFile } from "@/components/viewer/file-viewer";

type Row = {
  icon: typeof FileText;
  label: string;
  sub?: string;
  open?: OpenFile;
  downloadHref?: string;
};

function FileRow({ row, onOpen }: { row: Row; onOpen: (f: OpenFile) => void }) {
  const Icon = row.icon;
  return (
    <div className="border-border/60 flex items-center gap-2 border-b py-2 last:border-b-0">
      <Icon className="text-muted-foreground size-4 shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm">{row.label}</div>
        {row.sub && <div className="text-muted-foreground truncate font-mono text-[11px]">{row.sub}</div>}
      </div>
      {row.open && (
        <button
          onClick={() => onOpen(row.open!)}
          className="text-muted-foreground hover:text-foreground rounded p-1"
          title="Open in viewer"
        >
          <Eye className="size-3.5" />
        </button>
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

/** Map an input file's extension to a viewer kind. */
function docKind(rel: string): OpenFile["kind"] {
  const l = rel.toLowerCase();
  if (l.endsWith(".pdf")) return "pdf";
  return "markdown"; // .md / .txt render as markdown/text
}

export function FilesPanel({
  project,
  runs,
  hasNotes,
  onOpen,
}: {
  project: ProjectManifest;
  runs: RunRecord[];
  /** whether inputs/notes.md has any content — an empty notes file is hidden */
  hasNotes: boolean;
  onOpen: (f: OpenFile) => void;
}) {
  const fileHref = (rel: string) => `/api/projects/${project.id}/files/${rel}`;

  const rows: Row[] = [];
  if (project.inputs.protocolDoc) {
    const rel = project.inputs.protocolDoc;
    rows.push({
      icon: FileText,
      label: "Protocol document",
      sub: rel.split("/").pop(),
      open: { kind: docKind(rel), path: rel, title: rel.split("/").pop() ?? "Protocol" },
      downloadHref: `${fileHref(rel)}?download`,
    });
  }
  for (const t of project.inputs.tables ?? []) {
    rows.push({
      icon: FileSpreadsheet,
      label: "Design table",
      sub: t.split("/").pop(),
      open: { kind: "table", path: t, title: t.split("/").pop() ?? "Table" },
      downloadHref: `${fileHref(t)}?download`,
    });
  }
  const fq = project.inputs.fastq;
  if (fq?.source === "upload") {
    for (const mate of ["r1", "r2"] as const) {
      const rel = fq[mate];
      if (!rel) continue;
      rows.push({
        icon: Dna,
        label: `Reads (${mate.toUpperCase()})`,
        sub: rel.split("/").pop(),
        downloadHref: `${fileHref(rel)}?download`,
      });
    }
  }
  if (project.inputs.notesPath && hasNotes) {
    const rel = project.inputs.notesPath;
    rows.push({
      icon: StickyNote,
      label: "Lab notes",
      sub: rel.split("/").pop(),
      open: { kind: "markdown", path: rel, title: "Lab notes" },
      downloadHref: `${fileHref(rel)}?download`,
    });
  }
  if (project.activeSpecPath) {
    rows.push({
      icon: ScrollText,
      label: "Extracted spec",
      sub: "expected read/library structure",
      open: { kind: "spec", title: "Extracted spec" },
      downloadHref: `${fileHref(project.activeSpecPath)}?download`,
    });
  }
  for (const s of project.scripts ?? []) {
    rows.push({
      icon: FileCode,
      label: s.label,
      sub: `${s.path.split("/").pop()}${s.status === "ran" ? " · applied" : s.status === "failed" ? " · failed" : ""}`,
      open: { kind: "code", path: s.path, title: s.path.split("/").pop() ?? "script" },
      downloadHref: `${fileHref(s.path)}?download`,
    });
  }
  for (const run of runs) {
    if (run.steps.qc?.status === "succeeded" || run.overall != null) {
      const afterFixes = run.options?.fastqSource === "remediated";
      const label = afterFixes ? "QC report (after fixes)" : "QC report";
      rows.push({
        icon: FileJson,
        label,
        sub: `${run.id}${run.overall ? ` · ${run.overall.toUpperCase()}` : ""}`,
        open: {
          kind: "html",
          url: `/api/projects/${project.id}/runs/${run.id}/report?format=html`,
          title: `${label} · ${run.id}`,
        },
        downloadHref: `/api/projects/${project.id}/runs/${run.id}/report?format=html&download`,
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
        <FileRow key={i} row={r} onOpen={onOpen} />
      ))}
    </div>
  );
}
