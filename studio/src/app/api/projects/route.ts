import { NextResponse } from "next/server";
import { createProject, listProjects } from "@/lib/store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json(await listProjects());
}

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { name?: unknown };
  const name = typeof body.name === "string" ? body.name.trim() : "";
  if (!name) {
    return NextResponse.json({ error: "name is required" }, { status: 400 });
  }
  const project = await createProject({ name });
  return NextResponse.json(project, { status: 201 });
}
