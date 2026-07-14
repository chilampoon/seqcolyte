import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { basicAuthOk } from "@/lib/auth";

/**
 * Optional basic-auth gate for public deployments. If STUDIO_AUTH_USER and
 * STUDIO_AUTH_PASS are set, every request must carry matching Basic credentials;
 * if they're unset, the app is open (local / private-network use).
 *
 * Studio spawns paid Claude calls and runs a pipeline, so DO set these when the
 * app is reachable from the public internet. The browser attaches the cached
 * Basic credentials to fetch and EventSource (SSE) automatically after sign-in.
 *
 * The FASTQ upload route is excluded from the matcher: Next caps a request body
 * that flows through middleware at 10 MiB (which silently truncates large FASTQ),
 * so that route runs `basicAuthOk` itself instead (see src/lib/auth.ts).
 */
export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api/projects/[^/]+/inputs/upload).*)"],
};

export function proxy(request: NextRequest) {
  if (basicAuthOk(request)) return NextResponse.next();
  return new NextResponse("Authentication required", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Seqcolyte Studio"' },
  });
}
