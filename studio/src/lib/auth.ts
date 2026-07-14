/**
 * Shared HTTP Basic-auth gate (STUDIO_AUTH_USER / STUDIO_AUTH_PASS). Returns true when auth passes
 * or isn't configured (open for local / private use). Used by both the proxy middleware and the
 * upload route — the latter is EXCLUDED from the middleware because Next.js caps a request body that
 * passes through middleware at 10 MiB, which truncates large FASTQ uploads; it enforces auth itself.
 */
export function basicAuthOk(req: Request): boolean {
  const user = process.env.STUDIO_AUTH_USER;
  const pass = process.env.STUDIO_AUTH_PASS;
  if (!user || !pass) return true;
  const [scheme, encoded] = (req.headers.get("authorization") ?? "").split(" ");
  if (scheme !== "Basic" || !encoded) return false;
  let decoded = "";
  try {
    decoded = atob(encoded);
  } catch {
    return false;
  }
  const sep = decoded.indexOf(":");
  return sep !== -1 && decoded.slice(0, sep) === user && decoded.slice(sep + 1) === pass;
}

/** A 401 response with the Basic-auth challenge header. */
export function authChallenge(): Response {
  return new Response("Authentication required", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Seqcolyte Studio"' },
  });
}
