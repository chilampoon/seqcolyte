import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Optional basic-auth gate for public deployments. If STUDIO_AUTH_USER and
 * STUDIO_AUTH_PASS are set, every request must carry matching Basic credentials;
 * if they're unset, the app is open (local / private-network use).
 *
 * Studio spawns paid Claude calls and runs a pipeline, so DO set these when the
 * app is reachable from the public internet. The browser attaches the cached
 * Basic credentials to fetch and EventSource (SSE) automatically after sign-in.
 */
export const config = {
  // Run on everything except Next's static assets and the favicon.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};

export function proxy(request: NextRequest) {
  const user = process.env.STUDIO_AUTH_USER;
  const pass = process.env.STUDIO_AUTH_PASS;
  if (!user || !pass) return NextResponse.next();

  const header = request.headers.get("authorization") ?? "";
  const [scheme, encoded] = header.split(" ");
  if (scheme === "Basic" && encoded) {
    let decoded = "";
    try {
      decoded = atob(encoded);
    } catch {
      decoded = "";
    }
    const sep = decoded.indexOf(":");
    if (sep !== -1) {
      const u = decoded.slice(0, sep);
      const p = decoded.slice(sep + 1);
      if (u === user && p === pass) return NextResponse.next();
    }
  }

  return new NextResponse("Authentication required", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Seqcolyte Studio"' },
  });
}
