import { NextResponse } from "next/server";
import { runPreflight } from "@/lib/preflight";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json(await runPreflight());
}
