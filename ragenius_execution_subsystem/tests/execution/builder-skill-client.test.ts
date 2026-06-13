import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";

import { HttpBuilderSkillClient } from "../../src/core/skills/builder-skill-client.js";

const originalFetch = globalThis.fetch;

describe("builder skill client", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("loads a bound published skill from builder endpoints", async () => {
    globalThis.fetch = (async (input: string | URL) => {
      const url = String(input);
      if (url.includes("/api/apps/app_001/skill-bindings")) {
        return new Response(
          JSON.stringify({
            items: [
              {
                skill_id: "lesson_planner_skill",
                skill_version: "2.0.0",
                enabled: true,
                permission_mode: "require_confirmation"
              }
            ]
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }

      return new Response(
        JSON.stringify({
          skill_id: "lesson_planner_skill",
          name: "Lesson Planner Skill",
          version: "2.0.0",
          description: "Builder-managed lesson planner.",
          enabled: true,
          required_tools: ["rag_retrieval_tool"],
          required_permissions: ["rag.read"],
          input_schema: {
            type: "object",
            properties: {
              topic: { type: "string" }
            },
            required: ["topic"]
          },
          output_schema: {
            type: "object",
            properties: {
              items: {
                type: "array",
                items: { type: "string" }
              }
            }
          },
          workflow_definition: {
            steps: [
              {
                id: "finish",
                type: "end"
              }
            ]
          }
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    const client = new HttpBuilderSkillClient("http://builder.local");
    const skill = await client.getBoundSkill("app_001", "lesson_planner_skill");

    assert.ok(skill);
    assert.equal(skill?.id, "lesson_planner_skill");
    assert.equal(skill?.version, "2.0.0");
    assert.equal(skill?.requiredTools[0], "rag_retrieval_tool");
    assert.equal(skill?.confirmationMode, "require_confirmation");
    assert.equal(skill?.resultType, "json");
    assert.doesNotThrow(() => skill?.inputSchema.parse({ topic: "Explain retrieval" }));
  });
});
