import { NextResponse } from "next/server";
import { createProject, listProjects } from "@/lib/store";
import { ONBOARDING_MESSAGE, appendConversation } from "@/lib/chat";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json(await listProjects());
}

export async function POST(req: Request) {
  // Nameless creation: default to "Untitled" (id stays stable; name is display-only
  // and gets auto-set after extraction, or renamed inline).
  const body = (await req.json().catch(() => ({}))) as { name?: unknown };
  const name = typeof body.name === "string" && body.name.trim() ? body.name.trim() : "Untitled";
  const project = await createProject({ name });
  // Seed the onboarding conversation so the chat opens with a prompt.
  await appendConversation(project.id, [
    { role: "assistant", text: ONBOARDING_MESSAGE, ts: new Date().toISOString() },
  ]);
  return NextResponse.json(project, { status: 201 });
}
