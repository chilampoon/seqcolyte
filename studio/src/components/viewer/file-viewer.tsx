"use client";

import { useEffect, useState } from "react";
import { Loader2, X } from "lucide-react";
import { Streamdown } from "streamdown";
import { SpecPanel } from "@/components/spec/spec-panel";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

/** A file opened in the middle viewer pane. */
export type OpenFile = {
  kind: "spec" | "pdf" | "markdown" | "table" | "json" | "html";
  /** project-relative path served by /api/projects/[id]/files/[...] (pdf/markdown/table/json) */
  path?: string;
  /** absolute URL to embed directly (html/pdf reports served by their own route) */
  url?: string;
  /** for a run's snapshot spec (else the project's active spec) */
  runId?: string;
  title: string;
};

/** Minimal CSV/TSV parser with quoted-field support. */
function parseDelimited(text: string, delim: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i++;
        } else inQuotes = false;
      } else field += c;
    } else if (c === '"') {
      inQuotes = true;
    } else if (c === delim) {
      row.push(field);
      field = "";
    } else if (c === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (c !== "\r") {
      field += c;
    }
  }
  if (field.length || row.length) {
    row.push(field);
    rows.push(row);
  }
  return rows.filter((r) => r.some((cell) => cell.trim() !== ""));
}

function TableView({ rows }: { rows: string[][] }) {
  if (rows.length === 0) return <p className="text-muted-foreground text-sm">Empty table.</p>;
  const [head, ...body] = rows;
  return (
    <div className="border-border/60 overflow-hidden rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            {head.map((h, i) => (
              <TableHead key={i} className="font-mono text-xs whitespace-nowrap">
                {h}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {body.map((r, ri) => (
            <TableRow key={ri}>
              {head.map((_, ci) => (
                <TableCell key={ci} className="font-mono text-xs whitespace-nowrap">
                  {r[ci] ?? ""}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export function FileViewer({
  projectId,
  file,
  onClose,
  headerAction,
}: {
  projectId: string;
  file: OpenFile;
  onClose: () => void;
  /** Optional action rendered in the header (e.g. the "Confirm spec" button). */
  headerAction?: React.ReactNode;
}) {
  const filesUrl = file.path ? `/api/projects/${projectId}/files/${file.path}` : null;
  const frameSrc = file.url ?? filesUrl; // pdf / html embed target
  const [text, setText] = useState<string | null>(null);
  const [rows, setRows] = useState<string[][] | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");

  useEffect(() => {
    // spec + pdf + html render their content directly (SpecPanel / iframe).
    if (file.kind === "spec" || file.kind === "pdf" || file.kind === "html") return;
    setText(null);
    setRows(null);
    if (!filesUrl) {
      setState("error");
      return;
    }
    let cancelled = false;
    setState("loading");
    (async () => {
      try {
        const lower = (file.path ?? "").toLowerCase();
        if (file.kind === "table") {
          if (lower.endsWith(".xlsx") || lower.endsWith(".xls")) {
            const buf = await (await fetch(filesUrl, { cache: "no-store" })).arrayBuffer();
            const XLSX = await import("xlsx");
            const wb = XLSX.read(buf, { type: "array" });
            const ws = wb.Sheets[wb.SheetNames[0]];
            const aoa = XLSX.utils.sheet_to_json(ws, { header: 1, defval: "" }) as unknown[][];
            if (!cancelled) setRows(aoa.map((r) => r.map((c) => String(c ?? ""))));
          } else {
            const t = await (await fetch(filesUrl, { cache: "no-store" })).text();
            if (!cancelled) setRows(parseDelimited(t, lower.endsWith(".tsv") ? "\t" : ","));
          }
        } else {
          const t = await (await fetch(filesUrl, { cache: "no-store" })).text();
          if (!cancelled) {
            if (file.kind === "json") {
              try {
                setText(JSON.stringify(JSON.parse(t), null, 2));
              } catch {
                setText(t);
              }
            } else {
              setText(t);
            }
          }
        }
        if (!cancelled) setState("idle");
      } catch {
        if (!cancelled) setState("error");
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, file.kind, file.path]);

  const isFrame = file.kind === "pdf" || file.kind === "html";
  const bodyClass = isFrame ? "min-h-0 flex-1" : "min-h-0 flex-1 overflow-auto p-3";

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <header className="border-border/60 flex shrink-0 items-center gap-2 border-b px-3 py-2.5">
        <span className="truncate text-sm font-medium" title={file.title}>
          {file.title}
        </span>
        <div className="ml-auto flex items-center gap-1">
          {headerAction}
          <button
            onClick={onClose}
            title="Close"
            className="text-muted-foreground hover:text-foreground hover:bg-muted rounded-md p-1"
          >
            <X className="size-4" />
          </button>
        </div>
      </header>

      <div className={bodyClass}>
        {file.kind === "spec" && (
          <div className="p-3">
            <SpecPanel
              specUrl={
                file.runId
                  ? `/api/projects/${projectId}/runs/${file.runId}/spec`
                  : `/api/projects/${projectId}/spec`
              }
            />
          </div>
        )}

        {isFrame && frameSrc && (
          <iframe src={frameSrc} title={file.title} className="h-full w-full border-0" />
        )}

        {state === "loading" && !isFrame && file.kind !== "spec" && (
          <div className="text-muted-foreground flex items-center gap-2 py-16 text-sm">
            <Loader2 className="size-4 animate-spin" /> Loading…
          </div>
        )}
        {state === "error" && (
          <div className="text-muted-foreground py-16 text-center text-sm">
            Could not load this file.
          </div>
        )}

        {state === "idle" && file.kind === "markdown" && text != null && (
          <div className="prose-chat text-sm">
            <Streamdown>{text || "_(empty)_"}</Streamdown>
          </div>
        )}
        {state === "idle" && file.kind === "table" && rows != null && <TableView rows={rows} />}
        {state === "idle" && file.kind === "json" && text != null && (
          <pre className="bg-muted/40 overflow-x-auto rounded-md p-3 font-mono text-[11px] whitespace-pre-wrap break-all">
            {text}
          </pre>
        )}
      </div>
    </div>
  );
}
