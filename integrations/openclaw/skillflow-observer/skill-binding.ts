export type PlannedSkill = {
  readonly skillId: string;
  readonly relativePath: string;
};

export function advertisedPlannedSkill(
  skills: readonly PlannedSkill[],
  relativePath: string,
  advertised: ReadonlySet<string>,
): string | undefined {
  const match = skills.find((skill) => skill.relativePath === relativePath);
  return match && advertised.has(match.skillId) ? match.skillId : undefined;
}
