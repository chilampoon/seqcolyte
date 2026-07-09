import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  // Lean, self-contained server bundle for Docker/self-hosting.
  output: "standalone",
  // Scope file tracing to this app (it reaches the pipeline via child_process at
  // runtime, not via imports), so the parent repo isn't pulled into the bundle.
  outputFileTracingRoot: path.join(process.cwd()),
};

export default nextConfig;
