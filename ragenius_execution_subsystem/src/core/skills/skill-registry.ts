import { AppError } from "../errors/app-error.js";

import { sampleSkills } from "./sample-skills.js";
import type { SkillDefinition } from "./skill.types.js";

export class SkillRegistry {
  private readonly skills = new Map<string, SkillDefinition>();

  constructor(initialSkills: SkillDefinition[] = sampleSkills) {
    for (const skill of initialSkills) {
      this.skills.set(skill.id, skill);
    }
  }

  list(): SkillDefinition[] {
    return [...this.skills.values()];
  }

  get(skillId: string): SkillDefinition {
    const skill = this.skills.get(skillId);
    if (!skill || !skill.enabled) {
      throw new AppError({
        code: "SKILL_NOT_FOUND",
        message: "Skill was not found or is disabled.",
        errorClass: "validation",
        httpStatus: 404,
        details: { skill_id: skillId },
        recoverable: true,
        suggestedAction: "Use GET /v1/skills to inspect available skills."
      });
    }

    return skill;
  }

  register(skill: SkillDefinition): void {
    this.skills.set(skill.id, skill);
  }
}
