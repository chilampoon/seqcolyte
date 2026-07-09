import readline from "node:readline";
import type { UIMessageStreamWriter } from "ai";

export interface ClaudeStreamMeta {
  sessionId?: string;
  costUsd?: number;
  resultText?: string;
  isError?: boolean;
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n) + `\n… (${s.length - n} more chars)` : s;
}

function stringifyToolResult(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((c) =>
        c && typeof c === "object" && "text" in c
          ? String((c as { text: unknown }).text)
          : JSON.stringify(c),
      )
      .join("\n");
  }
  return JSON.stringify(content);
}

/**
 * Bridge a `claude -p --output-format stream-json --verbose --include-partial-messages`
 * NDJSON stream into AI SDK UI-message chunks.
 *
 * Mapping (verified against claude 2.1.x):
 *  - system/init            -> capture session_id (for --resume)
 *  - stream_event text_delta on a text block -> text-start / text-delta / text-end
 *  - assistant tool_use blocks -> tool-input-available (dynamic)
 *  - user tool_result blocks   -> tool-output-available
 *  - result                 -> capture cost + session + final text
 * thinking blocks and non-text deltas are dropped.
 */
export async function bridgeClaudeStream(
  stdout: NodeJS.ReadableStream,
  writer: UIMessageStreamWriter,
): Promise<ClaudeStreamMeta> {
  const rl = readline.createInterface({ input: stdout, crlfDelay: Infinity });
  const meta: ClaudeStreamMeta = {};

  const openText = new Map<number, string>(); // block index -> text part id
  const emittedTools = new Set<string>();
  let textCounter = 0;

  const closeAllText = () => {
    for (const id of openText.values()) writer.write({ type: "text-end", id });
    openText.clear();
  };

  for await (const raw of rl) {
    const line = raw.trim();
    if (!line) continue;
    let ev: Record<string, unknown>;
    try {
      ev = JSON.parse(line) as Record<string, unknown>;
    } catch {
      continue;
    }

    switch (ev.type) {
      case "system": {
        if (ev.subtype === "init" && typeof ev.session_id === "string") {
          meta.sessionId = ev.session_id;
        }
        break;
      }

      case "stream_event": {
        const e = ev.event as
          | { type: string; index?: number; content_block?: { type?: string }; delta?: { type?: string; text?: string } }
          | undefined;
        if (!e) break;
        const idx = e.index ?? 0;
        if (e.type === "content_block_start") {
          if (e.content_block?.type === "text") {
            const id = `t${textCounter++}`;
            openText.set(idx, id);
            writer.write({ type: "text-start", id });
          }
        } else if (e.type === "content_block_delta") {
          if (e.delta?.type === "text_delta" && openText.has(idx)) {
            writer.write({ type: "text-delta", id: openText.get(idx)!, delta: e.delta.text ?? "" });
          }
        } else if (e.type === "content_block_stop") {
          const id = openText.get(idx);
          if (id) {
            writer.write({ type: "text-end", id });
            openText.delete(idx);
          }
        } else if (e.type === "message_stop") {
          closeAllText();
        }
        break;
      }

      case "assistant": {
        const content = (ev.message as { content?: Array<Record<string, unknown>> } | undefined)?.content ?? [];
        for (const block of content) {
          if (block.type === "tool_use" && typeof block.id === "string" && !emittedTools.has(block.id)) {
            emittedTools.add(block.id);
            writer.write({
              type: "tool-input-available",
              toolCallId: block.id,
              toolName: String(block.name ?? "tool"),
              input: block.input ?? {},
              dynamic: true,
            });
          }
        }
        break;
      }

      case "user": {
        const content =
          (ev.message as { content?: Array<Record<string, unknown>> } | undefined)?.content ??
          (ev.content as Array<Record<string, unknown>> | undefined) ??
          [];
        for (const block of content) {
          if (block.type === "tool_result" && typeof block.tool_use_id === "string") {
            writer.write({
              type: "tool-output-available",
              toolCallId: block.tool_use_id,
              output: truncate(stringifyToolResult(block.content), 4000),
              dynamic: true,
            });
          }
        }
        break;
      }

      case "result": {
        if (typeof ev.session_id === "string") meta.sessionId = ev.session_id;
        if (typeof ev.total_cost_usd === "number") meta.costUsd = ev.total_cost_usd;
        if (typeof ev.result === "string") meta.resultText = ev.result;
        if (ev.is_error === true || ev.subtype === "error_max_turns") meta.isError = true;
        break;
      }
    }
  }

  closeAllText();
  return meta;
}
