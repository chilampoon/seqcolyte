import { promises as fs } from "node:fs";
import path from "node:path";
import { assertSafeId, projectDir, resolveWithin } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const CONTENT_TYPES: Record<string, string> = {
  ".pdf": "application/pdf",
  ".json": "application/json",
  ".md": "text/markdown; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".log": "text/plain; charset=utf-8",
  ".py": "text/plain; charset=utf-8",
  ".sh": "text/plain; charset=utf-8",
  ".csv": "text/csv; charset=utf-8",
  ".tsv": "text/tab-separated-values; charset=utf-8",
  ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
};

/** Serve a file from within the project dir (path-validated). */
export async function GET(
  req: Request,
  ctx: { params: Promise<{ id: string; path: string[] }> },
) {
  const { id, path: parts } = await ctx.params;
  try {
    assertSafeId(id);
    const abs = resolveWithin(projectDir(id), ...parts); // throws on traversal
    const data = await fs.readFile(abs);
    const ext = path.extname(abs).toLowerCase();
    const download = new URL(req.url).searchParams.get("download") != null;
    return new Response(new Uint8Array(data), {
      headers: {
        "content-type": CONTENT_TYPES[ext] ?? "application/octet-stream",
        "content-disposition": `${download ? "attachment" : "inline"}; filename="${path.basename(abs)}"`,
        "cache-control": "no-store",
      },
    });
  } catch {
    return new Response("not found", { status: 404 });
  }
}
