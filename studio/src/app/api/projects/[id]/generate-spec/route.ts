import { promises as fs } from "node:fs";
import { NextResponse } from "next/server";
import { getProject, updateProject } from "@/lib/store";
import { inProject } from "@/lib/paths";
import { readConversation } from "@/lib/chat";
import { startExtract } from "@/lib/extractRunner";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Build a spec from the user's free-text library description (typed in chat)
 * instead of an uploaded protocol file. Saves the description as the project's
 * lab notes and runs the same extractor `startExtract` uses, so the result flows
 * into the normal review → Confirm-spec → run-QC path. The chat assistant is
 * read-only and cannot do this itself — this is the workspace "Generate spec"
 * button's endpoint.
 */
export async function POST(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  let project;
  try {
    project = await getProject(id);
  } catch {
    return NextResponse.json({ error: "project not found" }, { status: 404 });
  }

  // The description is everything the user typed in chat (minus upload notices).
  const conv = await readConversation(id);
  const description = conv
    .filter((e) => e.role === "user" && !e.text.startsWith("📎"))
    .map((e) => e.text.trim())
    .filter(Boolean)
    .join("\n\n")
    .trim();

  if (description.length < 20) {
    return NextResponse.json(
      {
        error:
          "Describe your library structure in the chat first — read layout (R1/R2), UMI/barcode positions and lengths, and any adapters — then click Generate spec.",
      },
      { status: 400 },
    );
  }

  // Persist as the project's lab notes (shown under Files) and extract from it.
  const rel = project.inputs.notesPath || "inputs/notes.md";
  await fs.mkdir(inProject(id, "inputs"), { recursive: true });
  await fs.writeFile(inProject(id, rel), `${description}\n`, "utf8");
  await updateProject(id, { inputs: { ...project.inputs, notesPath: rel } });

  await startExtract(id, rel);
  return NextResponse.json({ ok: true });
}
