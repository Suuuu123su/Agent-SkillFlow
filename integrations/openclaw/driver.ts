import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import {
  childFailure,
  diagnosticOutput,
  freePort,
  spawnCaptured,
  stopChild,
  waitForHttp,
  type CapturedChild,
} from "./child-process.js";
import { parsePlan } from "./driver-types.js";
import { GATEWAY_TOKEN, writeGatewayConfig } from "./gateway-config.js";
import { waitForTargetEffectEvidence } from "./observation.js";
import { responseControl } from "./response-script.js";
import { openClawSessionKey } from "./session-key.js";

async function main(): Promise<void> {
  const requestPath = requiredArg("--request");
  const outputRoot = path.resolve(requiredArg("--output"));
  const pluginRoot = path.resolve(requiredArg("--plugin"));
  const repoRoot = process.cwd();
  const rawPlan: unknown = JSON.parse(await fs.readFile(requestPath, "utf8"));
  const plan = parsePlan(rawPlan);
  await fs.mkdir(outputRoot, { recursive: false });
  const stateDir = path.join(outputRoot, "state");
  const workspaceRoot = path.join(outputRoot, "workspace");
  const configPath = path.join(stateDir, "openclaw.json");
  const rawLogPath = path.join(outputRoot, "openclaw-events.jsonl");
  const controlPath = path.join(outputRoot, "response-control.json");
  await Promise.all([fs.mkdir(stateDir), fs.mkdir(workspaceRoot)]);
  await stageWorkspace(plan, workspaceRoot);
  const mockPort = await freePort();
  let gatewayPort = await freePort();
  while (gatewayPort === mockPort) gatewayPort = await freePort();
  await writeGatewayConfig({
    configPath,
    gatewayPort,
    mockPort,
    plan,
    pluginRoot,
    rawLogPath,
    workspaceRoot,
  });
  const childEnv: NodeJS.ProcessEnv = {
    ...process.env,
    MOCK_PORT: String(mockPort),
    MOCK_RESPONSE_CONTROL: controlPath,
    OPENAI_API_KEY: "skillflow-t15-local-placeholder",
    OPENCLAW_CONFIG_PATH: configPath,
    OPENCLAW_NO_RESPAWN: "1",
    OPENCLAW_SKIP_CHANNELS: "1",
    OPENCLAW_SKIP_STARTUP_MODEL_PREWARM: "1",
    OPENCLAW_STATE_DIR: stateDir,
  };
  let mock: CapturedChild | undefined;
  let gateway: CapturedChild | undefined;
  try {
    await fs.writeFile(controlPath, JSON.stringify({ text: "T15_BOOT" }), "utf8");
    mock = spawnCaptured(process.execPath, ["scripts/e2e/mock-openai-server.mjs"], {
      cwd: repoRoot,
      env: childEnv,
      label: "mock OpenAI server",
    });
    await waitForHttp(`http://127.0.0.1:${mockPort}/health`, mock);
    gateway = spawnCaptured(
      process.execPath,
      ["dist/index.js", "gateway", "--port", String(gatewayPort), "--bind", "loopback"],
      { cwd: repoRoot, env: childEnv, label: "OpenClaw Gateway" },
    );
    await waitForHttp(`http://127.0.0.1:${gatewayPort}/health`, gateway);
    for (const [index, invocation] of plan.invocations.entries()) {
      if (gateway.child.exitCode !== null) throw childFailure(gateway);
      const version = `${plan.scenario_id}-${index}`;
      await fs.writeFile(
        controlPath,
        `${JSON.stringify(responseControl(invocation, workspaceRoot, version), null, 2)}\n`,
        "utf8",
      );
      await runInvocation(gatewayPort, plan.scenario_id, invocation.session_id, invocation.prompt);
    }
    await waitForTargetEffectEvidence(rawLogPath, plan.target_effect_aliases);
    const stat = await fs.stat(rawLogPath);
    if (stat.size === 0) throw new Error("observer emitted an empty event log");
    await fs.writeFile(
      path.join(outputRoot, "driver-result.json"),
      `${JSON.stringify(
        {
          ok: true,
          scenario_id: plan.scenario_id,
          invocation_count: plan.invocations.length,
          revocation_hook_available: plan.revocations.length === 0,
          real_credentials_used: false,
          external_effects_replaced: true,
          production_state_modified: false,
        },
        null,
        2,
      )}\n`,
      { encoding: "utf8", flag: "wx" },
    );
  } catch (error) {
    if (gateway) {
      const detail = `${errorMessage(error)}\nGateway logs:\n${diagnosticOutput(
        gateway.stdout,
        gateway.stderr,
      )}`;
      throw new Error(detail, { cause: error });
    }
    throw error;
  } finally {
    await stopChild(gateway);
    await stopChild(mock);
  }
}

async function stageWorkspace(plan: ReturnType<typeof parsePlan>, workspaceRoot: string) {
  for (const file of plan.workspace_files) {
    const target = inside(workspaceRoot, file.relative_path);
    await fs.mkdir(path.dirname(target), { recursive: true });
    await fs.writeFile(target, file.content, { encoding: "utf8", flag: "wx" });
  }
  for (const skill of plan.skills) {
    const root = inside(workspaceRoot, `skills/${skill.skill_id}`);
    await fs.mkdir(root, { recursive: true });
    const content = [
      "---",
      `name: ${skill.skill_id}`,
      `description: Deterministic T15 pilot skill ${skill.skill_id}.`,
      "---",
      "",
      "Use only the tool calls supplied by the isolated T15 fake provider.",
      "",
    ].join("\n");
    await fs.writeFile(path.join(root, "SKILL.md"), content, { encoding: "utf8", flag: "wx" });
  }
}

async function runInvocation(
  port: number,
  scenarioId: string,
  session: string,
  prompt: string,
): Promise<void> {
  const response = await fetch(`http://127.0.0.1:${port}/v1/responses`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${GATEWAY_TOKEN}`,
      "content-type": "application/json",
      "x-openclaw-agent": "main",
      "x-openclaw-scopes": "operator.write",
      "x-openclaw-session-key": openClawSessionKey(scenarioId, session),
    },
    body: JSON.stringify({ model: "openclaw/main", input: prompt, stream: false }),
    signal: AbortSignal.timeout(180_000),
  });
  const body = await response.text();
  if (!response.ok) throw new Error(`Gateway response failed (${response.status}): ${body}`);
  if (!body.includes("T15_PILOT_OK")) throw new Error(`unexpected Gateway response: ${body}`);
}

function inside(root: string, relative: string): string {
  const target = path.resolve(root, relative);
  const rel = path.relative(path.resolve(root), target);
  if (!rel || rel === ".." || rel.startsWith(`..${path.sep}`) || path.isAbsolute(rel)) {
    throw new Error(`path escapes T15 workspace: ${relative}`);
  }
  return target;
}

function requiredArg(name: string): string {
  const index = process.argv.indexOf(name);
  const value = index >= 0 ? process.argv[index + 1] : undefined;
  if (!value) throw new Error(`missing ${name}`);
  return value;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

await main();
