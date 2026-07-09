import {
  execFile,
  spawn,
  type ChildProcess,
  type ProcessEnvOptions,
} from "node:child_process";
import { promisify } from "node:util";
import { closeSync, openSync } from "node:fs";

const execFileP = promisify(execFile);

export interface ProbeResult {
  ok: boolean;
  stdout: string;
  stderr: string;
  code: number | null;
}

/**
 * Fire a short read-only command (e.g. `claude --version`) and capture output.
 * NEVER runs through a shell — cmd + args only, so user input can't be injected.
 */
export async function probe(
  cmd: string,
  args: string[],
  opts: { cwd?: string; timeoutMs?: number } = {},
): Promise<ProbeResult> {
  try {
    const { stdout, stderr } = await execFileP(cmd, args, {
      cwd: opts.cwd,
      timeout: opts.timeoutMs ?? 6000,
      maxBuffer: 4 * 1024 * 1024,
    });
    return { ok: true, stdout, stderr, code: 0 };
  } catch (e) {
    const err = e as { stdout?: string; stderr?: string; code?: number; message?: string };
    return {
      ok: false,
      stdout: err.stdout ?? "",
      stderr: err.stderr ?? err.message ?? String(e),
      code: typeof err.code === "number" ? err.code : null,
    };
  }
}

export interface SpawnedStep {
  pid: number;
  child: ChildProcess;
  /** resolves with the exit code once the process ends (or -1 on spawn error) */
  done: Promise<number>;
}

/**
 * Spawn a long-running step DETACHED (its own process group) with stdout+stderr
 * appended to a log file. Detached so cancel can kill the whole group — the
 * python step spawns Rust/claude children that a bare SIGTERM to the pid misses.
 */
export function spawnLogged(opts: {
  cmd: string;
  args: string[];
  cwd: string;
  logFile: string;
  env?: NodeJS.ProcessEnv;
}): SpawnedStep {
  const fd = openSync(opts.logFile, "a");
  const spawnOpts: ProcessEnvOptions & {
    detached: boolean;
    stdio: ["ignore", number, number];
  } = {
    cwd: opts.cwd,
    detached: true,
    stdio: ["ignore", fd, fd],
    env: { ...process.env, ...opts.env },
  };
  const child = spawn(opts.cmd, opts.args, spawnOpts);

  const done = new Promise<number>((resolve) => {
    let settled = false;
    const finish = (code: number) => {
      if (settled) return;
      settled = true;
      try {
        closeSync(fd);
      } catch {
        /* already closed */
      }
      resolve(code);
    };
    child.on("exit", (code) => finish(code ?? -1));
    child.on("error", () => finish(-1));
  });

  return { pid: child.pid ?? -1, child, done };
}

/** Is a pid still alive? Used to reconcile run state after a dev-server reload. */
export function isAlive(pid: number): boolean {
  if (!pid || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

/** Kill an entire detached process group (pid was the group leader). */
export function killGroup(pid: number, signal: NodeJS.Signals = "SIGTERM"): void {
  if (!pid || pid <= 0) return;
  try {
    process.kill(-pid, signal);
  } catch {
    try {
      process.kill(pid, signal);
    } catch {
      /* already gone */
    }
  }
}
