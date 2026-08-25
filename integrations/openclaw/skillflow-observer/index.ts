import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { jsonResult } from "openclaw/plugin-sdk/tool-results";
import {
  EventLog,
  parseObserverConfig,
  parseSafeSinkArgs,
  type EventFields,
  type ResourceFact,
} from "./event-log.js";
import { parseAvailableSkills, sessionId, toolRelativePath } from "./paths.js";
import { advertisedPlannedSkill } from "./skill-binding.js";

const SAFE_SINK = "skillflow_safe_sink";

export default definePluginEntry({
  id: "skillflow-observer",
  name: "SkillFlow T15 Observer",
  description: "Bounded four-hook observer and receipt-only safe sink.",
  register(api) {
    const config = parseObserverConfig(api.pluginConfig);
    const log = new EventLog(config);
    const plannedSkillIds = new Set(config.skills.map((skill) => skill.skillId));
    const loadedBySession = new Map<string, Set<string>>();
    const activeSkillByRun = new Map<string, string>();

    api.registerTool({
      label: "SkillFlow Safe Sink",
      name: SAFE_SINK,
      description: "Records a mock:// effect and returns a receipt without external I/O.",
      parameters: {
        type: "object",
        additionalProperties: false,
        required: ["effect_alias", "action", "source", "sink", "sensitivity", "origin_ids"],
        properties: {
          effect_alias: { type: "string", minLength: 1 },
          action: { type: "string", const: "network.send" },
          source: { type: "string", minLength: 1 },
          sink: { type: "string", pattern: "^mock://" },
          sensitivity: { type: "integer", minimum: 0, maximum: 4 },
          origin_ids: { type: "array", items: { type: "string", minLength: 1 } },
        },
      },
      execute: async (toolCallId, raw) => {
        const args = parseSafeSinkArgs(raw);
        return jsonResult({
          executed: true,
          receipt_id: receiptId(toolCallId),
          effect_alias: args.effect_alias,
        });
      },
    });

    api.on("llm_input", async (event, context) => {
      const currentSession = sessionId(context);
      await log.append({
        kind: "context_read",
        session_id: currentSession,
        actor_id: "harness",
        platform_hook: "llm_input",
        call_id: event.runId,
      });
      const loaded = loadedBySession.get(currentSession) ?? new Set<string>();
      loadedBySession.set(currentSession, loaded);
      for (const skill of parseAvailableSkills(event.systemPrompt)) {
        if (!plannedSkillIds.has(skill.skillId) || loaded.has(skill.skillId)) continue;
        loaded.add(skill.skillId);
        await log.append({
          kind: "skill_load",
          session_id: currentSession,
          actor_id: skill.skillId,
          platform_hook: "llm_input",
          call_id: event.runId,
          skill_id: skill.skillId,
        });
      }
    });

    api.on("before_tool_call", async (event, context) => {
      const runKey = event.runId ?? context.runId ?? config.runId;
      await log.append({
        kind: "tool_request",
        session_id: sessionId(context),
        actor_id: activeSkillByRun.get(runKey) ?? "harness",
        platform_hook: "before_tool_call",
        ...(event.toolCallId ? { call_id: event.toolCallId } : {}),
        tool_name: event.toolName,
      });
    });

    api.on("after_tool_call", async (event, context) => {
      const currentSession = sessionId(context);
      const runKey = event.runId ?? context.runId ?? config.runId;
      const actor = activeSkillByRun.get(runKey) ?? "harness";
      await log.append({
        kind: "tool_result",
        session_id: currentSession,
        actor_id: actor,
        platform_hook: "after_tool_call",
        ...(event.toolCallId ? { call_id: event.toolCallId } : {}),
        tool_name: event.toolName,
      });
      if (event.error) return;
      const relative = toolRelativePath(event.params, config.workspaceRoot);
      if (event.toolName === "read" && relative) {
        const skillId = advertisedPlannedSkill(
          config.skills,
          relative,
          loadedBySession.get(currentSession) ?? new Set(),
        );
        if (skillId) {
          activeSkillByRun.set(runKey, skillId);
          await appendSkillInvoke(log, currentSession, event.toolCallId, skillId);
          return;
        }
      }
      const resource = relative
        ? config.resources.find(
            (item) => item.tool === event.toolName && item.relative_path === relative,
          )
        : undefined;
      if (resource) {
        await appendResourceEffect(log, currentSession, event.toolCallId, actor, resource);
      }
      if (event.toolName === SAFE_SINK) {
        const args = parseSafeSinkArgs(event.params);
        await log.append({
          kind: "safe_effect",
          session_id: currentSession,
          actor_id: actor,
          platform_hook: "after_tool_call",
          call_id: requiredCallId(event.toolCallId),
          tool_name: SAFE_SINK,
          effect_alias: args.effect_alias,
          receipt_id: receiptId(requiredCallId(event.toolCallId)),
          origin_ids: args.origin_ids,
          executed: true,
          action: args.action,
          source: args.source,
          sink: args.sink,
          scope: "exact-sink",
          lifetime: "call",
          sensitivity: args.sensitivity,
          policy_fact: "platform_executed_no_grant_fact",
        });
      }
    });
  },
});

async function appendSkillInvoke(
  log: EventLog,
  currentSession: string,
  toolCallId: string | undefined,
  skillId: string,
): Promise<void> {
  const base = {
    session_id: currentSession,
    actor_id: skillId,
    platform_hook: "after_tool_call",
    call_id: requiredCallId(toolCallId),
    skill_id: skillId,
  } satisfies Omit<EventFields, "kind">;
  await log.append({ kind: "skill_invoke", ...base });
}

async function appendResourceEffect(
  log: EventLog,
  currentSession: string,
  toolCallId: string | undefined,
  actor: string,
  fact: ResourceFact,
): Promise<void> {
  const kind =
    fact.action === "file.read"
      ? "file_read"
      : fact.action === "memory.read"
        ? "memory_read"
        : "memory_write";
  await log.append({
    kind,
    session_id: currentSession,
    actor_id: actor,
    platform_hook: "after_tool_call",
    call_id: requiredCallId(toolCallId),
    tool_name: fact.tool,
    resource: fact.resource,
    ...(fact.effect_alias ? { effect_alias: fact.effect_alias } : {}),
    receipt_id: receiptId(requiredCallId(toolCallId)),
    origin_ids: fact.origin_ids,
    executed: true,
    action: fact.action,
    source: fact.source,
    sink: fact.sink,
    scope: fact.scope,
    lifetime: fact.lifetime,
    sensitivity: fact.sensitivity,
    policy_fact: "platform_executed_no_grant_fact",
  });
}

function requiredCallId(value: string | undefined): string {
  if (!value) throw new Error("OpenClaw tool hook omitted toolCallId");
  return value;
}

function receiptId(toolCallId: string): string {
  return `openclaw-receipt:${toolCallId}`;
}
