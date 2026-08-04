import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { ExecutionEngine } from "../../src/core/execution/execution-engine.js";
import { PermissionEngine } from "../../src/core/permissions/permission-engine.js";
import { buildApp } from "../../src/app.js";
import type { FastifyInstance } from "fastify";

describe("dry run placeholder", () => {
  it("does not execute side-effecting tools during dry run", async () => {
    const engine = new ExecutionEngine({
      permissionEngine: new PermissionEngine([
        {
          appId: "app_001",
          toolId: "mock_video_generation_tool",
          scope: "external_api.write",
          mode: "auto_allow"
        }
      ])
    });

    const result = await engine.execute({
      request_type: "execute_skill",
      app_id: "app_001",
      session_id: "sess_001",
      skill_id: "video_director_skill",
      input: {
        prompt: "Explain RAG simply",
        duration: 30
      },
      execution_options: {
        dry_run: true
      }
    });

    assert.equal(result.status, "completed");
    assert.equal(result.result_type, "json");
    assert.equal(result.result.side_effects_executed, false);
  });

  it("returns dry run response from POST /v1/executions", async () => {
    const app: FastifyInstance = buildApp({
      permissionEngine: new PermissionEngine([
        {
          appId: "app_001",
          toolId: "mock_video_generation_tool",
          scope: "external_api.write",
          mode: "auto_allow"
        }
      ])
    });

    const response = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_skill",
        app_id: "app_001",
        session_id: "sess_001",
        skill_id: "video_director_skill",
        input: {
          prompt: "Explain RAG simply",
          duration: 30
        },
        execution_options: {
          dry_run: true
        }
      }
    });

    assert.equal(response.statusCode, 200);
    assert.equal(response.json().result.side_effects_executed, false);

    await app.close();
  });
});
