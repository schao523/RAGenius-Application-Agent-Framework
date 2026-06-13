import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { ExecutionRequest } from "../../src/api/schemas/execution-request.schema.js";
import { PrismaExecutionStore } from "../../src/core/execution/prisma-execution-store.js";
import type { ExecutionStorePrismaClient } from "../../src/db/prisma.js";

describe("prisma execution store", () => {
  it("persists and reloads execution records, requests, and logs", async () => {
    let upsertPayload: Record<string, unknown> | undefined;
    let createdLogs:
      | Array<Record<string, unknown>>
      | undefined;

    const prisma = {
      execution: {
        async upsert(args: Record<string, unknown>) {
          upsertPayload = args;
          return args.create;
        },
        async findUnique() {
          return {
            id: "execution_001",
            requestType: "execute_skill",
            appId: "app_001",
            sessionId: "sess_001",
            skillId: "video_director_skill",
            requestPayload: {
              request_type: "execute_skill",
              app_id: "app_001",
              session_id: "sess_001",
              skill_id: "video_director_skill",
              input: { prompt: "Explain RAG simply", duration: 30 }
            },
            status: "completed",
            resultType: "video",
            result: { title: "Video: Explain RAG simply" },
            executionProvenance: [
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
            executionMetadata: {
              used_fallback: true,
              fallback_count: 1,
              execution_paths: ["rest_fallback"],
              provider_ids: ["gdrive"],
              tool_ids: ["mcp.gdrive.download_file_content"]
            },
            files: [],
            errors: [],
            logsSummary: "Skill completed.",
            createdAt: new Date("2026-05-27T00:00:00.000Z"),
            updatedAt: new Date("2026-05-27T00:00:01.000Z")
          };
        },
        async findMany() {
          return [];
        }
      },
      executionLog: {
        async createMany(args: { data: Array<Record<string, unknown>> }) {
          createdLogs = args.data;
          return { count: args.data.length };
        },
        async findMany() {
          return [
            {
              executionId: "execution_001",
              level: "info",
              eventType: "summary",
              message: "Skill completed.",
              createdAt: new Date("2026-05-27T00:00:01.000Z")
            }
          ];
        }
      },
      $connect: async () => undefined,
      $disconnect: async () => undefined
    } satisfies ExecutionStorePrismaClient;

    const store = new PrismaExecutionStore(prisma);
    const request: ExecutionRequest = {
      request_type: "execute_skill",
      app_id: "app_001",
      session_id: "sess_001",
      skill_id: "video_director_skill",
      input: { prompt: "Explain RAG simply", duration: 30 }
    };

    await store.save({
      executionId: "execution_001",
      request,
      result: {
        execution_id: "execution_001",
        status: "completed",
        result_type: "video",
        result: { title: "Video: Explain RAG simply" },
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
    const storedRequest = await store.getRequest("execution_001");
    const logs = await store.getLogs("execution_001");

    assert.ok(upsertPayload);
    assert.equal(
      (upsertPayload?.create as Record<string, unknown>).requestType,
      "execute_skill"
    );
    assert.deepEqual(
      (upsertPayload?.create as Record<string, unknown>).executionProvenance,
      [
        {
          execution_path: "rest_fallback",
          tool_id: "mcp.gdrive.download_file_content",
          provider_type: "mcp",
          provider_id: "gdrive",
          remote_tool_name: "download_file_content",
          fallback_used: true,
          fallback_reason: "mcp_permission_rejected"
        }
      ]
    );
    assert.deepEqual(
      (upsertPayload?.create as Record<string, unknown>).executionMetadata,
      {
        used_fallback: true,
        fallback_count: 1,
        execution_paths: ["rest_fallback"],
        provider_ids: ["gdrive"],
        tool_ids: ["mcp.gdrive.download_file_content"]
      }
    );
    assert.equal(createdLogs?.length, 1);
    assert.equal(record?.execution_id, "execution_001");
    assert.equal(record?.status, "completed");
    assert.equal(record?.execution_provenance?.[0]?.execution_path, "rest_fallback");
    assert.equal(record?.execution_metadata?.used_fallback, true);
    assert.equal(storedRequest?.session_id, "sess_001");
    assert.equal(logs[0]?.message, "Skill completed.");
  });

  it("lists recent execution records with fallback filters", async () => {
    const prisma = {
      execution: {
        async upsert() {
          return undefined;
        },
        async findUnique() {
          return null;
        },
        async findMany() {
          return [
            {
              id: "execution_mcp",
              requestType: "execute_skill",
              appId: "app_001",
              sessionId: "sess_001",
              skillId: "gmail_search",
              requestPayload: {},
              status: "completed",
              resultType: "json",
              result: {},
              executionProvenance: [
                {
                  execution_path: "mcp",
                  tool_id: "mcp.gmail.search_messages",
                  provider_type: "mcp",
                  provider_id: "gmail",
                }
              ],
              executionMetadata: {
                used_fallback: false,
                fallback_count: 0,
                execution_paths: ["mcp"],
                provider_ids: ["gmail"],
                tool_ids: ["mcp.gmail.search_messages"],
              },
              files: [],
              errors: [],
              logsSummary: "Direct MCP execution.",
              createdAt: new Date("2026-05-27T00:00:00.000Z"),
              updatedAt: new Date("2026-05-27T00:00:01.000Z"),
            },
            {
              id: "execution_fallback",
              requestType: "execute_skill",
              appId: "app_001",
              sessionId: "sess_002",
              skillId: "drive_download",
              requestPayload: {},
              status: "completed",
              resultType: "json",
              result: {},
              executionProvenance: [
                {
                  execution_path: "rest_fallback",
                  tool_id: "mcp.gdrive.download_file_content",
                  provider_type: "mcp",
                  provider_id: "gdrive",
                  fallback_used: true,
                }
              ],
              executionMetadata: {
                used_fallback: true,
                fallback_count: 1,
                execution_paths: ["rest_fallback"],
                provider_ids: ["gdrive"],
                tool_ids: ["mcp.gdrive.download_file_content"],
              },
              files: [],
              errors: [],
              logsSummary: "Fallback execution.",
              createdAt: new Date("2026-05-27T00:00:02.000Z"),
              updatedAt: new Date("2026-05-27T00:00:03.000Z"),
            }
          ];
        }
      },
      executionLog: {
        async createMany() {
          return { count: 0 };
        },
        async findMany() {
          return [];
        }
      },
      $connect: async () => undefined,
      $disconnect: async () => undefined
    } satisfies ExecutionStorePrismaClient;

    const store = new PrismaExecutionStore(prisma);
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
