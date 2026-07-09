import { promises as fs } from "node:fs";
import path from "node:path";
import { assertSafeId, runDir } from "@/lib/paths";
import { getRun } from "@/lib/store";
import type { StepName, StepStatus } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const STEPS: StepName[] = ["extract", "simulate", "qc"];
const TERMINAL: StepStatus[] = ["succeeded", "failed", "canceled", "skipped"];

async function readFrom(
  file: string,
  offset: number,
): Promise<{ text: string; offset: number }> {
  try {
    const fh = await fs.open(file, "r");
    try {
      const { size } = await fh.stat();
      if (size <= offset) return { text: "", offset };
      const len = size - offset;
      const buf = Buffer.alloc(len);
      await fh.read(buf, 0, len, offset);
      return { text: buf.toString("utf8"), offset: size };
    } finally {
      await fh.close();
    }
  } catch {
    return { text: "", offset }; // log file not created yet
  }
}

export async function GET(
  req: Request,
  ctx: { params: Promise<{ id: string; runId: string; step: string }> },
) {
  const { id, runId, step } = await ctx.params;
  try {
    assertSafeId(id);
    assertSafeId(runId);
  } catch {
    return new Response("bad id", { status: 400 });
  }
  if (!STEPS.includes(step as StepName)) {
    return new Response("bad step", { status: 400 });
  }

  const logFile = path.join(runDir(id, runId), "logs", `${step}.log`);
  const startOffset = Number(new URL(req.url).searchParams.get("offset") ?? 0) || 0;
  const enc = new TextEncoder();

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      let offset = startOffset;
      let closed = false;
      const send = (event: string, data: unknown) => {
        if (closed) return;
        try {
          controller.enqueue(enc.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
        } catch {
          closed = true;
        }
      };
      const close = () => {
        if (closed) return;
        closed = true;
        try {
          controller.close();
        } catch {
          /* already closed */
        }
      };
      req.signal.addEventListener("abort", close);

      try {
        // eslint-disable-next-line no-constant-condition
        while (!closed && !req.signal.aborted) {
          const chunk = await readFrom(logFile, offset);
          if (chunk.text) {
            offset = chunk.offset;
            send("log", { text: chunk.text, offset });
          }

          let terminal = false;
          let finalStatus: StepStatus | undefined;
          try {
            const run = await getRun(id, runId);
            const st = run.steps[step as StepName]?.status;
            send("status", {
              step,
              status: st,
              overallStatus: run.overallStatus,
              overall: run.overall ?? null,
            });
            if (st && TERMINAL.includes(st)) {
              terminal = true;
              finalStatus = st;
            }
          } catch {
            /* run.json not readable yet */
          }

          if (terminal) {
            // one last read to flush bytes written just before the process exited
            const tail = await readFrom(logFile, offset);
            if (tail.text) {
              offset = tail.offset;
              send("log", { text: tail.text, offset });
            }
            send("done", { status: finalStatus });
            close();
            break;
          }

          send("ping", { t: offset });
          await new Promise((r) => setTimeout(r, 700));
        }
      } finally {
        close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "content-type": "text/event-stream; charset=utf-8",
      "cache-control": "no-cache, no-transform",
      connection: "keep-alive",
      "x-accel-buffering": "no",
    },
  });
}
