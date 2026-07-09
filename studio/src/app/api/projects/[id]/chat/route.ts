import { spawn } from "node:child_process";
import { promises as fs } from "node:fs";
import { createUIMessageStream, createUIMessageStreamResponse, type UIMessage } from "ai";
import { CLAUDE_BIN, DEFAULT_MODEL } from "@/lib/config";
import { inProject, projectDir } from "@/lib/paths";
import { getProject } from "@/lib/store";
import {
  appendConversation,
  buildContext,
  getLatestReport,
  readConversation,
  readSession,
  writeSession,
  type ConversationEntry,
} from "@/lib/chat";
import { bridgeClaudeStream } from "@/lib/claudeStream";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function lastUserText(messages: UIMessage[]): string {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m?.role === "user") {
      return (m.parts ?? [])
        .filter((p): p is { type: "text"; text: string } => p.type === "text")
        .map((p) => p.text)
        .join("")
        .trim();
    }
  }
  return "";
}

/** Load prior turns so the client can hydrate history on mount. */
export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const conv = await readConversation(id);
  const messages = conv.map((e, i) => ({
    id: `h${i}`,
    role: e.role,
    parts: [{ type: "text", text: e.text }],
  }));
  return Response.json({ messages });
}

export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;

  let project;
  try {
    project = await getProject(id);
  } catch {
    return new Response("project not found", { status: 404 });
  }

  const body = (await req.json().catch(() => ({}))) as { messages?: UIMessage[] };
  const userText = lastUserText(body.messages ?? []);
  if (!userText) return new Response("empty message", { status: 400 });

  const session = await readSession(id);
  const resuming = !!session.sessionId;

  // First turn: inject the grounded context preamble. Later turns: --resume keeps context.
  let prompt = userText;
  if (!resuming) {
    let notes = "";
    try {
      notes = await fs.readFile(inProject(id, "inputs/notes.md"), "utf8");
    } catch {
      /* no notes */
    }
    const latest = await getLatestReport(id);
    prompt = buildContext(project, notes, latest) + "\n" + userText;
  }

  const args = [
    "-p",
    prompt,
    "--output-format",
    "stream-json",
    "--verbose",
    "--include-partial-messages",
    "--model",
    DEFAULT_MODEL,
    // Read-only guardrail: allow inspection, hard-deny exec/mutation/network.
    "--allowedTools",
    "Read",
    "Grep",
    "Glob",
    "--disallowedTools",
    "Bash",
    "Write",
    "Edit",
    "NotebookEdit",
    "Task",
    "WebFetch",
    "WebSearch",
  ];
  if (resuming && session.sessionId) args.push("--resume", session.sessionId);

  const child = spawn(CLAUDE_BIN, args, { cwd: projectDir(id), env: process.env });
  let stderr = "";
  child.stderr?.on("data", (d: Buffer) => {
    stderr += d.toString();
  });
  const onAbort = () => {
    try {
      child.kill("SIGTERM");
    } catch {
      /* already gone */
    }
  };
  req.signal.addEventListener("abort", onAbort);

  const stream = createUIMessageStream({
    execute: async ({ writer }) => {
      const meta = await bridgeClaudeStream(child.stdout!, writer);
      const code: number = await new Promise((resolve) => {
        if (child.exitCode != null) resolve(child.exitCode);
        else child.once("exit", (c) => resolve(c ?? -1));
      });

      if (!meta.resultText && !meta.sessionId && code !== 0) {
        writer.write({
          type: "error",
          errorText: `Assistant unavailable (exit ${code}). ${stderr.trim().slice(0, 300)}`,
        });
        return;
      }

      if (meta.sessionId) await writeSession(id, { sessionId: meta.sessionId });
      const now = new Date().toISOString();
      const entries: ConversationEntry[] = [{ role: "user", text: userText, ts: now }];
      if (meta.resultText) {
        entries.push({
          role: "assistant" as const,
          text: meta.resultText,
          ts: now,
          ...(meta.costUsd != null ? { costUsd: meta.costUsd } : {}),
        });
      }
      await appendConversation(id, entries);
    },
    onError: (e) => `chat error: ${String(e)}`,
  });

  return createUIMessageStreamResponse({ stream });
}
