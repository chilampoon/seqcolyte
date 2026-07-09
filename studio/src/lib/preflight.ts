import { CLAUDE_BIN, REPO_ROOT } from "./config";
import { probe } from "./spawn";

export interface PreflightCheck {
  id: string;
  label: string;
  ok: boolean;
  required: boolean;
  detail: string;
  fix?: string;
}

export interface PreflightResult {
  checks: PreflightCheck[];
  ready: boolean; // all *required* checks pass
  repoRoot: string;
}

/**
 * The front page only gates on the one genuinely-global concern: is the Claude
 * CLI available? (Studio reuses the terminal `claude` login — no in-app OAuth;
 * auth is confirmed on the first real call.) Install prerequisites (Rust core,
 * Python) and per-project data (spec, reads, whitelist) are not shown here — a
 * run surfaces a clear error if any is missing.
 */
export async function runPreflight(): Promise<PreflightResult> {
  const claude = await probe(CLAUDE_BIN, ["--version"]);
  const checks: PreflightCheck[] = [
    {
      id: "claude",
      label: "Claude CLI",
      ok: claude.ok,
      required: true,
      detail: claude.ok ? claude.stdout.trim() || "installed" : "not found on PATH",
      fix: "install the Claude CLI and sign in (`claude auth login`)",
    },
  ];

  return { checks, ready: claude.ok, repoRoot: REPO_ROOT };
}
