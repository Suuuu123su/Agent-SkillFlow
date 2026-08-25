import fs from "node:fs/promises";
import type { PilotPlan } from "./driver-types.js";

export const GATEWAY_TOKEN = "skillflow-t15-local-token";

export async function writeGatewayConfig(params: {
  readonly configPath: string;
  readonly gatewayPort: number;
  readonly mockPort: number;
  readonly plan: PilotPlan;
  readonly pluginRoot: string;
  readonly rawLogPath: string;
  readonly workspaceRoot: string;
}): Promise<void> {
  const modelRef = "openai/gpt-5.6-luna";
  const config = {
    agents: {
      defaults: {
        workspace: params.workspaceRoot,
        skills: params.plan.skills.map((item) => item.skill_id),
        model: { primary: modelRef },
        models: { [modelRef]: { params: { transport: "sse", openaiWsWarmup: false } } },
      },
    },
    gateway: {
      mode: "local",
      bind: "loopback",
      port: params.gatewayPort,
      auth: { mode: "token", token: GATEWAY_TOKEN },
      controlUi: { enabled: false },
      http: { endpoints: { responses: { enabled: true } } },
    },
    models: {
      mode: "merge",
      providers: {
        openai: {
          baseUrl: `http://127.0.0.1:${params.mockPort}/v1`,
          apiKey: { source: "env", provider: "default", id: "OPENAI_API_KEY" },
          api: "openai-responses",
          request: { allowPrivateNetwork: true },
          models: [
            {
              id: "gpt-5.6-luna",
              name: "gpt-5.6-luna",
              api: "openai-responses",
              reasoning: false,
              input: ["text"],
              cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
              contextWindow: 128000,
              maxTokens: 4096,
            },
          ],
        },
      },
    },
    tools: {
      allow: ["read", "write", "skillflow_safe_sink"],
      fs: { workspaceOnly: true },
    },
    skills: { allowBundled: [] },
    plugins: {
      enabled: true,
      allow: ["skillflow-observer"],
      load: { paths: [params.pluginRoot] },
      entries: {
        "skillflow-observer": {
          enabled: true,
          hooks: { allowConversationAccess: true },
          config: {
            logPath: params.rawLogPath,
            runId: params.plan.run_id,
            taskId: params.plan.task_id,
            workspaceRoot: params.workspaceRoot,
            resources: params.plan.resources,
            skills: params.plan.skills.map((item) => ({
              skillId: item.skill_id,
              relativePath: `skills/${item.skill_id}/SKILL.md`,
            })),
          },
        },
      },
    },
  };
  await fs.writeFile(params.configPath, `${JSON.stringify(config, null, 2)}\n`, {
    encoding: "utf8",
    flag: "wx",
  });
}
