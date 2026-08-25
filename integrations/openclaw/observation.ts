import fs from "node:fs/promises";
import { setTimeout as delay } from "node:timers/promises";

export function hasTargetEffectEvidence(
  jsonl: string,
  targetAliases: readonly string[],
): boolean {
  const observed = new Set<string>();
  for (const line of jsonl.split(/\r?\n/u).filter((item) => item.length > 0)) {
    const value: unknown = JSON.parse(line);
    if (
      isRecord(value) &&
      typeof value.effect_alias === "string" &&
      value.executed === true &&
      typeof value.receipt_id === "string" &&
      value.receipt_id.length > 0
    ) {
      observed.add(value.effect_alias);
    }
  }
  return targetAliases.every((alias) => observed.has(alias));
}

export async function waitForTargetEffectEvidence(
  logPath: string,
  targetAliases: readonly string[],
  timeoutMs = 30_000,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const jsonl = await fs.readFile(logPath, "utf8");
      if (hasTargetEffectEvidence(jsonl, targetAliases)) return;
    } catch (error) {
      if (!isMissingFile(error)) throw error;
    }
    await delay(50);
  }
  throw new Error(`observer did not emit target Effect evidence within ${timeoutMs}ms`);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isMissingFile(error: unknown): boolean {
  return error instanceof Error && Reflect.get(error, "code") === "ENOENT";
}
