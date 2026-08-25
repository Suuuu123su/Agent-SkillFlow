export type ResourceFact = {
  readonly tool: "read" | "write";
  readonly relative_path: string;
  readonly resource: string;
  readonly action: "file.read" | "memory.read" | "memory.write";
  readonly source: string | null;
  readonly sink: string;
  readonly scope: "exact-file" | "exact-key";
  readonly lifetime: "call";
  readonly sensitivity: number;
  readonly origin_ids: readonly string[];
  readonly effect_alias: string | null;
};

export type ToolCall = {
  readonly tool: "read" | "write" | "skillflow_safe_sink";
  readonly relative_path: string | null;
  readonly content: string | null;
  readonly effect_alias: string | null;
  readonly action: "network.send" | null;
  readonly source: string | null;
  readonly sink: string | null;
  readonly sensitivity: number | null;
  readonly origin_ids: readonly string[];
};

export type Invocation = {
  readonly session_id: string;
  readonly step_id: string;
  readonly skill_id: string;
  readonly prompt: string;
  readonly tool_calls: readonly ToolCall[];
};

export type PilotPlan = {
  readonly schema_version: "0.1";
  readonly scenario_id: string;
  readonly task_id: string;
  readonly run_id: string;
  readonly skills: readonly { readonly skill_id: string }[];
  readonly workspace_files: readonly {
    readonly relative_path: string;
    readonly content: string;
  }[];
  readonly resources: readonly ResourceFact[];
  readonly invocations: readonly Invocation[];
  readonly revocations: readonly {
    readonly session_id: string;
    readonly skill_id: string;
  }[];
  readonly target_effect_aliases: readonly string[];
  readonly expected_origin_ids: readonly string[];
};

export function parsePlan(value: unknown): PilotPlan {
  if (!isPlan(value)) throw new Error("T15 request does not match the fixed pilot contract");
  return value;
}

function isPlan(value: unknown): value is PilotPlan {
  return (
    isRecord(value) &&
    value.schema_version === "0.1" &&
    strings(value, ["scenario_id", "task_id", "run_id"]) &&
    Array.isArray(value.skills) &&
    value.skills.every((item) => isRecord(item) && nonEmpty(item.skill_id)) &&
    Array.isArray(value.workspace_files) &&
    value.workspace_files.every(
      (item) => isRecord(item) && nonEmpty(item.relative_path) && nonEmpty(item.content),
    ) &&
    Array.isArray(value.resources) &&
    value.resources.every(isResource) &&
    Array.isArray(value.invocations) &&
    value.invocations.every(isInvocation) &&
    Array.isArray(value.revocations) &&
    value.revocations.every(
      (item) => isRecord(item) && strings(item, ["session_id", "skill_id"]),
    ) &&
    stringArray(value.target_effect_aliases) &&
    stringArray(value.expected_origin_ids)
  );
}

function isInvocation(value: unknown): value is Invocation {
  return (
    isRecord(value) &&
    strings(value, ["session_id", "step_id", "skill_id", "prompt"]) &&
    Array.isArray(value.tool_calls) &&
    value.tool_calls.every(isToolCall)
  );
}

function isToolCall(value: unknown): value is ToolCall {
  if (!isRecord(value) || !["read", "write", "skillflow_safe_sink"].includes(String(value.tool))) {
    return false;
  }
  return (
    nullable(value.relative_path) &&
    nullable(value.content) &&
    nullable(value.effect_alias) &&
    (value.action === null || value.action === "network.send") &&
    nullable(value.source) &&
    nullable(value.sink) &&
    (value.sensitivity === null || Number.isInteger(value.sensitivity)) &&
    stringArray(value.origin_ids)
  );
}

function isResource(value: unknown): value is ResourceFact {
  return (
    isRecord(value) &&
    (value.tool === "read" || value.tool === "write") &&
    strings(value, ["relative_path", "resource", "action", "sink", "scope", "lifetime"]) &&
    nullable(value.source) &&
    nullable(value.effect_alias) &&
    Number.isInteger(value.sensitivity) &&
    stringArray(value.origin_ids)
  );
}

function strings(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return keys.every((key) => nonEmpty(value[key]));
}

function stringArray(value: unknown): value is readonly string[] {
  return Array.isArray(value) && value.every(nonEmpty);
}

function nullable(value: unknown): value is string | null {
  return value === null || nonEmpty(value);
}

function nonEmpty(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
