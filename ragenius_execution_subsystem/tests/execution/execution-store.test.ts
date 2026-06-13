import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { ExecutionRequest } from "../../src/api/schemas/execution-request.schema.js";
import { InMemoryExecutionStore } from "../../src/core/execution/execution-store.js";

describe("execution store", () => {
  it("persists and retrieves execution records with logs", async () => {
    const store = new InMemoryExecutionStore();
    const request: ExecutionRequest = {
      request_type: "execute_skill",
      app_id: "app_001",
      session_id: "sess_001",
      skill_id: "video_director_skill",
      input: {
        prompt: "Explain RAG simply",
        duration: 30
      }
    };

    await store.save({
      executionId: "execution_001",
      request,
      result: {
        execution_id: "execution_001",
        status: "completed",
        result_type: "video",
        result: {
          title: "Video: Explain RAG simply"
        },
        execution_provenance: [
          {
            execution_path: "rest_fallback",
            tool_id: "mcp.gdrive.download_file_content",
            provider_type: "mcp",
            provider_id: "gdrive",
            remote_tool_name: "download_file_content",
            fallback_used: true,
            fallback_reason: "mcp_permission_rejected"
          }
        ],
        execution_metadata: {
          used_fallback: true,
          fallback_count: 1,
          execution_paths: ["rest_fallback"],
          provider_ids: ["gdrive"],
          tool_ids: ["mcp.gdrive.download_file_content"]
        },
        files: [],
        errors: [],
        logs_summary: "Skill completed."
      }
    });

    const record = await store.get("execution_001");
    const logs = await store.getLogs("execution_001");
    const storedRequest = await store.getRequest("execution_001");

    assert.equal(record?.execution_id, "execution_001");
    assert.equal(record?.app_id, "app_001");
    assert.equal(record?.skill_id, "video_director_skill");
    assert.equal(record?.status, "completed");
    assert.equal(record?.execution_provenance?.[0]?.execution_path, "rest_fallback");
    assert.equal(record?.execution_metadata?.used_fallback, true);
    assert.equal(record?.execution_metadata?.fallback_count, 1);
    assert.equal(storedRequest?.session_id, "sess_001");
    assert.equal(logs.length, 1);
    assert.equal(logs[0]?.message, "Skill completed.");
  });

  it("lists recent execution records with fallback filters", async () => {
    const store = new InMemoryExecutionStore();
    const request: ExecutionRequest = {
      request_type: "execute_skill",
      app_id: "app_001",
      session_id: "sess_001",
      skill_id: "video_director_skill",
      input: {
        prompt: "Explain RAG simply",
        duration: 30
      }
    };

    await store.save({
      executionId: "execution_fallback",
      request,
      result: {
        execution_id: "execution_fallback",
        status: "completed",
        result_type: "json",
        result: {},
        execution_provenance: [
          {
            execution_path: "rest_fallback",
            tool_id: "mcp.gdrive.download_file_content",
            provider_type: "mcp",
            provider_id: "gdrive",
            fallback_used: true
          }
        ],
        execution_metadata: {
          used_fallback: true,
          fallback_count: 1,
          execution_paths: ["rest_fallback"],
          provider_ids: ["gdrive"],
          tool_ids: ["mcp.gdrive.download_file_content"]
        },
        files: [],
        errors: [],
        logs_summary: "Fallback execution."
      }
    });

    await store.save({
      executionId: "execution_mcp",
      request: {
        ...request,
        session_id: "sess_002"
      },
      result: {
        execution_id: "execution_mcp",
        status: "completed",
        result_type: "json",
        result: {},
        execution_provenance: [
          {
            execution_path: "mcp",
            tool_id: "mcp.gmail.search_messages",
            provider_type: "mcp",
            provider_id: "gmail"
          }
        ],
        execution_metadata: {
          used_fallback: false,
          fallback_count: 0,
          execution_paths: ["mcp"],
          provider_ids: ["gmail"],
          tool_ids: ["mcp.gmail.search_messages"]
        },
        files: [],
        errors: [],
        logs_summary: "Direct MCP execution."
      }
    });

    const fallbackOnly = await store.listRecent({
      limit: 10,
      usedFallback: true
    });
    const mcpOnly = await store.listRecent({
      limit: 10,
      executionPath: "mcp"
    });

    assert.equal(fallbackOnly.length, 1);
    assert.equal(fallbackOnly[0]?.execution_id, "execution_fallback");
    assert.equal(mcpOnly.length, 1);
    assert.equal(mcpOnly[0]?.execution_id, "execution_mcp");
  });
});
