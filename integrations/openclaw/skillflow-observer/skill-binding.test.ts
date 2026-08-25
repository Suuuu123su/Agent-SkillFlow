import assert from "node:assert/strict";
import test from "node:test";
import { advertisedPlannedSkill, type PlannedSkill } from "./skill-binding.js";

const skills: readonly PlannedSkill[] = [
  { skillId: "memory-skill-a", relativePath: "skills/memory-skill-a/SKILL.md" },
];

test("skill invoke requires both catalog advertisement and exact SKILL.md read", () => {
  const advertised = new Set(["memory-skill-a"]);

  assert.equal(
    advertisedPlannedSkill(skills, "skills/memory-skill-a/SKILL.md", advertised),
    "memory-skill-a",
  );
  assert.equal(advertisedPlannedSkill(skills, "memory-skill-a/SKILL.md", advertised), undefined);
  assert.equal(
    advertisedPlannedSkill(skills, "skills/memory-skill-a/SKILL.md", new Set()),
    undefined,
  );
});
