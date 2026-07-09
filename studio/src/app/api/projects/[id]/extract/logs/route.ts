import { promises as fs } from "node:fs";
import { assertSafeId, inProject } from "@/lib/paths";
import { readExtractState } from "@/lib/extractRunner";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function readFrom(file: string, offset: number): Promise<{ text: string; offset: number }> {
  try {
    const fh = await fs.open(file, "r");
    try {
      const { size } = await fh.stat();
      if (size <= offset) return { text: "", offset };
      const buf = Buffer.alloc(size - offset);
      await fh.read(buf, 0, size - offset, offset);
      return { text: buf.toString("utf8"), offset: size };
    } finally {
      await fh.close();
    }
  } catch {
    return { text: "", offset };
  }
}

/** SSE tail of the extract log until the run reaches a terminal status. */
export async function GET(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  try {
    assertSafeId(id);
  } catch {
    return new Response("bad id", { status: 400 });
  }
  const logFile = inProject(id, "spec/extract.log");
  const enc = new TextEncoder();

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      let offset = 0;
      let closed = false;
      let idleTicks = 0;
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
        // cap ~5 min so a stuck/idle extract can't hold the stream forever
        for (let i = 0; i < 500 && !closed && !req.signal.aborted; i++) {
          const chunk = await readFrom(logFile, offset);
          if (chunk.text) {
            offset = chunk.offset;
            send("log", { text: chunk.text });
          }
          const state = await readExtractState(id);
          const status = state?.status ?? "idle";
          send("status", { status });
          if (status === "succeeded" || status === "failed") {
            const tail = await readFrom(logFile, offset);
            if (tail.text) send("log", { text: tail.text });
            send("done", { status });
            close();
            break;
          }
          if (status === "idle") {
            if (++idleTicks > 3) {
              send("done", { status: "idle" });
              close();
              break;
            }
          } else {
            idleTicks = 0;
          }
          await new Promise((r) => setTimeout(r, 600));
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
