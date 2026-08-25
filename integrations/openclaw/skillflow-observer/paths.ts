import path from "node:path";

export type SkillEntry = { readonly skillId: string; readonly location: string };

export function parseAvailableSkills(systemPrompt: string | undefined): readonly SkillEntry[] {
  if (!systemPrompt) return [];
  const entries: SkillEntry[] = [];
  const pattern = /<skill>\s*<name>([^<]+)<\/name>[\s\S]*?<location>([^<]+)<\/location>\s*<\/skill>/gu;
  for (const match of systemPrompt.matchAll(pattern)) {
    const skillId = decodeXml(match[1] ?? "").trim();
    const location = decodeXml(match[2] ?? "").trim();
    if (skillId && location) entries.push({ skillId, location });
  }
  return entries;
}

export function normalized(value: string): string {
  const result = path.normalize(path.resolve(value));
  return process.platform === "win32" ? result.toLowerCase() : result;
}

export function toolRelativePath(
  params: Record<string, unknown>,
  workspaceRoot: string,
): string | undefined {
  const candidate = params.path;
  if (typeof candidate !== "string" || !candidate.trim()) return undefined;
  const absolute = path.isAbsolute(candidate) ? path.resolve(candidate) : path.resolve(workspaceRoot, candidate);
  const relative = path.relative(path.resolve(workspaceRoot), absolute);
  if (!relative || relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    return undefined;
  }
  return relative.split(path.sep).join("/");
}

export function sessionId(context: { readonly sessionKey?: string; readonly sessionId?: string }): string {
  const fromKey = context.sessionKey?.split(":").at(-1)?.trim();
  return fromKey || context.sessionId || "unknown-session";
}

function decodeXml(value: string): string {
  return value
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replaceAll("&quot;", '"')
    .replaceAll("&#39;", "'")
    .replaceAll("&amp;", "&");
}
