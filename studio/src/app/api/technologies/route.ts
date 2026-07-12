import { NextResponse } from "next/server";
import { listTechnologies } from "@/lib/technologies";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** The technology-wiki gallery index (lightweight card summaries). */
export async function GET() {
  return NextResponse.json(await listTechnologies());
}
