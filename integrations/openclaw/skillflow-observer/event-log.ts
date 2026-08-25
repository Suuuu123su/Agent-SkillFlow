import fs from "node:fs/promises";
import path from "node:path";
import type { PlannedSkill } from "./skill-binding.js";

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

export type ObserverConfig = {
  readonly logPath: string;
  readonly runId: string;
  readonly taskId: string;
  readonly workspaceRoot: string;
  readonly resources: readonly ResourceFact[];
  readonly skills: readonly PlannedSkill[];
};

export type EventFields = {
  readonly kind: string;
  readonly session_id: string;
  readonly actor_id: string;
  readonly platform_hook: string;
  readonly call_id?: string;
  readonly skill_id?: string;
  readonly tool_name?: string;
  readonly resource?: string;
  readonly effect_alias?: string;
  readonly receipt_id?: string;
  readonly origin_ids?: readonly string[];
  readonly executed?: boolean;
  readonly action?: string;
  readonly source?: string | null;
  readonly sink?: string;
  readonly scope?: string;
  readonly lifetime?: string;
  readonly sensitivity?: number;
  readonly policy_fact?: string;
};

export class EventLog {
  private sequence = 0;
  private pending: Promise<void> = Promise.resolve();

  constructor(
    private readonly config: ObserverConfig,
  ) {}

  append(fields: EventFields): Promise<void> {
    const record = {
      schema_version: "0.1",
      sequence: this.sequence,
      timestamp: new Date().toISOString(),
      run_id: this.config.runId,
      task_id: this.config.taskId,
      origin_ids: [],
      ...fields,
    };
    this.sequence += 1;
    this.pending = this.pending.then(async () => {
      await fs.mkdir(path.dirname(this.config.logPath), { recursive: true });
      await fs.appendFile(this.config.logPath, `${JSON.stringify(record)}\n`, "utf8");
    });
    return this.pending;
  }
}

export function parseObserverConfig(value: unknown): ObserverConfig {
  if (!isRecord(value)) throw new Error("skillflow-observer config is required");
  const resources = value.resources;
  const skills = value.skills;
  if (!Array.isArray(resources)) throw new Error("resources must be an array");
  if (!Array.isArray(skills)) throw new Error("skills must be an array");
  return {
    logPath: requiredString(value, "logPath"),
    runId: requiredString(value, "runId"),
    taskId: requiredString(value, "taskId"),
    workspaceRoot: requiredString(value, "workspaceRoot"),
    resources: resources.map(parseResourceFact),
    skills: skills.map(parsePlannedSkill),
  };
}

function parsePlannedSkill(value: unknown): PlannedSkill {
  if (!isRecord(value)) throw new Error("planned skill must be an object");
  return {
    skillId: requiredString(value, "skillId"),
    relativePath: requiredString(value, "relativePath"),
  };
}

export function parseSafeSinkArgs(value: unknown): {
  readonly effect_alias: string;
  readonly action: "network.send";
  readonly source: string;
  readonly sink: string;
  readonly sensitivity: number;
  readonly origin_ids: readonly string[];
} {
  if (!isRecord(value)) throw new Error("safe sink arguments must be an object");
  const action = requiredString(value, "action");
  const sink = requiredString(value, "sink");
  const sensitivity = value.sensitivity;
  const origins = value.origin_ids;
  if (action !== "network.send") throw new Error("safe sink only accepts network.send");
  if (!sink.startsWith("mock://")) throw new Error("safe sink requires mock:// target");
  if (!Number.isInteger(sensitivity) || Number(sensitivity) < 0 || Number(sensitivity) > 4) {
    throw new Error("safe sink sensitivity is invalid");
  }
  if (!Array.isArray(origins) || !origins.every(isNonEmptyString)) {
    throw new Error("safe sink origin_ids are invalid");
  }
  return {
    effect_alias: requiredString(value, "effect_alias"),
    action,
    source: requiredString(value, "source"),
    sink,
    sensitivity: Number(sensitivity),
    origin_ids: origins,
  };
}

function parseResourceFact(value: unknown): ResourceFact {
  if (!isRecord(value)) throw new Error("resource fact must be an object");
  const tool = requiredString(value, "tool");
  const action = requiredString(value, "action");
  const scope = requiredString(value, "scope");
  const sensitivity = value.sensitivity;
  const origins = value.origin_ids;
  if (tool !== "read" && tool !== "write") throw new Error("resource tool is invalid");
  if (action !== "file.read" && action !== "memory.read" && action !== "memory.write") {
    throw new Error("resource action is invalid");
  }
  if (scope !== "exact-file" && scope !== "exact-key") throw new Error("scope is invalid");
  if (!Number.isInteger(sensitivity) || !Array.isArray(origins) || !origins.every(isNonEmptyString)) {
    throw new Error("resource evidence is invalid");
  }
  return {
    tool,
    relative_path: requiredString(value, "relative_path"),
    resource: requiredString(value, "resource"),
    action,
    source: nullableString(value.source),
    sink: requiredString(value, "sink"),
    scope,
    lifetime: "call",
    sensitivity: Number(sensitivity),
    origin_ids: origins,
    effect_alias: nullableString(value.effect_alias),
  };
}

function requiredString(value: Record<string, unknown>, key: string): string {
  const item = value[key];
  if (!isNonEmptyString(item)) throw new Error(`${key} must be a non-empty string`);
  return item;
}

function nullableString(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (!isNonEmptyString(value)) throw new Error("optional string is invalid");
  return value;
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
