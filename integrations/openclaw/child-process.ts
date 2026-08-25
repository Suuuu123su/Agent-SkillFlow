import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import net from "node:net";
import { setTimeout as delay } from "node:timers/promises";

export type CapturedChild = {
  readonly child: ChildProcessWithoutNullStreams;
  readonly label: string;
  stdout: string;
  stderr: string;
};

export async function freePort(): Promise<number> {
  return await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 0;
      server.close((error) => (error ? reject(error) : resolve(port)));
    });
  });
}

export function spawnCaptured(
  command: string,
  args: readonly string[],
  options: { readonly cwd: string; readonly env: NodeJS.ProcessEnv; readonly label: string },
): CapturedChild {
  const child = spawn(command, args, {
    cwd: options.cwd,
    env: options.env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  const captured = { child, label: options.label, stdout: "", stderr: "" };
  child.stdout.on("data", (chunk: Buffer) => {
    captured.stdout = bounded(captured.stdout, chunk.toString());
  });
  child.stderr.on("data", (chunk: Buffer) => {
    captured.stderr = bounded(captured.stderr, chunk.toString());
  });
  return captured;
}

export async function waitForHttp(
  url: string,
  child: CapturedChild,
  timeoutMs = 120_000,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (child.child.exitCode !== null) throw childFailure(child);
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(1_000) });
      if (response.ok) return;
    } catch (error) {
      if (!(error instanceof Error) || !isExpectedProbeFailure(error)) throw error;
    }
    await delay(100);
  }
  throw new Error(`${child.label} did not become ready\n${child.stderr}`);
}

export function isExpectedProbeFailure(error: Error): boolean {
  return (
    error instanceof TypeError ||
    (error instanceof DOMException && error.name === "TimeoutError")
  );
}

export async function stopChild(child: CapturedChild | undefined): Promise<void> {
  if (!child || child.child.exitCode !== null) return;
  child.child.kill("SIGTERM");
  const exited = await Promise.race([
    new Promise<boolean>((resolve) => child.child.once("exit", () => resolve(true))),
    delay(5_000).then(() => false),
  ]);
  if (!exited && child.child.exitCode === null) child.child.kill("SIGKILL");
}

export function childFailure(child: CapturedChild): Error {
  return new Error(
    `${child.label} failed with exit ${child.child.exitCode ?? "unknown"}\n` +
      diagnosticOutput(child.stdout, child.stderr),
  );
}

export function diagnosticOutput(stdout: string, stderr: string): string {
  return [stderr, stdout].filter((item) => item.length > 0).join("\n") || "<no output>";
}

function bounded(current: string, chunk: string): string {
  const next = current + chunk;
  return next.length <= 131_072 ? next : next.slice(-131_072);
}
