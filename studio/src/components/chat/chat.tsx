"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import type { UIMessage } from "ai";
import { Streamdown } from "streamdown";
import {
  ArrowUp,
  ChevronRight,
  FileScan,
  Loader2,
  Paperclip,
  PanelLeft,
  Wrench,
} from "lucide-react";
import { toast } from "sonner";
import type { ScriptRecord, StepStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import { AnalysisTrace } from "@/components/trace/analysis-trace";
import { RemediationPanel } from "@/components/chat/remediation-panel";

const UPLOAD_ACCEPT = ".pdf,.txt,.md,.csv,.tsv,.xlsx,.xls,.fastq,.fq,.fastq.gz,.fq.gz,.gz";

/** Concatenated text of a message's text parts (ignores tool parts). */
function messageText(m: UIMessage): string {
  return ((m.parts ?? []) as AnyPart[])
    .filter((p) => p.type === "text")
    .map((p) => p.text ?? "")
    .join("");
}

const fmtMB = (bytes: number) => (bytes / 1e6).toFixed(1);
const uploadPct = (u: { loaded: number; total: number }) =>
  u.total > 0 ? Math.min(100, Math.round((100 * u.loaded) / u.total)) : 0;

/**
 * Stream a file to the server as a raw `application/octet-stream` body (name in
 * the `x-filename` header) and report progress. Two wins over `fetch(FormData)`:
 * `fetch` can't surface upload progress at all, and multipart forces the server
 * to buffer the whole file before writing — the raw body streams straight to
 * disk. `xhr.upload.onprogress` gives bytes-sent; `xhr.send(file)` streams the
 * File without materializing it. Same-origin, so cached Basic-auth credentials
 * ride along automatically.
 */
function xhrUpload(
  url: string,
  file: File,
  onProgress: (loaded: number, total: number) => void,
): Promise<{
  ok: boolean;
  data: { error?: string; filename?: string; extract?: boolean; runId?: string };
}> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.setRequestHeader("x-filename", encodeURIComponent(file.name));
    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable) onProgress(ev.loaded, ev.total);
    };
    xhr.onload = () => {
      let data = {};
      try {
        data = JSON.parse(xhr.responseText || "{}");
      } catch {
        /* non-JSON body (e.g. proxy error) — leave data empty */
      }
      resolve({ ok: xhr.status >= 200 && xhr.status < 300, data });
    };
    xhr.onerror = () => reject(new Error("network error"));
    xhr.onabort = () => reject(new Error("aborted"));
    xhr.send(file);
  });
}

type AnyPart = {
  type: string;
  text?: string;
  toolName?: string;
  input?: unknown;
  output?: unknown;
  state?: string;
};

function ToolPart({ part }: { part: AnyPart }) {
  const [open, setOpen] = useState(false);
  const name = part.toolName ?? part.type.replace(/^tool-/, "");
  const inputStr =
    part.input && typeof part.input === "object"
      ? JSON.stringify(part.input).length > 80
        ? JSON.stringify(part.input).slice(0, 80) + "…"
        : JSON.stringify(part.input)
      : String(part.input ?? "");
  const done = part.state === "output-available" || part.output != null;
  return (
    <div className="border-border/60 bg-muted/30 rounded-md border text-xs">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1.5 px-2 py-1.5 text-left"
      >
        <Wrench className="text-muted-foreground size-3 shrink-0" />
        <span className="font-medium">{name}</span>
        <span className="text-muted-foreground truncate font-mono">{inputStr}</span>
        {!done && <Loader2 className="ml-auto size-3 animate-spin" />}
        {done && (
          <ChevronRight
            className={cn("text-muted-foreground ml-auto size-3 transition-transform", open && "rotate-90")}
          />
        )}
      </button>
      {open && part.output != null && (
        <pre className="border-border/60 max-h-40 overflow-auto border-t px-2 py-1.5 font-mono text-[10px] whitespace-pre-wrap">
          {typeof part.output === "string" ? part.output : JSON.stringify(part.output, null, 2)}
        </pre>
      )}
    </div>
  );
}

function MessageBubble({ message }: { message: UIMessage }) {
  const isUser = message.role === "user";
  const parts = (message.parts ?? []) as AnyPart[];
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] space-y-2 rounded-lg px-3 py-2 text-sm",
          isUser ? "bg-primary text-primary-foreground" : "bg-muted/50",
        )}
      >
        {parts.map((part, i) => {
          if (part.type === "text") {
            // Both roles render markdown; the user bubble inherits its own color.
            return (
              <div
                key={i}
                className={cn(
                  "prose-chat text-sm",
                  isUser && "[&_*]:!text-primary-foreground [&_p]:!my-0",
                )}
              >
                <Streamdown>{part.text ?? ""}</Streamdown>
              </div>
            );
          }
          if (part.type === "dynamic-tool" || part.type.startsWith("tool-")) {
            return <ToolPart key={i} part={part} />;
          }
          return null;
        })}
      </div>
    </div>
  );
}

/**
 * The primary full-height chat surface (promoted from the old right-dock).
 * Same grounded endpoint + hydration + tool rendering; composer pinned bottom.
 */
export function Chat({
  projectId,
  railOpen,
  onToggleRail,
  onExtractDone,
  onInputsChanged,
  hasSpec,
  phase,
  scripts,
  onRunStarted,
  traceRunId,
  onRunDone,
}: {
  projectId: string;
  railOpen: boolean;
  onToggleRail: () => void;
  /** Called after an uploaded protocol finishes extraction (opens the Spec viewer). */
  onExtractDone?: () => void;
  /** Called after any upload changes the project inputs (so the Files panel refreshes). */
  onInputsChanged?: () => void;
  /** Whether the project already has an extracted spec (gates the auto-build). */
  hasSpec?: boolean;
  /** Current project phase (auto-build only fires while gathering inputs). */
  phase?: string;
  /** Remediation scripts on the project (drives the fix panel's Generate/Run state). */
  scripts?: ScriptRecord[];
  /** Fires when an upload auto-starts a QC run (so the workspace shows its trace). */
  onRunStarted?: (runId: string) => void;
  /** When set, the QC run's workflow trace renders in the chat stream. */
  traceRunId?: string | null;
  /** Fires when the traced run reaches a terminal status (`live` = finished while watching). */
  onRunDone?: (status: StepStatus, live: boolean) => void;
}) {
  const [input, setInput] = useState("");
  const [uploading, setUploading] = useState(false);
  const [upload, setUpload] = useState<{ name: string; loaded: number; total: number } | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [doneRunId, setDoneRunId] = useState<string | null>(null);
  const dragDepth = useRef(0);
  const [extract, setExtract] = useState<{ status: string; log: string; doc: string } | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const esRef = useRef<EventSource | null>(null);
  const onExtractDoneRef = useRef(onExtractDone);
  onExtractDoneRef.current = onExtractDone;
  const autoBuildUserCountRef = useRef(0);

  const { messages, sendMessage, status, setMessages } = useChat({
    id: `chat-${projectId}`,
    transport: new DefaultChatTransport({ api: `/api/projects/${projectId}/chat` }),
  });

  // (Re)load the persisted conversation — on mount, and after uploads/extraction
  // append out-of-band messages.
  const hydrate = useCallback(async () => {
    try {
      const d = (await (await fetch(`/api/projects/${projectId}/chat`)).json()) as {
        messages?: UIMessage[];
      };
      if (d.messages?.length) setMessages(d.messages);
    } catch {
      /* keep current */
    }
  }, [projectId, setMessages]);

  useEffect(() => {
    void hydrate();
  }, [hydrate]);

  // A newly-started run appends an out-of-band "Spec confirmed" message — re-pull it.
  // Also reset the "run finished" marker so the remediation panel hides during the new run.
  useEffect(() => {
    setDoneRunId(null);
    if (traceRunId) void hydrate();
  }, [traceRunId, hydrate]);

  // The phase advancing (confirm → awaiting_reads, an auto-started run, …) appends
  // assistant messages server-side — re-pull the conversation so they show.
  useEffect(() => {
    void hydrate();
  }, [phase, hydrate]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, status, extract, traceRunId]);

  useEffect(() => () => esRef.current?.close(), []);

  const busy = status === "submitted" || status === "streaming";

  // Auto-build the spec from the chat description — no button. Fires once per NEW
  // user message while the project has no spec yet and is still gathering inputs.
  // The endpoint silently no-ops (400) until the description is substantive, so a
  // short question won't trigger it; a real library description does.
  useEffect(() => {
    if (status !== "ready" || hasSpec || extract) return;
    if (phase && phase !== "awaiting_inputs") return;
    // Count only real typed descriptions — ignore "📎 Uploaded …" notices (those
    // have their own extraction path) so an upload never double-triggers a build.
    const userCount = messages.filter(
      (m) => m.role === "user" && !messageText(m).startsWith("📎"),
    ).length;
    if (userCount === 0 || userCount === autoBuildUserCountRef.current) return;
    autoBuildUserCountRef.current = userCount;
    void (async () => {
      try {
        const res = await fetch(`/api/projects/${projectId}/generate-spec`, { method: "POST" });
        if (!res.ok) return; // description not substantive yet — retry on the next message
        const d = (await res.json().catch(() => ({}))) as { ok?: boolean };
        if (d.ok) streamExtract("your library description");
      } catch {
        /* ignore — user can upload a protocol file instead */
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, hasSpec, extract, phase, messages, projectId]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    sendMessage({ text });
    setInput("");
  }

  function streamExtract(doc: string) {
    esRef.current?.close();
    setExtract({ status: "running", log: "", doc });
    const es = new EventSource(`/api/projects/${projectId}/extract/logs`);
    esRef.current = es;
    es.addEventListener("log", (ev) => {
      const d = JSON.parse((ev as MessageEvent).data) as { text: string };
      setExtract((x) => (x ? { ...x, log: x.log + d.text } : x));
    });
    es.addEventListener("status", (ev) => {
      const d = JSON.parse((ev as MessageEvent).data) as { status: string };
      setExtract((x) => (x ? { ...x, status: d.status } : x));
    });
    es.addEventListener("done", async () => {
      es.close();
      await hydrate(); // the assistant summary (or failure note) is now a real message
      setExtract(null);
      onExtractDoneRef.current?.();
    });
    es.onerror = () => {
      // browser retries; the server closes cleanly on `done`.
    };
  }

  async function uploadFile(file: File) {
    setUploading(true);
    setUpload({ name: file.name, loaded: 0, total: file.size });
    try {
      const { ok, data } = await xhrUpload(
        `/api/projects/${projectId}/inputs/upload`,
        file,
        (loaded, total) => setUpload({ name: file.name, loaded, total }),
      );
      if (!ok) {
        toast.error(data.error ?? "Upload failed");
        return;
      }
      await hydrate();
      onInputsChanged?.(); // refresh the Files panel (new reads/doc/table appear immediately)
      if (data.runId) onRunStarted?.(data.runId); // an upload auto-started QC → show its trace
      if (data.extract) streamExtract(data.filename ?? file.name);
    } catch {
      toast.error("Upload failed");
    } finally {
      setUploading(false);
      setUpload(null);
    }
  }

  /** Upload one or more files sequentially (keeps R1/R2 slotting deterministic). */
  async function uploadFiles(files: File[]) {
    for (const f of files) await uploadFile(f);
  }

  async function onPickFile(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (files.length) await uploadFiles(files);
  }

  // --- drag-and-drop upload onto the whole chat surface ---
  function hasFiles(e: React.DragEvent): boolean {
    return Array.from(e.dataTransfer?.types ?? []).includes("Files");
  }
  function onDragEnter(e: React.DragEvent) {
    if (!hasFiles(e)) return;
    e.preventDefault();
    dragDepth.current += 1;
    setDragActive(true);
  }
  function onDragOver(e: React.DragEvent) {
    if (hasFiles(e)) e.preventDefault(); // required for the drop event to fire
  }
  function onDragLeave(e: React.DragEvent) {
    if (!hasFiles(e)) return;
    dragDepth.current -= 1;
    if (dragDepth.current <= 0) {
      dragDepth.current = 0;
      setDragActive(false);
    }
  }
  async function onDrop(e: React.DragEvent) {
    if (!hasFiles(e)) return;
    e.preventDefault();
    dragDepth.current = 0;
    setDragActive(false);
    if (uploading) return;
    const files = Array.from(e.dataTransfer.files ?? []);
    if (files.length) await uploadFiles(files);
  }

  return (
    <div
      className="relative flex h-full min-h-0 flex-col overflow-hidden"
      onDragEnter={onDragEnter}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      {dragActive && (
        <div className="border-primary/50 bg-background/80 pointer-events-none absolute inset-2 z-20 flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed backdrop-blur-sm">
          <Paperclip className="text-primary size-6" />
          <div className="text-sm font-medium">Drop to upload</div>
          <div className="text-muted-foreground text-xs">
            protocol (PDF / txt / md), FASTQ reads, or design tables
          </div>
        </div>
      )}
      <header className="border-border/60 flex shrink-0 items-center gap-2 border-b px-3 py-2.5">
        <button
          onClick={onToggleRail}
          title={railOpen ? "Hide files" : "Show files"}
          className="text-muted-foreground hover:text-foreground hover:bg-muted rounded-md p-1"
        >
          <PanelLeft className="size-4" />
        </button>
      </header>

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl space-y-4 px-4 py-6">
          {messages.length === 0 ? (
            <div className="text-muted-foreground py-16 text-center text-sm">
              Loading…
            </div>
          ) : (
            messages.map((m) => <MessageBubble key={m.id} message={m} />)
          )}
          {status === "submitted" && (
            <div className="text-muted-foreground flex items-center gap-2 text-xs">
              <Loader2 className="size-3 animate-spin" /> thinking…
            </div>
          )}
          {extract && (
            <div className="flex justify-start">
              <div className="bg-muted/50 max-w-[85%] space-y-2 rounded-lg px-3 py-2 text-sm">
                <div className="flex items-center gap-2 font-medium">
                  {extract.status === "running" ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <FileScan className="size-3.5" />
                  )}
                  Extracting the expected structure from{" "}
                  <span className="font-mono text-xs">{extract.doc}</span>…
                </div>
                {extract.log && (
                  <pre className="bg-background/60 border-border/60 max-h-40 overflow-auto rounded border p-2 font-mono text-[10px] whitespace-pre-wrap">
                    {extract.log}
                  </pre>
                )}
              </div>
            </div>
          )}
          {traceRunId && (
            <AnalysisTrace
              key={traceRunId}
              projectId={projectId}
              runId={traceRunId}
              onRunDone={(status, live) => {
                if (status === "succeeded") setDoneRunId(traceRunId);
                onRunDone?.(status, live);
              }}
            />
          )}
          {doneRunId && (
            <RemediationPanel
              key={`rem-${doneRunId}`}
              projectId={projectId}
              runId={doneRunId}
              scripts={scripts ?? []}
              onRunStarted={(rid) => onRunStarted?.(rid)}
              onChanged={() => onInputsChanged?.()}
            />
          )}
        </div>
      </div>

      <div className="border-border/60 shrink-0 border-t p-3">
        {upload && (
          <div className="mx-auto mb-2 max-w-3xl">
            <div className="text-muted-foreground mb-1 flex items-center gap-2 text-xs">
              <Loader2 className="size-3 shrink-0 animate-spin" />
              <span className="truncate font-mono">{upload.name}</span>
              <span className="ml-auto shrink-0 tabular-nums">
                {upload.loaded >= upload.total && upload.total > 0
                  ? "finishing…"
                  : `${fmtMB(upload.loaded)} / ${fmtMB(upload.total)} MB · ${uploadPct(upload)}%`}
              </span>
            </div>
            <div className="bg-muted h-1.5 w-full overflow-hidden rounded-full">
              <div
                className="bg-primary h-full rounded-full transition-[width] duration-150 ease-out"
                style={{ width: `${uploadPct(upload)}%` }}
              />
            </div>
          </div>
        )}
        <form onSubmit={submit} className="mx-auto flex max-w-3xl items-end gap-2">
          <input
            ref={fileRef}
            type="file"
            multiple
            accept={UPLOAD_ACCEPT}
            className="hidden"
            onChange={onPickFile}
          />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            title="Attach a protocol, notes, or design tables"
            className="border-input text-muted-foreground hover:text-foreground flex size-10 shrink-0 items-center justify-center rounded-md border disabled:opacity-40"
          >
            {uploading ? <Loader2 className="size-4 animate-spin" /> : <Paperclip className="size-4" />}
          </button>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) submit(e);
            }}
            rows={1}
            placeholder="Describe your experiment, or ask about this project…"
            className="border-input bg-background max-h-40 min-h-10 flex-1 resize-none rounded-md border px-3 py-2 text-sm outline-none focus-visible:ring-1"
          />
          <button
            type="submit"
            disabled={!input.trim() || busy}
            className="bg-primary text-primary-foreground flex size-10 shrink-0 items-center justify-center rounded-md disabled:opacity-40"
          >
            {busy ? <Loader2 className="size-4 animate-spin" /> : <ArrowUp className="size-4" />}
          </button>
        </form>
      </div>
    </div>
  );
}
