import path from "node:path";
import type { Invocation, ToolCall } from "./driver-types.js";

type FunctionCall = { readonly name: string; readonly args: Record<string, unknown> };

export function responseControl(
  invocation: Invocation,
  workspaceRoot: string,
  version: string,
): Record<string, unknown> {
  const calls: FunctionCall[] = [
    {
      name: "read",
      args: { path: path.join(workspaceRoot, "skills", invocation.skill_id, "SKILL.md") },
    },
    ...invocation.tool_calls.map((call) => functionCall(call)),
  ];
  return {
    scriptVersion: version,
    responses: [
      ...calls.map((call, index) => ({ events: toolCallEvents(call, `${version}-${index}`) })),
      { text: `T15_PILOT_OK ${invocation.step_id}` },
    ],
  };
}

function functionCall(call: ToolCall): FunctionCall {
  if (call.tool === "read") {
    return { name: call.tool, args: { path: required(call.relative_path, "read path") } };
  }
  if (call.tool === "write") {
    return {
      name: call.tool,
      args: {
        path: required(call.relative_path, "write path"),
        content: required(call.content, "write content"),
      },
    };
  }
  return {
    name: call.tool,
    args: {
      effect_alias: required(call.effect_alias, "effect alias"),
      action: required(call.action, "effect action"),
      source: required(call.source, "effect source"),
      sink: required(call.sink, "effect sink"),
      sensitivity: required(call.sensitivity, "effect sensitivity"),
      origin_ids: call.origin_ids,
    },
  };
}

function toolCallEvents(call: FunctionCall, identity: string): readonly Record<string, unknown>[] {
  const callId = `call_t15_${identity}`;
  const itemId = `fc_t15_${identity}`;
  const serialized = JSON.stringify(call.args);
  const item = {
    type: "function_call",
    id: itemId,
    call_id: callId,
    name: call.name,
    arguments: serialized,
  };
  return [
    {
      type: "response.output_item.added",
      item: { ...item, arguments: "" },
    },
    { type: "response.function_call_arguments.delta", delta: serialized },
    { type: "response.output_item.done", item },
    {
      type: "response.completed",
      response: {
        id: `resp_t15_${identity}`,
        status: "completed",
        output: [item],
        usage: {
          input_tokens: 32,
          output_tokens: 8,
          total_tokens: 40,
          input_tokens_details: { cached_tokens: 0 },
        },
      },
    },
  ];
}

function required<T>(value: T | null, label: string): T {
  if (value === null) throw new Error(`${label} is missing`);
  return value;
}
