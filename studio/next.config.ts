import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Lean, self-contained server bundle for Docker/self-hosting. Tracing defaults to
  // this app's own directory (studio/) — the pipeline in the parent repo is reached
  // via child_process at runtime, not via imports, so it isn't bundled.
  output: "standalone",
  // The store layer (src/lib/store.ts) does deliberate dynamic filesystem I/O over the
  // project store at runtime; that makes the bundle tracer conservatively pull the
  // config file into every route trace and warn. Exclude it — it's never imported.
  outputFileTracingExcludes: {
    "**/*": ["next.config.ts", "next.config.js"],
  },
};

export default nextConfig;
