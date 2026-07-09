"use client";

import { useEffect, useRef, useState } from "react";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import type { UIMessage } from "ai";
import { Streamdown } from "streamdown";
import { ArrowUp, ChevronRight, Loader2, Sparkles, Wrench } from "lucide-react";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

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
      ? (JSON.stringify(part.input).length > 80
          ? JSON.stringify(part.input).slice(0, 80) + "…"
          : JSON.stringify(part.input))
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
          "max-w-[92%] space-y-2 rounded-lg px-3 py-2 text-sm",
          isUser ? "bg-primary text-primary-foreground" : "bg-muted/50",
        )}
      >
        {parts.map((part, i) => {
          if (part.type === "text") {
            return isUser ? (
              <p key={i} className="whitespace-pre-wrap">
                {part.text}
              </p>
            ) : (
              <div key={i} className="prose-chat text-sm">
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

export function ChatDock({ projectId }: { projectId: string }) {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const { messages, sendMessage, status, setMessages } = useChat({
    id: `chat-${projectId}`,
    transport: new DefaultChatTransport({ api: `/api/projects/${projectId}/chat` }),
  });

  // Hydrate prior conversation on mount.
  useEffect(() => {
    let cancelled = false;
    fetch(`/api/projects/${projectId}/chat`)
      .then((r) => r.json())
      .then((d: { messages?: UIMessage[] }) => {
        if (!cancelled && d.messages?.length) setMessages(d.messages);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [projectId, setMessages]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, status]);

  const busy = status === "submitted" || status === "streaming";

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    sendMessage({ text });
    setInput("");
  }

  return (
    <aside className="h-fit lg:sticky lg:top-6">
      <Card className="flex h-[36rem] flex-col gap-0 py-0">
        <CardHeader className="border-border/60 border-b py-3">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Sparkles className="text-primary size-4" />
            Assistant
          </CardTitle>
        </CardHeader>

        <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-3">
          {messages.length === 0 ? (
            <div className="text-muted-foreground flex h-full items-center justify-center px-4 text-center text-sm">
              Ask about this project — its findings, the diagnosis, or why a check failed. Answers
              are grounded in the run&apos;s actual artifacts.
            </div>
          ) : (
            messages.map((m) => <MessageBubble key={m.id} message={m} />)
          )}
          {status === "submitted" && (
            <div className="text-muted-foreground flex items-center gap-2 text-xs">
              <Loader2 className="size-3 animate-spin" /> thinking…
            </div>
          )}
        </div>

        <form onSubmit={submit} className="border-border/60 flex items-end gap-2 border-t p-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) submit(e);
            }}
            rows={1}
            placeholder="Ask about this project…"
            className="border-input bg-background max-h-32 min-h-9 flex-1 resize-none rounded-md border px-3 py-2 text-sm outline-none focus-visible:ring-1"
          />
          <button
            type="submit"
            disabled={!input.trim() || busy}
            className="bg-primary text-primary-foreground flex size-9 shrink-0 items-center justify-center rounded-md disabled:opacity-40"
          >
            {busy ? <Loader2 className="size-4 animate-spin" /> : <ArrowUp className="size-4" />}
          </button>
        </form>
      </Card>
    </aside>
  );
}
