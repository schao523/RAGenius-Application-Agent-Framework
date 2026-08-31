import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, it } from "node:test";
import type { FastifyInstance } from "fastify";
import { z } from "zod";

import { buildApp, createAppServices } from "../../src/app.js";
import { executionRequestSchema } from "../../src/api/schemas/execution-request.schema.js";
import { CodexCliProvider } from "../../src/core/agents/codex-cli-provider.js";
import { ExecutionEngine } from "../../src/core/execution/execution-engine.js";
import { InMemoryExecutionStore } from "../../src/core/execution/execution-store.js";
import { PermissionEngine } from "../../src/core/permissions/permission-engine.js";
import { getEnv } from "../../src/config/env.js";
import { buildRuntimeConfig } from "../../src/config/runtime-config.js";
import { ToolEngine } from "../../src/core/tools/tool-engine.js";
import { AdapterToolProvider } from "../../src/core/tools/providers/adapter-tool-provider.js";
import { ArtifactStore } from "../../src/core/tools/providers/artifact-store.js";
import { NotebookLmAdapter } from "../../src/core/tools/providers/notebooklm-adapter.js";

const originalFetch = globalThis.fetch;
const repositoryRoot = path.resolve(process.cwd(), "..");
const repositoryDocsRoot = path.join(repositoryRoot, "docs");
const repositoryOutputsRoot = path.join(repositoryRoot, "outputs");
const mutationRoots = new Set<string>();

async function claimPendingConfirmation(
  engine: ExecutionEngine,
  pending: {
    execution_id?: string | null | undefined;
    result: Record<string, unknown>;
  },
  scope: { appId: string; sessionId: string }
) {
  const executionId = String(pending.execution_id ?? "");
  const confirmationId = String(pending.result.confirmation_id ?? "");
  const claim = await engine.getConfirmationService().claim({
    ...scope,
    confirmationId,
    executionId
  });
  assert.equal(claim.outcome, "claimed");
  if (claim.outcome !== "claimed") {
    throw new Error("Expected confirmation claim.");
  }
  return {
    approvedConfirmation: {
      confirmationId,
      policySnapshot: claim.record.policySnapshot
    },
    executionId
  };
}

async function cleanupMutationRoot(root: string): Promise<void> {
  for (let attempt = 0; attempt < 5; attempt += 1) {
    try {
      await fs.rm(root, { recursive: true, force: true });
      return;
    } catch (error) {
      if (
        !(error && typeof error === "object" && "code" in error) ||
        (error as { code?: string }).code !== "EPERM" ||
        attempt === 4
      ) {
        if (
          error &&
          typeof error === "object" &&
          "code" in error &&
          (error as { code?: string }).code === "EPERM"
        ) {
          return;
        }
        throw error;
      }
      await new Promise((resolve) => setTimeout(resolve, 50 * (attempt + 1)));
    }
  }
}

describe("health routes", () => {
  let app: FastifyInstance | undefined;
  const temporaryArtifactRoots = new Set<string>();

  afterEach(async () => {
    await app?.close();
    app = undefined;
    globalThis.fetch = originalFetch;
    await Promise.all(
      [...temporaryArtifactRoots].map(async (root) => {
        await cleanupMutationRoot(root);
        temporaryArtifactRoots.delete(root);
      })
    );
  });

  it("returns ok for /healthz", async () => {
    app = buildApp();

    const response = await app.inject({
      method: "GET",
      url: "/healthz"
    });

    assert.equal(response.statusCode, 200);
    assert.deepEqual(response.json(), { status: "ok" });
  });

  it("returns non-secret runtime config details for /readyz", async () => {
    globalThis.fetch = (async (_input: string | URL | Request, init?: RequestInit) => {
      const payload = JSON.parse(String(init?.body ?? "{}")) as { method?: string };

      if (payload.method === "initialize") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 1,
            result: { protocolVersion: "2025-06-18" }
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }

      if (payload.method === "notifications/initialized") {
        return new Response("", {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      return new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          id: 2,
          result: {
            tools: []
          }
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    const runtimeConfig = buildRuntimeConfig(
      getEnv({
        DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
        BUILDER_BASE_URL: "http://127.0.0.1:8011",
        HTTPS_PROXY: "http://proxy.local:8080",
        MCP_SERVERS_JSON: JSON.stringify([
          {
            id: "local-browser",
            transport: "http",
            baseUrl: "http://127.0.0.1:4100",
            enabled: true
          }
        ])
      })
    );
    app = buildApp({}, runtimeConfig);

    const response = await app.inject({
      method: "GET",
      url: "/readyz"
    });

    assert.equal(response.statusCode, 200);
    assert.equal(response.json().status, "ready");
    assert.equal(response.json().checks.runtime_config.builder.configured, true);
    assert.equal(response.json().checks.runtime_config.fileTools.configured, false);
    assert.equal(
      response.json().checks.runtime_config.artifactStore.configured,
      true
    );
    assert.equal(
      response.json().checks.runtime_config.network.proxyConfigured,
      true
    );
    assert.equal(
      response.json().checks.runtime_config.mcp.configuredServers,
      1
    );
    assert.equal(
      response.json().checks.runtime_config.mcp.startupDiscoveryEnabled,
      true
    );
    assert.equal(
      response.json().checks.runtime_config.providers.semanticScholar.hasApiKey,
      false
    );
    assert.equal(
      response.json().checks.runtime_config.providers.codexCli.enabled,
      false
    );
    assert.equal(
      response.json().checks.mcp_discovery.startupCompleted,
      true
    );
    assert.equal(
      response.json().checks.mcp_discovery.providers["local-browser"].status,
      "success"
    );
  });

  it("returns cross-family runtime integrations including adapter-backed NotebookLM", async () => {
    const runtimeConfig = buildRuntimeConfig(
      getEnv({
        DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
        NOTEBOOKLM_ENABLED: "true",
        NOTEBOOKLM_PYTHON_COMMAND: "python",
        NOTEBOOKLM_BRIDGE_SCRIPT: "scripts/notebooklm_bridge.py",
        NOTEBOOKLM_AUTH_MODE: "profile",
        NOTEBOOKLM_PROFILE: "default",
        NOTEBOOKLM_ALLOWED_OPERATIONS: "ask,generate_video",
        ADAPTERS_JSON: JSON.stringify([
          {
            id: "adapter.notebooklm.ask",
            enabled: true
          },
          {
            id: "adapter.notebooklm.generate_video",
            enabled: true
          }
        ]),
        MCP_SERVERS_JSON: "[]"
      })
    );
    app = buildApp({}, runtimeConfig);

    const response = await app.inject({
      method: "GET",
      url: "/v1/runtime/integrations"
    });

    assert.equal(response.statusCode, 200);
    const body = response.json();
    assert.ok(Array.isArray(body.items));
    const notebooklm = body.items.find(
      (item: { id: string }) => item.id === "notebooklm"
    );
    assert.ok(notebooklm);
    assert.equal(notebooklm.family, "adapter");
    assert.equal(notebooklm.enabled, true);
    assert.ok(notebooklm.tool_ids.includes("adapter.notebooklm.ask"));
    assert.ok(notebooklm.tool_ids.includes("adapter.notebooklm.generate_video"));
  });

  it("returns runtime tool inventory with fallback and policy metadata", async () => {
    const runtimeConfig = buildRuntimeConfig(
      getEnv({
        DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
        NOTEBOOKLM_ENABLED: "true",
        NOTEBOOKLM_PYTHON_COMMAND: "python",
        NOTEBOOKLM_BRIDGE_SCRIPT: "scripts/notebooklm_bridge.py",
        NOTEBOOKLM_AUTH_MODE: "profile",
        NOTEBOOKLM_PROFILE: "default",
        NOTEBOOKLM_ALLOWED_OPERATIONS: "generate_video",
        ADAPTERS_JSON: JSON.stringify([
          {
            id: "adapter.notebooklm.generate_video",
            enabled: true
          }
        ]),
        MCP_SERVERS_JSON: "[]"
      })
    );
    app = buildApp({}, runtimeConfig);
    app.services.toolRegistry.register({
      id: "mcp.gdrive.download_file_content",
      name: "Drive Download",
      providerType: "mcp",
      inputSchema: z.object({ fileId: z.string() }),
      outputSchema: z.object({ content: z.string() }),
      permissionScopes: ["external_api.read"],
      sideEffecting: false,
      enabled: true,
      metadata: {
        policyClass: "review_required",
        providerId: "gdrive"
      }
    });
    app.services.toolRegistry.register({
      id: "mcp.gmail.create_draft",
      name: "create_draft",
      providerType: "mcp",
      inputSchema: z.object({
        to: z.array(z.string()).optional(),
        subject: z.string().optional(),
        body: z.string().optional()
      }),
      outputSchema: z.object({ draftId: z.string() }),
      permissionScopes: ["external_api.write"],
      sideEffecting: true,
      enabled: true,
      metadata: {
        policyClass: "review_required",
        providerId: "gmail"
      }
    });
    app.services.toolRegistry.register({
      id: "mcp.gmail.create_draft_with_attachments",
      name: "create_draft",
      providerType: "mcp",
      inputSchema: z.object({
        to: z.array(z.string()).optional(),
        subject: z.string().optional(),
        body: z.string().optional(),
        attachments: z.array(z.string()).optional()
      }),
      outputSchema: z.object({ draftId: z.string() }),
      permissionScopes: ["external_api.write"],
      sideEffecting: true,
      enabled: true,
      metadata: {
        policyClass: "review_required",
        providerId: "gmail"
      }
    });

    const response = await app.inject({
      method: "GET",
      url: "/v1/tools/inventory"
    });

    assert.equal(response.statusCode, 200);
    const body = response.json();
    assert.ok(Array.isArray(body.items));
    const notebooklmVideo = body.items.find(
      (item: { tool_id: string }) =>
        item.tool_id === "adapter.notebooklm.generate_video"
    );
    assert.ok(notebooklmVideo);
    assert.equal(notebooklmVideo.family, "adapter");
    assert.equal(notebooklmVideo.provider_id, "notebooklm");
    assert.equal(notebooklmVideo.exec_capable, true);
    assert.equal(notebooklmVideo.exec_kind, "tool");
    assert.equal(notebooklmVideo.policy_class, "review_required");
    assert.equal(notebooklmVideo.risk_class, "write");
    assert.ok(notebooklmVideo.input_schema);
    assert.ok(notebooklmVideo.output_schema);
    assert.equal(notebooklmVideo.input_schema.type, "object");
    assert.ok(notebooklmVideo.input_schema.properties.notebookTitle);
    assert.ok(notebooklmVideo.input_schema.properties.instructions);
    assert.equal(notebooklmVideo.fallback_capable, false);
    const notebooklmAddSourceFile = body.items.find(
      (item: { tool_id: string }) =>
        item.tool_id === "adapter.notebooklm.add_source_file"
    );
    assert.ok(notebooklmAddSourceFile);
    assert.equal(notebooklmAddSourceFile.artifact_picker?.enabled, true);
    assert.equal(notebooklmAddSourceFile.artifact_picker?.field_name, "filePath");
    assert.equal(notebooklmAddSourceFile.artifact_picker?.selection_mode, "single");
    assert.deepEqual(
      notebooklmAddSourceFile.artifact_picker?.accepted_artifact_types,
      ["chat_export"]
    );
    assert.equal(
      notebooklmAddSourceFile.artifact_picker?.required_consumption_mode,
      "file_backed"
    );
    assert.equal(notebooklmAddSourceFile.artifact_picker?.max_artifact_count, 1);
    const driveDownload = body.items.find(
      (item: { tool_id: string }) =>
        item.tool_id === "mcp.gdrive.download_file_content"
    );
    assert.ok(driveDownload);
    assert.equal(driveDownload.name, "Google Drive Download File");
    assert.equal(driveDownload.fallback_capable, true);
    assert.equal(driveDownload.fallback_strategy, "rest_api");
    const gmailCreateDraft = body.items.find(
      (item: { tool_id: string }) => item.tool_id === "mcp.gmail.create_draft"
    );
    assert.ok(gmailCreateDraft);
    assert.equal(gmailCreateDraft.name, "Gmail Create Draft");
    const gmailCreateDraftWithAttachments = body.items.find(
      (item: { tool_id: string }) =>
        item.tool_id === "mcp.gmail.create_draft_with_attachments"
    );
    assert.ok(gmailCreateDraftWithAttachments);
    assert.equal(
      gmailCreateDraftWithAttachments.name,
      "Gmail Create Draft With Attachments"
    );
    assert.equal(gmailCreateDraftWithAttachments.artifact_picker?.enabled, true);
    assert.equal(gmailCreateDraftWithAttachments.artifact_picker?.field_name, "artifactIds");
    assert.deepEqual(
      gmailCreateDraftWithAttachments.artifact_picker?.allowed_artifact_types,
      ["google_drive_export", "chat_export"]
    );
    assert.deepEqual(
      gmailCreateDraftWithAttachments.artifact_picker?.accepted_artifact_types,
      ["google_drive_export", "chat_export"]
    );
    assert.equal(
      gmailCreateDraftWithAttachments.artifact_picker?.required_consumption_mode,
      "binary_payload"
    );
    assert.equal(gmailCreateDraftWithAttachments.artifact_picker?.max_artifact_count, 3);
  });

  it("returns app-scoped artifact inventory with policy eligibility filtering", async () => {
    const artifactRoot = await fs.mkdtemp(
      path.join(os.tmpdir(), "ragenius-artifacts-list-")
    );
    temporaryArtifactRoots.add(artifactRoot);
    app = buildApp(
      {},
      buildRuntimeConfig(
        getEnv({
          DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
          ARTIFACT_STORAGE_ROOT: artifactRoot
        })
      )
    );
    await app.services.artifactStore.save(
      "app_artifacts_1",
      "google_drive_export",
      "Execution Summary.pdf",
      {
        name: "Execution Summary.pdf",
        mime_type: "application/pdf",
        content: "cGRm"
      }
    );
    await app.services.artifactStore.save(
      "app_artifacts_1",
      "chat_export",
      "session-export.md",
      {
        content: "## Export",
        format: "md",
        message_count: 1
      }
    );

    const response = await app.inject({
      method: "GET",
      url: "/v1/artifacts?app_id=app_artifacts_1&eligible_for=attachments"
    });

    assert.equal(response.statusCode, 200);
    const body = response.json();
    assert.equal(body.items.length, 2);
    const driveExport = body.items.find(
      (item: { artifact_type: string }) => item.artifact_type === "google_drive_export"
    );
    const chatExport = body.items.find(
      (item: { artifact_type: string }) => item.artifact_type === "chat_export"
    );
    assert.ok(driveExport);
    assert.equal(driveExport.display_name, "Execution Summary.pdf");
    assert.equal(driveExport.status, "ready");
    assert.equal(driveExport.consumption.default_mode, "binary_payload");
    assert.deepEqual(driveExport.consumption.supported_modes, [
      "binary_payload",
      "file_backed",
      "metadata_only",
    ]);
    assert.deepEqual(driveExport.eligible_consumers, ["gmail_attachments", "export"]);
    assert.equal(typeof driveExport.content, "undefined");
    assert.ok(chatExport);
    assert.equal(chatExport.display_name, "session-export.md");
    assert.equal(chatExport.consumption.default_mode, "file_backed");
    assert.deepEqual(chatExport.consumption.supported_modes, [
      "file_backed",
      "inline_text",
      "binary_payload",
      "metadata_only",
    ]);
    assert.deepEqual(chatExport.eligible_consumers, [
      "export",
      "future_markdown_processors",
      "gmail_attachments",
    ]);
    assert.equal(typeof chatExport.content, "undefined");
  });

  it("returns runtime skill inventory for actual registered skills", async () => {
    const runtimeConfig = buildRuntimeConfig(
      getEnv({
        DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
        NOTEBOOKLM_ENABLED: "true",
        NOTEBOOKLM_PYTHON_COMMAND: "python",
        NOTEBOOKLM_BRIDGE_SCRIPT: "scripts/notebooklm_bridge.py",
        NOTEBOOKLM_AUTH_MODE: "profile",
        NOTEBOOKLM_PROFILE: "default",
        NOTEBOOKLM_ALLOWED_OPERATIONS: "generate_video",
        ADAPTERS_JSON: JSON.stringify([
          {
            id: "adapter.notebooklm.generate_video",
            enabled: true
          }
        ]),
        MCP_SERVERS_JSON: "[]"
      })
    );
    app = buildApp({}, runtimeConfig);

    const response = await app.inject({
      method: "GET",
      url: "/v1/skills/inventory"
    });

    assert.equal(response.statusCode, 200);
    const body = response.json();
    assert.ok(Array.isArray(body.items));
    const notebooklmGenerateVideo = body.items.find(
      (item: { skill_id: string }) => item.skill_id === "notebooklm_generate_video"
    );
    assert.ok(notebooklmGenerateVideo);
    assert.equal(notebooklmGenerateVideo.exec_capable, true);
    assert.equal(notebooklmGenerateVideo.exec_kind, "skill");
    assert.ok(Array.isArray(notebooklmGenerateVideo.required_tools));
    assert.ok(notebooklmGenerateVideo.required_tools.includes("adapter.notebooklm.generate_video"));
    assert.ok(notebooklmGenerateVideo.input_schema);
    assert.ok(notebooklmGenerateVideo.output_schema);
    assert.equal(notebooklmGenerateVideo.input_schema.type, "object");
    assert.ok(notebooklmGenerateVideo.input_schema.properties.notebookTitle);
    assert.ok(notebooklmGenerateVideo.input_schema.properties.instructions);
    assert.equal(notebooklmGenerateVideo.inventory_visibility, "internal_wrapper");
    assert.equal(notebooklmGenerateVideo.workflow_kind, "single_tool_wrapper");
  });

  it("returns chat export artifact skill in runtime skill inventory", async () => {
    app = buildApp();

    const response = await app.inject({
      method: "GET",
      url: "/v1/skills/inventory"
    });

    assert.equal(response.statusCode, 200);
    const body = response.json();
    const chatExportSkill = body.items.find(
      (item: { skill_id: string }) => item.skill_id === "save_chat_export_artifact"
    );
    assert.ok(chatExportSkill);
    assert.ok(chatExportSkill.required_tools.includes("save_artifact"));
    assert.ok(chatExportSkill.input_schema);
  });

  it("returns only user-facing runtime workflows when skill inventory visibility=user", async () => {
    app = buildApp();

    const response = await app.inject({
      method: "GET",
      url: "/v1/skills/inventory?visibility=user"
    });

    assert.equal(response.statusCode, 200);
    const body = response.json();
    assert.ok(Array.isArray(body.items));
    assert.ok(
      body.items.some(
        (item: { skill_id: string; inventory_visibility?: string; workflow_kind?: string }) =>
          item.skill_id === "video_director_skill" &&
          item.inventory_visibility === "user_skill" &&
          item.workflow_kind === "multi_step_workflow"
      )
    );
    assert.ok(
      !body.items.some(
        (item: { skill_id: string }) => item.skill_id === "notebooklm_generate_video"
      )
    );
    assert.ok(
      !body.items.some(
        (item: { skill_id: string }) => item.skill_id === "gmail_create_draft"
      )
    );
  });
});

describe("execution request schema", () => {
  it("accepts a valid execution request", () => {
    const parsed = executionRequestSchema.parse({
      request_type: "execute_skill",
      app_id: "app_001",
      session_id: "sess_001",
      skill_id: "video_director_skill",
      input: {
        prompt: "Explain RAG simply",
        duration: 30
      }
    });

    assert.equal(parsed.request_type, "execute_skill");
    assert.equal(parsed.app_id, "app_001");
    assert.deepEqual(parsed.execution_options, undefined);
  });

  it("accepts a valid agent execution request", () => {
    const parsed = executionRequestSchema.parse({
      request_type: "execute_agent",
      agent_backend: "codex_cli",
      app_id: "app_001",
      session_id: "sess_001",
      agent_query: "Use NotebookLM to summarize Micah 2.",
      agent_skill_hint: "notebooklm",
      approved_content_id: "ac_123",
      approved_revision_id: "rev_123",
      context: {
        execution_mode: "sync"
      }
    });

    assert.equal(parsed.request_type, "execute_agent");
    assert.equal(parsed.agent_backend, "codex_cli");
    assert.equal(parsed.agent_skill_hint, "notebooklm");
  });

  it("rejects a request without skill_id", () => {
    assert.throws(
      () =>
        executionRequestSchema.parse({
          request_type: "execute_skill",
          app_id: "app_001",
          session_id: "sess_001",
          input: {}
        }),
      /Required/
    );
  });

  it("rejects a request with an unsupported request_type", () => {
    assert.throws(
      () =>
        executionRequestSchema.parse({
          request_type: "bad_request",
          app_id: "app_001",
          session_id: "sess_001",
          skill_id: "video_director_skill",
          input: {}
        }),
      /Invalid discriminator value/
    );
  });
});

describe("chat export artifact skill", () => {
  let app: FastifyInstance | undefined;

  afterEach(async () => {
    await app?.close();
    app = undefined;
  });

  it("persists selected chat content through save_artifact", async () => {
    app = buildApp();

    const response = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_skill",
        app_id: "app_chat_exporter",
        session_id: "sess_chat_exporter",
        skill_id: "save_chat_export_artifact",
        input: {
          name: "bible-study.md",
          displayName: "Bible Study Reviewed.md",
          content: "## 1. User\n\nWhat is RAG?",
          format: "md",
          messageCount: 1,
          sessionId: "sess_chat_exporter",
          reviewed: true,
          reviewedAt: "2026-06-12T00:00:00.000Z",
          reviewedBy: "user1",
          reviewSource: "user_marked_reviewed",
          sourceMessageIds: ["msg_1"]
        }
      }
    });

    assert.equal(response.statusCode, 200);
    const body = response.json();
    assert.equal(body.status, "completed");
    assert.equal(body.result.artifact_type, "chat_export");
    assert.equal(body.result.artifact_id.startsWith("artifact_"), true);
    assert.equal(body.result.display_name, "Bible Study Reviewed.md");
    assert.equal(body.result.reviewed, true);
    assert.equal(body.result.reviewed_at, "2026-06-12T00:00:00.000Z");
    assert.equal(body.result.reviewed_by, "user1");
    assert.equal(body.result.review_source, "user_marked_reviewed");
    assert.deepEqual(body.result.source_message_ids, ["msg_1"]);
    assert.match(body.result.path, /chat_export/);
    assert.match(body.result.file_path, /bible-study\.md$/);
    assert.equal(body.result.artifacts?.length, 1);
    assert.equal(body.result.artifacts?.[0]?.artifact_type, "chat_export");
    assert.equal(body.result.artifacts?.[0]?.display_name, "Bible Study Reviewed.md");
    assert.equal(body.result.artifacts?.[0]?.source_skill_id, "save_chat_export_artifact");
    assert.equal(body.result.artifacts?.[0]?.reviewed, true);
  });

  it("updates an existing chat export artifact as reviewed", async () => {
    app = buildApp();

    const createResponse = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_skill",
        app_id: "app_chat_exporter",
        session_id: "sess_chat_exporter",
        skill_id: "save_chat_export_artifact",
        input: {
          name: "same-turn.md",
          content: "Already exported content",
          format: "md",
          messageCount: 1,
          sessionId: "sess_chat_exporter",
          sourceMessageIds: ["msg_existing"]
        }
      }
    });
    assert.equal(createResponse.statusCode, 200);
    const artifactId = createResponse.json().result.artifact_id;

    const updateResponse = await app.inject({
      method: "PATCH",
      url: `/v1/artifacts/${artifactId}`,
      payload: {
        app_id: "app_chat_exporter",
        metadata: {
          reviewed: true,
          reviewed_at: "2026-06-12T01:00:00.000Z",
          reviewed_by: "user1",
          review_source: "user_marked_reviewed",
          source_message_ids: ["msg_existing"]
        }
      }
    });

    assert.equal(updateResponse.statusCode, 200);
    const body = updateResponse.json();
    assert.equal(body.artifact_id, artifactId);
    assert.equal(body.reviewed, true);
    assert.equal(body.reviewed_at, "2026-06-12T01:00:00.000Z");
    assert.equal(body.reviewed_by, "user1");
    assert.equal(body.review_source, "user_marked_reviewed");
    assert.deepEqual(body.source_message_ids, ["msg_existing"]);

    const inventoryResponse = await app.inject({
      method: "GET",
      url: "/v1/artifacts?app_id=app_chat_exporter&session_id=sess_chat_exporter&artifact_type=chat_export&status=ready"
    });
    assert.equal(inventoryResponse.statusCode, 200);
    const inventoryItem = inventoryResponse.json().items.find(
      (item: { artifact_id?: string }) => item.artifact_id === artifactId
    );
    assert.equal(inventoryItem.reviewed, true);
    assert.equal(inventoryItem.reviewed_by, "user1");
  });
});

describe("agent execution routes", () => {
  let app: FastifyInstance | undefined;

  afterEach(async () => {
    await app?.close();
    app = undefined;
  });

  it("accepts execute_agent requests through /v1/executions", async () => {
    app = buildApp({
      executionEngine: new ExecutionEngine({
        codexCliProvider: new CodexCliProvider(
          {
            enabled: true,
            nodeCommand: "node",
            bridgeScript: "scripts/codex_cli_bridge.js",
            command: "codex",
            args: ["exec", "--json"],
            timeoutMs: 120000
          },
          async () => ({
            ok: true,
            result: {
              final_message: "Codex route invocation succeeded.",
              activated_skills: ["notebooklm"],
              tool_summary: ["notebooklm: list notebooks"],
              artifacts: [],
              output: {
                notebooks: 3
              },
              raw_output: "{\"notebooks\":3}"
            }
          })
        )
      })
    });

    const response = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_agent",
        agent_backend: "codex_cli",
        app_id: "app_001",
        session_id: "sess_001",
        agent_query: "Use NotebookLM to summarize Micah 2.",
        agent_skill_hint: "notebooklm",
        context: {
          execution_mode: "sync"
        }
      }
    });

    assert.equal(response.statusCode, 200);
    assert.equal(response.json().status, "completed");
    assert.equal(response.json().result.backend, "codex_cli");
    assert.equal(
      response.json().result.final_message,
      "Codex route invocation succeeded."
    );
  });

  it("returns pending confirmation for write-capable execute_agent requests until confirmed", async () => {
    const executionStore = new InMemoryExecutionStore();
    app = buildApp({
      executionEngine: new ExecutionEngine({
        executionStore,
        codexCliProvider: new CodexCliProvider(
          {
            enabled: true,
            nodeCommand: "node",
            bridgeScript: "scripts/codex_cli_bridge.js",
            command: "codex",
            args: ["exec", "--json"],
            timeoutMs: 120000
          },
          async () => ({
            ok: true,
            result: {
              final_message: "Codex generated the NotebookLM video request.",
              activated_skills: ["notebooklm"],
              tool_summary: ["notebooklm: generate video"],
              artifacts: [],
              output: {
                status: "submitted"
              },
              raw_output: "{\"status\":\"submitted\"}"
            }
          })
        )
      }),
      executionStore,
    });

    const createResponse = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_agent",
        agent_backend: "codex_cli",
        app_id: "app_001",
        session_id: "sess_001",
        agent_query: "Use NotebookLM to generate a study video for Micah 2."
      }
    });

    assert.equal(createResponse.statusCode, 202);
    assert.equal(createResponse.json().status, "pending_confirmation");
    assert.equal(
      createResponse.json().result.permission_scope,
      "agent.external_write"
    );

    const confirmResponse = await app.inject({
      method: "POST",
      url: `/v1/executions/${createResponse.json().execution_id}/confirm?app_id=app_001&session_id=sess_001`,
      payload: {
        confirmation_id: createResponse.json().result.confirmation_id
      }
    });

    assert.equal(confirmResponse.statusCode, 200);
    assert.equal(confirmResponse.json().status, "completed");
    assert.equal(confirmResponse.json().result.backend, "codex_cli");
    assert.equal(
      confirmResponse.json().result.final_message,
      "Codex generated the NotebookLM video request."
    );
  });

  it("blocks destructive execute_agent requests", async () => {
    app = buildApp({
      executionEngine: new ExecutionEngine({
        codexCliProvider: new CodexCliProvider(
          {
            enabled: true,
            nodeCommand: "node",
            bridgeScript: "scripts/codex_cli_bridge.js",
            command: "codex",
            args: ["exec", "--json"],
            timeoutMs: 120000
          },
          async () => {
            throw new Error("bridge should not run for blocked agent requests");
          }
        )
      })
    });

    const response = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_agent",
        agent_backend: "codex_cli",
        app_id: "app_001",
        session_id: "sess_001",
        agent_query: "Delete the NotebookLM notebook after exporting it."
      }
    });

    assert.equal(response.statusCode, 403);
    assert.equal(response.json().error.code, "PERMISSION_BLOCKED");
    assert.equal(response.json().error.details.permission_scope, "agent.destructive");
  });
});

describe("execution engine", () => {
  afterEach(async () => {
    globalThis.fetch = originalFetch;
    await Promise.all(
      [...mutationRoots].map(async (root) => {
        await cleanupMutationRoot(root);
        mutationRoots.delete(root);
      })
    );
  });

  it("executes the sample skill end to end", async () => {
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
      }
    });

    assert.equal(result.status, "completed");
    assert.equal(result.result_type, "video");
    assert.equal(result.result.title, "Video: Explain RAG simply");
  });

  it("executes the codex agent path through the codex_cli provider", async () => {
    const engine = new ExecutionEngine({
      codexCliProvider: new CodexCliProvider(
        {
          enabled: true,
          nodeCommand: "node",
          bridgeScript: "scripts/codex_cli_bridge.js",
          command: "codex",
          args: ["exec", "--json"],
          timeoutMs: 120000
        },
        async (_config, bridgeRequest) => ({
          ok: true,
          result: {
            final_message: "Codex completed the NotebookLM request.",
            user_summary: {
              status: "completed",
              title: "NotebookLM question answered",
              subtitle: "GPT Application Designer",
              preview: "Learning GPT design offers transformative advantages."
            },
            activated_skills: bridgeRequest.agent_skill_hint
              ? [bridgeRequest.agent_skill_hint]
              : [],
            tool_summary: ["notebooklm: generate report"],
            artifacts: [],
            output: {
              status: "completed",
              request_echo: bridgeRequest.agent_query
            },
            raw_output: "{\"status\":\"completed\"}"
          }
        })
      )
    });

    const result = await engine.execute({
      request_type: "execute_agent",
      agent_backend: "codex_cli",
      app_id: "app_001",
      session_id: "sess_001",
      agent_query: "Use NotebookLM to summarize Micah 2.",
      agent_skill_hint: "notebooklm",
      approved_content_id: "ac_123",
      approved_revision_id: "rev_123",
      context: {
        execution_mode: "sync"
      }
    });

    assert.equal(result.status, "completed");
    assert.equal(result.result_type, "json");
    assert.equal(result.result.backend, "codex_cli");
    assert.equal(result.result.policy_class, "agent_read_only");
    assert.equal(result.result.workspace_access, "none");
    assert.equal(result.result.network_access, "allowlisted");
    assert.deepEqual(result.result.activated_skills, ["notebooklm"]);
    assert.deepEqual(result.result.tool_summary, ["notebooklm: generate report"]);
    assert.equal(
      result.result.final_message,
      "Codex completed the NotebookLM request."
    );
    assert.deepEqual(result.result.user_summary, {
      status: "completed",
      title: "NotebookLM question answered",
      subtitle: "GPT Application Designer",
      preview: "Learning GPT design offers transformative advantages."
    });
  });

  it("returns pending confirmation for workspace-writing codex agent requests", async () => {
    const engine = new ExecutionEngine({
      codexCliProvider: new CodexCliProvider(
        {
          enabled: true,
          nodeCommand: "node",
          bridgeScript: "scripts/codex_cli_bridge.js",
          command: "codex",
          args: ["exec", "--json"],
          timeoutMs: 120000
        },
        async () => {
          throw new Error("bridge should not run before confirmation");
        }
      )
    });

    const result = await engine.execute({
      request_type: "execute_agent",
      agent_backend: "codex_cli",
      app_id: "app_001",
      session_id: "sess_001",
      agent_query: "Patch the repo files to update the execution contract."
    });

    assert.equal(result.status, "pending_confirmation");
    assert.equal(result.result.permission_scope, "agent.workspace_write");
    assert.equal(result.result.risk_class, "agent_workspace_write");
    assert.equal(result.result.workspace_access, "scoped_write");
    assert.equal(result.result.network_access, "deny");
  });

  it("fails invalid skill input before execution", async () => {
    const engine = new ExecutionEngine();

    const result = await engine.execute({
      request_type: "execute_skill",
      app_id: "app_001",
      session_id: "sess_001",
      skill_id: "video_director_skill",
      input: {
        prompt: "Explain RAG simply",
        duration: "30"
      }
    });

    assert.equal(result.status, "failed");
    assert.equal(result.errors[0]?.code, "VALIDATION_ERROR");
  });

  it("requires confirmation before adding a NotebookLM source file", async () => {
    const adapterCalls: Array<Record<string, unknown>> = [];
    const resolutionCalls: Array<Record<string, unknown>> = [];
    const engine = new ExecutionEngine({
      async resolveScopedSkillArtifactFile(input) {
        resolutionCalls.push(input);
        return "D:\\scoped-artifacts\\reviewed-chat.md";
      },
      toolEngine: new ToolEngine({
        adapter: {
          async execute(tool, input, options) {
            adapterCalls.push({ tool_id: tool.id, input, options });
            return {
              notebook_id: "notebook_1",
              source: {
                id: "source_1",
                title: "reviewed-chat.md",
                kind: "file",
                status: "ready"
              }
            };
          }
        }
      })
    });

    const request = {
      request_type: "execute_skill",
      app_id: "app_001",
      session_id: "session-1779614072248",
      skill_id: "notebooklm_add_source_file",
      input: {
        notebookTitle: "GPT Application Designer",
        filePath: "artifact_export",
        artifactRefs: [{
          artifact_id: "artifact_export",
          field_name: "filePath",
          consumption: { resolved_mode: "file_backed" }
        }]
      }
    } as const;

    const pending = await engine.execute(request);

    assert.equal(pending.status, "pending_confirmation");
    assert.equal(pending.result.tool_id, "adapter.notebooklm.add_source_file");
    assert.equal(pending.result.permission_scope, "external_api.write");
    assert.equal(adapterCalls.length, 0);
    assert.equal(resolutionCalls.length, 0);

    const completed = await engine.execute(
      request,
      await claimPendingConfirmation(engine, pending, {
        appId: "app_001",
        sessionId: "session-1779614072248"
      })
    );

    assert.equal(completed.status, "completed");
    assert.equal(completed.result.notebook_id, "notebook_1");
    assert.equal(adapterCalls.length, 1);
    assert.equal(adapterCalls[0]?.tool_id, "adapter.notebooklm.add_source_file");
    assert.equal(
      (adapterCalls[0]?.input as Record<string, unknown>).filePath,
      "D:\\scoped-artifacts\\reviewed-chat.md"
    );
    assert.deepEqual(resolutionCalls, [{
      appId: "app_001",
      artifactId: "artifact_export",
      sessionId: "session-1779614072248"
    }]);
  });

  it("falls back to a builder-provided published skill and returns raw json output", async () => {
    const engine = new ExecutionEngine({
      permissionEngine: new PermissionEngine(),
      builderSkillClient: {
        async getBoundSkill(appId, skillId) {
          assert.equal(appId, "app_builder");
          assert.equal(skillId, "lesson_planner_skill");
          return {
            id: "lesson_planner_skill",
            name: "Lesson Planner Skill",
            version: "2.0.0",
            description: "Builder-managed lesson planner.",
            inputSchema: z.object({
              topic: z.string().min(1)
            }),
            outputSchema: z.object({
              items: z.array(z.unknown())
            }),
            requiredTools: ["rag_retrieval_tool"],
            requiredPermissions: ["rag.read"],
            workflowDefinition: {
              steps: [
                {
                  id: "retrieve_context",
                  type: "tool_call",
                  toolId: "rag_retrieval_tool",
                  inputMapping: {
                    query: "$.input.topic",
                    topK: 3
                  },
                  outputMapping: {
                    items: "$.output.items"
                  },
                  on: { success: "finish" }
                },
                {
                  id: "finish",
                  type: "end"
                }
              ]
            },
            enabled: true,
            resultType: "json"
          };
        }
      }
    });

    const result = await engine.execute({
      request_type: "execute_skill",
      app_id: "app_builder",
      session_id: "sess_builder",
      skill_id: "lesson_planner_skill",
      input: {
        topic: "Explain retrieval"
      }
    });

    assert.equal(result.status, "completed");
    assert.equal(result.result_type, "json");
    assert.ok(Array.isArray(result.result.items));
    assert.equal(result.files.length, 0);
  });

  it("applies builder binding auto-allow mode to a side-effecting builder-managed skill", async () => {
    const engine = new ExecutionEngine({
      permissionEngine: new PermissionEngine(),
      builderSkillClient: {
        async getBoundSkill(appId, skillId) {
          assert.equal(appId, "app_builder_write");
          assert.equal(skillId, "builder_video_skill");
          return {
            id: "builder_video_skill",
            name: "Builder Video Skill",
            version: "1.0.0",
            inputSchema: z.object({
              prompt: z.string().min(1),
              duration: z.number().int().positive()
            }),
            outputSchema: z.object({
              title: z.string(),
              summary: z.string()
            }),
            requiredTools: ["mock_video_generation_tool"],
            requiredPermissions: ["external_api.write"],
            workflowDefinition: {
              steps: [
                {
                  id: "generate_video",
                  type: "tool_call",
                  toolId: "mock_video_generation_tool",
                  inputMapping: {
                    prompt: "$.input.prompt",
                    duration: "$.input.duration"
                  },
                  outputMapping: {
                    title: "$.output.title",
                    summary: "$.output.summary"
                  },
                  on: { success: "finish" }
                },
                {
                  id: "finish",
                  type: "end"
                }
              ]
            },
            enabled: true,
            confirmationMode: "auto_allow",
            resultType: "json"
          };
        }
      }
    });

    const result = await engine.execute({
      request_type: "execute_skill",
      app_id: "app_builder_write",
      session_id: "sess_builder_write",
      skill_id: "builder_video_skill",
      input: {
        prompt: "Explain RAG simply",
        duration: 30
      }
    });

    assert.equal(result.status, "completed");
    assert.equal(result.result_type, "json");
    assert.equal(result.result.title, "Video: Explain RAG simply");
  });

  it("applies builder binding require-confirmation mode to a side-effecting builder-managed skill", async () => {
    const engine = new ExecutionEngine({
      permissionEngine: new PermissionEngine(),
      builderSkillClient: {
        async getBoundSkill(appId, skillId) {
          assert.equal(appId, "app_builder_confirm");
          assert.equal(skillId, "builder_video_skill");
          return {
            id: "builder_video_skill",
            name: "Builder Video Skill",
            version: "1.0.0",
            inputSchema: z.object({
              prompt: z.string().min(1),
              duration: z.number().int().positive()
            }),
            outputSchema: z.object({
              title: z.string(),
              summary: z.string()
            }),
            requiredTools: ["mock_video_generation_tool"],
            requiredPermissions: ["external_api.write"],
            workflowDefinition: {
              steps: [
                {
                  id: "generate_video",
                  type: "tool_call",
                  toolId: "mock_video_generation_tool",
                  inputMapping: {
                    prompt: "$.input.prompt",
                    duration: "$.input.duration"
                  },
                  outputMapping: {
                    title: "$.output.title",
                    summary: "$.output.summary"
                  },
                  on: { success: "finish" }
                },
                {
                  id: "finish",
                  type: "end"
                }
              ]
            },
            enabled: true,
            confirmationMode: "require_confirmation",
            resultType: "json"
          };
        }
      }
    });

    const result = await engine.execute({
      request_type: "execute_skill",
      app_id: "app_builder_confirm",
      session_id: "sess_builder_confirm",
      skill_id: "builder_video_skill",
      input: {
        prompt: "Explain RAG simply",
        duration: 30
      }
    });

    assert.equal(result.status, "pending_confirmation");
    assert.equal(result.result.tool_id, "mock_video_generation_tool");
  });

  it("executes a builder-provided research paper finder skill through the paper search tool", async () => {
    globalThis.fetch = (async (input: string | URL) => {
      const url = String(input);
      assert.match(url, /export\.arxiv\.org\/api\/query/);
      return new Response(
        `<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00011v1</id>
    <title>Retrieval Augmented Generation for DeepSeek</title>
    <summary>Applied research summary.</summary>
    <published>2024-03-01T00:00:00Z</published>
    <author><name>Test Author</name></author>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.00012v1</id>
    <title>Expert Routing for DeepSeek</title>
    <summary>Applied research summary two.</summary>
    <published>2023-03-01T00:00:00Z</published>
    <author><name>Second Author</name></author>
  </entry>
</feed>`,
        { status: 200, headers: { "Content-Type": "application/atom+xml" } }
      );
    }) as typeof fetch;

    const engine = new ExecutionEngine({
      permissionEngine: new PermissionEngine(),
      builderSkillClient: {
        async getBoundSkill(appId, skillId) {
          assert.equal(appId, "app_research");
          assert.equal(skillId, "research_paper_finder");
          return {
            id: "research_paper_finder",
            name: "research-paper-finder",
            version: "1.0.0",
            description: "Builder-managed research paper finder.",
            inputSchema: z.object({
              topic: z.string().min(1),
              limit: z.number().int().positive().max(10).optional(),
              source: z.enum(["auto", "arxiv", "semantic-scholar"]).optional()
            }),
            outputSchema: z.object({
              topic: z.string(),
              source: z.string(),
              papers: z.array(
                z.object({
                  title: z.string(),
                  link: z.string(),
                  year: z.number().int(),
                  authors: z.array(z.string()),
                  summary: z.string(),
                  why_it_matters: z.string()
                })
              )
            }),
            requiredTools: ["research_paper_search_tool"],
            requiredPermissions: ["external_api.read"],
            workflowDefinition: {
              steps: [
                {
                  id: "search_papers",
                  type: "tool_call",
                  toolId: "research_paper_search_tool",
                  inputMapping: {
                    topic: "$.input.topic",
                    limit: "$.input.limit",
                    source: "$.input.source"
                  },
                  outputMapping: {
                    topic: "$.output.topic",
                    source: "$.output.source",
                    papers: "$.output.papers"
                  },
                  on: { success: "finish" }
                },
                {
                  id: "finish",
                  type: "end"
                }
              ]
            },
            enabled: true,
            resultType: "json"
          };
        }
      }
    });

    const result = await engine.execute({
      request_type: "execute_skill",
      app_id: "app_research",
      session_id: "sess_research",
      skill_id: "research_paper_finder",
      input: {
        topic: "retrieval augmented generation",
        limit: 2,
        source: "auto"
      }
    });
    const payload = result.result as {
      topic: string;
      source: string;
      papers: Array<{ title: string }>;
    };

    assert.equal(result.status, "completed");
    assert.equal(result.result_type, "json");
    assert.equal(payload.topic, "retrieval augmented generation");
    assert.equal(payload.source, "arxiv");
    assert.equal(payload.papers.length, 2);
    assert.ok(payload.papers[0]);
    assert.match(payload.papers[0].title, /retrieval augmented generation/i);
  });

  it("executes a normalized file inventory contract", async () => {
    const runtimeConfig = buildRuntimeConfig(
      getEnv({
        DATABASE_URL:
          "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
        FILESYSTEM_ALLOWED_ROOTS: repositoryDocsRoot,
        ARTIFACT_STORAGE_ROOT: path.join(repositoryOutputsRoot, "test-artifacts-runtime"),
        MCP_SERVERS_JSON: "[]"
      })
    );
    const engine = new ExecutionEngine({
      permissionEngine: new PermissionEngine([
        {
          appId: "app_file_inventory",
          toolId: "list_files",
          scope: "filesystem.read",
          mode: "auto_allow"
        },
        {
          appId: "app_file_inventory",
          toolId: "save_artifact",
          scope: "artifact.write",
          mode: "auto_allow"
        }
      ]),
      toolEngine: createAppServices({}, runtimeConfig).toolEngine
    });

    const result = await engine.execute({
      request_type: "execute_skill",
      app_id: "app_file_inventory",
      session_id: "session-1",
      skill_id: "file_inventory",
      input: {
        path: repositoryDocsRoot
      },
      execution_options: { dry_run: false }
    });

    assert.equal(result.status, "completed");
    assert.equal(result.result_type, "json");
    assert.ok((result.result as { artifact_id?: string }).artifact_id);
  });

  it("executes a confirmed mutation skill within allowed roots", async () => {
    const tempRoot = path.join(
      repositoryOutputsRoot,
      `test-mutation-runtime-${Date.now()}`
    );
    mutationRoots.add(tempRoot);
    await fs.mkdir(tempRoot, { recursive: true });
    const targetPath = path.join(tempRoot, "content.md");
    await fs.writeFile(targetPath, "before", "utf-8");

    const runtimeConfig = buildRuntimeConfig(
      getEnv({
        DATABASE_URL:
          "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
        FILESYSTEM_ALLOWED_ROOTS: tempRoot,
        FILESYSTEM_MUTATION_ROOTS: tempRoot,
        FILESYSTEM_MAX_WRITE_BYTES: "4096",
        FILESYSTEM_MAX_PATCH_BYTES: "4096",
        ARTIFACT_STORAGE_ROOT: path.join(repositoryOutputsRoot, "test-artifacts-runtime"),
        MCP_SERVERS_JSON: "[]"
      })
    );
    const engine = new ExecutionEngine({
      permissionEngine: new PermissionEngine([
        {
          appId: "app_writer",
          toolId: "write_file",
          scope: "filesystem.write",
          mode: "require_confirmation"
        }
      ]),
      toolEngine: createAppServices({}, runtimeConfig).toolEngine
    });

    const pending = await engine.execute({
      request_type: "execute_skill",
      app_id: "app_writer",
      session_id: "sess_writer",
      skill_id: "content_replace",
      input: {
        path: targetPath,
        content: "after"
      }
    });
    assert.equal(pending.status, "pending_confirmation");
    assert.ok(pending.execution_id);

    const confirmed = await engine.execute(
      {
        request_type: "execute_skill",
        app_id: "app_writer",
        session_id: "sess_writer",
        skill_id: "content_replace",
        input: {
          path: targetPath,
          content: "after"
        }
      },
      await claimPendingConfirmation(engine, pending, {
        appId: "app_writer",
        sessionId: "sess_writer"
      })
    );

    assert.equal(confirmed.status, "completed");
    assert.equal(await fs.readFile(targetPath, "utf-8"), "after");
  });

  it("executes an adapter-backed skill through the service call seam", async () => {
    const runtimeConfig = buildRuntimeConfig(
      getEnv({
        DATABASE_URL:
          "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
        ADAPTERS_JSON: JSON.stringify([
          {
            id: "content_transform_adapter",
            command: "transform",
            enabled: true
          }
        ]),
        MCP_SERVERS_JSON: "[]"
      })
    );
    const engine = new ExecutionEngine({
      permissionEngine: new PermissionEngine([
        {
          appId: "app_adapter",
          toolId: "content_transform_adapter",
          scope: "adapter.execute",
          mode: "auto_allow"
        }
      ]),
      toolEngine: createAppServices({}, runtimeConfig).toolEngine
    });

    const result = await engine.execute({
      request_type: "execute_skill",
      app_id: "app_adapter",
      session_id: "sess_adapter",
      skill_id: "adapter_content_transform",
      input: {
        content: "hello"
      }
    });

    assert.equal(result.status, "completed");
    assert.equal(result.result_type, "json");
    assert.deepEqual(result.result, { output: "HELLO" });
  });

  it("executes a notebooklm ask skill through the adapter service seam", async () => {
    const runtimeConfig = buildRuntimeConfig(
      getEnv({
        DATABASE_URL:
          "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
        NOTEBOOKLM_ENABLED: "true",
        NOTEBOOKLM_ALLOWED_OPERATIONS: "ask,list_notebooks",
        ADAPTERS_JSON: JSON.stringify([
          {
            id: "adapter.notebooklm.ask",
            command: "python",
            args: ["scripts/notebooklm_bridge.py"],
            enabled: true
          }
        ]),
        MCP_SERVERS_JSON: "[]"
      })
    );

    const notebooklmAdapter = new NotebookLmAdapter(
      runtimeConfig.providers.notebooklm,
      async (request) => {
        if (request.operation === "list_notebooks") {
          return {
            ok: true,
            result: {
              notebooks: [{ id: "nb_1", title: "Research", sources_count: 1 }]
            }
          };
        }

        assert.equal(request.operation, "ask");
        assert.equal(request.arguments.notebookId, "nb_1");
        assert.equal(request.arguments.question, "What are the main themes?");

        return {
          ok: true,
          result: {
            answer: "The main themes are synthesis and evidence.",
            conversation_id: "conv_1",
            references: [{ source_id: "src_1", title: "Paper A" }],
            turn_number: 1
          }
        };
      }
    );

    const engine = new ExecutionEngine({
      permissionEngine: new PermissionEngine([
        {
          appId: "app_notebooklm",
          toolId: "adapter.notebooklm.ask",
          scope: "external_api.read",
          mode: "auto_allow"
        }
      ]),
      toolEngine: new ToolEngine(
        {
          adapter: new AdapterToolProvider(runtimeConfig.adapters, {
            notebooklmAdapter
          })
        },
        new PermissionEngine([
          {
            appId: "app_notebooklm",
            toolId: "adapter.notebooklm.ask",
            scope: "external_api.read",
            mode: "auto_allow"
          }
        ])
      )
    });

    const result = await engine.execute({
      request_type: "execute_skill",
      app_id: "app_notebooklm",
      session_id: "sess_notebooklm",
      skill_id: "notebooklm_existing_notebook_ask",
      input: {
        notebookTitle: "Research",
        question: "What are the main themes?"
      }
    });

    assert.equal(result.status, "completed");
    assert.equal(result.result_type, "json");
    assert.deepEqual(result.result, {
      answer: "The main themes are synthesis and evidence.",
      conversation_id: "conv_1",
      references: [{ source_id: "src_1", title: "Paper A" }],
      turn_number: 1
    });
  });

  it("executes a notebooklm generate report skill through the adapter service seam", async () => {
    const artifactRoot = path.join(
      repositoryOutputsRoot,
      `test-notebooklm-runtime-${Date.now()}`
    );
    mutationRoots.add(artifactRoot);
    const runtimeConfig = buildRuntimeConfig(
      getEnv({
        DATABASE_URL:
          "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
        ARTIFACT_STORAGE_ROOT: artifactRoot,
        NOTEBOOKLM_ENABLED: "true",
        NOTEBOOKLM_ALLOWED_OPERATIONS: "generate_report",
        ADAPTERS_JSON: JSON.stringify([
          {
            id: "adapter.notebooklm.generate_report",
            command: "python",
            args: ["scripts/notebooklm_bridge.py"],
            enabled: true
          }
        ]),
        MCP_SERVERS_JSON: "[]"
      })
    );

    const notebooklmAdapter = new NotebookLmAdapter(
      runtimeConfig.providers.notebooklm,
      async () => ({
        ok: true,
        result: {
          notebook_id: "nb_1",
          artifact_kind: "report",
          task_id: "task_1",
          status: "completed",
          content_markdown: "# NotebookLM Report"
        }
      }),
      {
        artifactStore: new ArtifactStore(artifactRoot)
      }
    );

    const permissions = new PermissionEngine([
      {
        appId: "app_notebooklm_write",
        toolId: "adapter.notebooklm.generate_report",
        scope: "external_api.write",
        mode: "auto_allow"
      }
    ]);

    const engine = new ExecutionEngine({
      permissionEngine: permissions,
      toolEngine: new ToolEngine(
        {
          adapter: new AdapterToolProvider(runtimeConfig.adapters, {
            notebooklmAdapter
          })
        },
        permissions
      )
    });

    const request = {
      request_type: "execute_skill",
      app_id: "app_notebooklm_write",
      session_id: "sess_notebooklm_write",
      skill_id: "notebooklm_generate_report",
      input: {
        notebookId: "nb_1",
        customPrompt: "Summarize the notebook"
      }
    } as const;
    const pending = await engine.execute(request);
    const result = await engine.execute(
      request,
      await claimPendingConfirmation(engine, pending, {
        appId: "app_notebooklm_write",
        sessionId: "sess_notebooklm_write"
      })
    );

    assert.equal(result.status, "completed");
    assert.equal(result.result_type, "json");
    assert.equal(result.result.notebook_id, "nb_1");
    assert.equal(result.result.artifact_kind, "report");
    assert.equal(result.result.task_id, "task_1");
    assert.equal(result.result.status, "completed");
    assert.equal(result.result.content_markdown, "# NotebookLM Report");
    const artifacts = (result.result as { artifacts?: Array<Record<string, unknown>> }).artifacts;
    assert.equal(artifacts?.length, 1);
    assert.equal(artifacts?.[0]?.artifact_type, "notebooklm_report");
    assert.equal(artifacts?.[0]?.display_name, "NotebookLM Report - nb_1.md");
  });

  it("executes a notebooklm poll artifact task skill through the adapter service seam", async () => {
    const runtimeConfig = buildRuntimeConfig(
      getEnv({
        DATABASE_URL:
          "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
        NOTEBOOKLM_ENABLED: "true",
        NOTEBOOKLM_ALLOWED_OPERATIONS: "poll_artifact_task",
        ADAPTERS_JSON: JSON.stringify([
          {
            id: "adapter.notebooklm.poll_artifact_task",
            command: "python",
            args: ["scripts/notebooklm_bridge.py"],
            enabled: true
          }
        ]),
        MCP_SERVERS_JSON: "[]"
      })
    );

    const notebooklmAdapter = new NotebookLmAdapter(
      runtimeConfig.providers.notebooklm,
      async () => ({
        ok: true,
        result: {
          notebook_id: "nb_1",
          artifact_kind: "video",
          task_id: "task_video_1",
          status: "completed"
        }
      })
    );

    const permissions = new PermissionEngine([
      {
        appId: "app_notebooklm_poll",
        toolId: "adapter.notebooklm.poll_artifact_task",
        scope: "external_api.read",
        mode: "auto_allow"
      }
    ]);

    const engine = new ExecutionEngine({
      permissionEngine: permissions,
      toolEngine: new ToolEngine(
        {
          adapter: new AdapterToolProvider(runtimeConfig.adapters, {
            notebooklmAdapter
          })
        },
        permissions
      )
    });

    const result = await engine.execute({
      request_type: "execute_skill",
      app_id: "app_notebooklm_poll",
      session_id: "sess_notebooklm_poll",
      skill_id: "notebooklm_poll_artifact_task",
      input: {
        notebookId: "nb_1",
        taskId: "task_video_1",
        artifactKind: "video"
      }
    });

    assert.equal(result.status, "completed");
    assert.equal(result.result_type, "json");
    assert.equal(result.result.notebook_id, "nb_1");
    assert.equal(result.result.artifact_kind, "video");
    assert.equal(result.result.task_id, "task_video_1");
    assert.equal(result.result.status, "completed");
  });
});

describe("execution routes", () => {
  let app: FastifyInstance | undefined;

  afterEach(async () => {
    await app?.close();
    app = undefined;
    globalThis.fetch = originalFetch;
  });

  it("returns completed execution from POST /v1/executions", async () => {
    app = buildApp({
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
        }
      }
    });

    assert.equal(response.statusCode, 200);
    assert.equal(response.json().status, "completed");
    assert.match(response.json().execution_id, /^execution_/);
  });

  it("returns persisted execution records from GET /v1/executions/:execution_id", async () => {
    app = buildApp({
      permissionEngine: new PermissionEngine([
        {
          appId: "app_001",
          toolId: "mock_video_generation_tool",
          scope: "external_api.write",
          mode: "auto_allow"
        }
      ])
    });

    const createResponse = await app.inject({
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
        }
      }
    });

    const executionId = createResponse.json().execution_id;
    const response = await app.inject({
      method: "GET",
      url: `/v1/executions/${executionId}?app_id=app_001&session_id=sess_001`
    });

    assert.equal(response.statusCode, 200);
    assert.equal(response.json().execution_id, executionId);
    assert.equal(response.json().status, "completed");
  });

  it("returns persisted execution logs from GET /v1/executions/:execution_id/logs", async () => {
    app = buildApp({
      permissionEngine: new PermissionEngine([
        {
          appId: "app_001",
          toolId: "mock_video_generation_tool",
          scope: "external_api.write",
          mode: "auto_allow"
        }
      ])
    });

    const createResponse = await app.inject({
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
        }
      }
    });

    const executionId = createResponse.json().execution_id;
    const response = await app.inject({
      method: "GET",
      url: `/v1/executions/${executionId}/logs?app_id=app_001&session_id=sess_001`
    });

    assert.equal(response.statusCode, 200);
    assert.equal(response.json().execution_id, executionId);
    assert.equal(Array.isArray(response.json().logs), true);
    assert.equal(response.json().logs[0]?.message, "Skill completed in 3 steps with 2 tool calls.");
  });

  it("discovers MCP tools and executes a search skill through the MCP provider", async () => {
    const runtimeConfig = buildRuntimeConfig(
      getEnv({
        DATABASE_URL:
          "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
        MCP_SERVERS_JSON: JSON.stringify([
          {
            id: "cms",
            transport: "stdio",
            command: "mock-mcp",
            args: [],
            enabled: true
          }
        ])
      })
    );
    app = buildApp(
      {
        permissionEngine: new PermissionEngine([
          {
            appId: "app_mcp_reader",
            toolId: "mcp.cms.search_pages",
            scope: "external_api.read",
            mode: "auto_allow"
          }
        ])
      },
      runtimeConfig
    );

    const discoverResponse = await app.inject({
      method: "POST",
      url: "/v1/tools/discover/mcp",
      payload: {
        provider_id: "cms"
      }
    });
    assert.equal(discoverResponse.statusCode, 200);
    assert.equal(discoverResponse.json().tools_discovered[0]?.tool_id, "mcp.cms.search_pages");

    const response = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_skill",
        app_id: "app_mcp_reader",
        session_id: "sess_mcp_reader",
        skill_id: "mcp_page_search",
        input: {
          query: "homepage"
        }
      }
    });

    assert.equal(response.statusCode, 200);
    assert.equal(response.json().status, "completed");
    assert.deepEqual(response.json().result.results, [
      {
        id: "page_1",
        title: "Homepage"
      }
    ]);
  });

  it("discovers Gmail MCP tools and executes a read-only Gmail skill", async () => {
    globalThis.fetch = (async (_input: string | URL | Request, init?: RequestInit) => {
      const payload = JSON.parse(String(init?.body ?? "{}")) as { method?: string };

      if (payload.method === "initialize") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 1,
            result: { protocolVersion: "2025-06-18" }
          }),
          {
            status: 200,
            headers: {
              "Content-Type": "application/json",
              "Mcp-Session-Id": "gmail-session-1"
            }
          }
        );
      }

      if (payload.method === "notifications/initialized") {
        return new Response("", {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (payload.method === "tools/list") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 2,
            result: {
              tools: [
                {
                  name: "search_messages",
                  title: "Search Messages"
                },
                {
                  name: "send_message",
                  title: "Send Message"
                }
              ]
            }
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" }
          }
        );
      }

      return new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          id: 3,
          result: {
            structuredContent: {
              results: [
                {
                  id: "msg-1",
                  subject: "Hello from Gmail",
                  snippet: "Preview text"
                }
              ]
            }
          }
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" }
        }
      );
    }) as typeof fetch;

    const sourceEnv = {
      DATABASE_URL:
        "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
      GMAIL_MCP_ACCESS_TOKEN: "gmail-token",
      MCP_SERVERS_JSON: JSON.stringify([
        {
          id: "gmail",
          transport: "http",
          baseUrl: "https://gmailmcp.googleapis.com/mcp/v1",
          authTokenEnv: "GMAIL_MCP_ACCESS_TOKEN",
          allowedToolNames: ["search_messages"],
          enabled: true
        }
      ])
    } as NodeJS.ProcessEnv;
    const runtimeConfig = buildRuntimeConfig(getEnv(sourceEnv), sourceEnv);
    app = buildApp(
      {
        permissionEngine: new PermissionEngine([
          {
            appId: "app_gmail_reader",
            toolId: "mcp.gmail.search_messages",
            scope: "external_api.read",
            mode: "auto_allow"
          }
        ])
      },
      runtimeConfig
    );

    const discoverResponse = await app.inject({
      method: "POST",
      url: "/v1/tools/discover/mcp",
      payload: {
        provider_id: "gmail"
      }
    });
    assert.equal(discoverResponse.statusCode, 200);
    assert.equal(discoverResponse.json().tools_discovered.length, 1);
    assert.equal(
      discoverResponse.json().tools_discovered[0]?.tool_id,
      "mcp.gmail.search_messages"
    );

    const response = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_skill",
        app_id: "app_gmail_reader",
        session_id: "sess_gmail_reader",
        skill_id: "gmail_message_search",
        input: {
          query: "from:alice@example.com"
        }
      }
    });

    assert.equal(response.statusCode, 200);
    assert.equal(response.json().status, "completed");
    assert.deepEqual(response.json().result.results, [
      {
        id: "msg-1",
        subject: "Hello from Gmail",
        snippet: "Preview text"
      }
    ]);
  });

  it("discovers Google Docs MCP tools and executes a read-only Docs skill", async () => {
    globalThis.fetch = (async (_input: string | URL | Request, init?: RequestInit) => {
      const payload = JSON.parse(String(init?.body ?? "{}")) as { method?: string };

      if (payload.method === "initialize") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 1,
            result: { protocolVersion: "2025-06-18" }
          }),
          {
            status: 200,
            headers: {
              "Content-Type": "application/json",
              "Mcp-Session-Id": "gdocs-session-1"
            }
          }
        );
      }

      if (payload.method === "notifications/initialized") {
        return new Response("", {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (payload.method === "tools/list") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 2,
            result: {
              tools: [
                {
                  name: "search_documents",
                  title: "Search Documents"
                },
                {
                  name: "update_document",
                  title: "Update Document"
                }
              ]
            }
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" }
          }
        );
      }

      return new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          id: 3,
          result: {
            structuredContent: {
              results: [
                {
                  id: "doc-1",
                  title: "Product Strategy",
                  webViewLink: "https://docs.google.com/document/d/doc-1/edit"
                }
              ]
            }
          }
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" }
        }
      );
    }) as typeof fetch;

    const sourceEnv = {
      DATABASE_URL:
        "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
      GOOGLE_DOCS_MCP_ACCESS_TOKEN: "gdocs-token",
      MCP_SERVERS_JSON: JSON.stringify([
        {
          id: "gdocs",
          transport: "http",
          baseUrl: "https://google-docs-mcp.example.com/mcp/v1",
          authTokenEnv: "GOOGLE_DOCS_MCP_ACCESS_TOKEN",
          allowedToolNames: ["search_documents"],
          enabled: true
        }
      ])
    } as NodeJS.ProcessEnv;
    const runtimeConfig = buildRuntimeConfig(getEnv(sourceEnv), sourceEnv);
    app = buildApp(
      {
        permissionEngine: new PermissionEngine([
          {
            appId: "app_gdocs_reader",
            toolId: "mcp.gdocs.search_documents",
            scope: "external_api.read",
            mode: "auto_allow"
          }
        ])
      },
      runtimeConfig
    );

    const discoverResponse = await app.inject({
      method: "POST",
      url: "/v1/tools/discover/mcp",
      payload: {
        provider_id: "gdocs"
      }
    });
    assert.equal(discoverResponse.statusCode, 200);
    assert.equal(discoverResponse.json().tools_discovered.length, 1);
    assert.equal(
      discoverResponse.json().tools_discovered[0]?.tool_id,
      "mcp.gdocs.search_documents"
    );

    const response = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_skill",
        app_id: "app_gdocs_reader",
        session_id: "sess_gdocs_reader",
        skill_id: "google_docs_search",
        input: {
          query: "strategy"
        }
      }
    });

    assert.equal(response.statusCode, 200);
    assert.equal(response.json().status, "completed");
    assert.deepEqual(response.json().result.results, [
      {
        id: "doc-1",
        title: "Product Strategy",
        webViewLink: "https://docs.google.com/document/d/doc-1/edit"
      }
    ]);
  });

  it("discovers Google Drive MCP tools and executes a read-only Drive skill", async () => {
    globalThis.fetch = (async (_input: string | URL | Request, init?: RequestInit) => {
      const payload = JSON.parse(String(init?.body ?? "{}")) as { method?: string };

      if (payload.method === "initialize") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 1,
            result: { protocolVersion: "2025-06-18" }
          }),
          {
            status: 200,
            headers: {
              "Content-Type": "application/json",
              "Mcp-Session-Id": "gdrive-session-1"
            }
          }
        );
      }

      if (payload.method === "notifications/initialized") {
        return new Response("", {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (payload.method === "tools/list") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 2,
            result: {
              tools: [
                {
                  name: "search_files",
                  title: "Search Files"
                },
                {
                  name: "delete_file",
                  title: "Delete File"
                }
              ]
            }
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" }
          }
        );
      }

      return new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          id: 3,
          result: {
            structuredContent: {
              results: [
                {
                  id: "file-1",
                  name: "Quarterly Plan.pdf",
                  webViewLink: "https://drive.google.com/file/d/file-1/view"
                }
              ]
            }
          }
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" }
        }
      );
    }) as typeof fetch;

    const sourceEnv = {
      DATABASE_URL:
        "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
      GOOGLE_DRIVE_MCP_ACCESS_TOKEN: "gdrive-token",
      MCP_SERVERS_JSON: JSON.stringify([
        {
          id: "gdrive",
          transport: "http",
          baseUrl: "https://google-drive-mcp.example.com/mcp/v1",
          authTokenEnv: "GOOGLE_DRIVE_MCP_ACCESS_TOKEN",
          allowedToolNames: ["search_files"],
          enabled: true
        }
      ])
    } as NodeJS.ProcessEnv;
    const runtimeConfig = buildRuntimeConfig(getEnv(sourceEnv), sourceEnv);
    app = buildApp(
      {
        permissionEngine: new PermissionEngine([
          {
            appId: "app_gdrive_reader",
            toolId: "mcp.gdrive.search_files",
            scope: "external_api.read",
            mode: "auto_allow"
          }
        ])
      },
      runtimeConfig
    );

    const discoverResponse = await app.inject({
      method: "POST",
      url: "/v1/tools/discover/mcp",
      payload: {
        provider_id: "gdrive"
      }
    });
    assert.equal(discoverResponse.statusCode, 200);
    assert.equal(discoverResponse.json().tools_discovered.length, 1);
    assert.equal(
      discoverResponse.json().tools_discovered[0]?.tool_id,
      "mcp.gdrive.search_files"
    );

    const response = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_skill",
        app_id: "app_gdrive_reader",
        session_id: "sess_gdrive_reader",
        skill_id: "google_drive_search",
        input: {
          query: "quarterly"
        }
      }
    });

    assert.equal(response.statusCode, 200);
    assert.equal(response.json().status, "completed");
    assert.deepEqual(response.json().result.results, [
      {
        id: "file-1",
        name: "Quarterly Plan.pdf",
        webViewLink: "https://drive.google.com/file/d/file-1/view"
      }
    ]);
  });

  it("discovers Google Drive download MCP tools and stores downloaded content as an artifact", async () => {
    globalThis.fetch = (async (_input: string | URL | Request, init?: RequestInit) => {
      const payload = JSON.parse(String(init?.body ?? "{}")) as { method?: string };

      if (payload.method === "initialize") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 1,
            result: { protocolVersion: "2025-06-18" }
          }),
          {
            status: 200,
            headers: {
              "Content-Type": "application/json",
              "Mcp-Session-Id": "gdrive-session-2"
            }
          }
        );
      }

      if (payload.method === "notifications/initialized") {
        return new Response("", {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (payload.method === "tools/list") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 2,
            result: {
              tools: [
                {
                  name: "download_file_content",
                  title: "Download File Content"
                }
              ]
            }
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" }
          }
        );
      }

      return new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          id: 3,
          result: {
            structuredContent: {
              file_id: "file-1",
              name: "Quarterly Plan.pdf",
              mime_type: "application/pdf",
              content: "cGRmLWNvbnRlbnQ=",
              content_encoding: "base64"
            }
          }
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" }
        }
      );
    }) as typeof fetch;

    const sourceEnv = {
      DATABASE_URL:
        "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
      GOOGLE_DRIVE_MCP_ACCESS_TOKEN: "gdrive-token",
      ARTIFACT_STORAGE_ROOT: path.join(repositoryOutputsRoot, "test-artifacts-runtime"),
      MCP_SERVERS_JSON: JSON.stringify([
        {
          id: "gdrive",
          transport: "http",
          baseUrl: "https://drivemcp.googleapis.com/mcp/v1",
          authTokenEnv: "GOOGLE_DRIVE_MCP_ACCESS_TOKEN",
          allowedToolNames: ["search_files", "download_file_content"],
          enabled: true
        }
      ])
    } as NodeJS.ProcessEnv;
    const runtimeConfig = buildRuntimeConfig(getEnv(sourceEnv), sourceEnv);
    app = buildApp(
      {
        permissionEngine: new PermissionEngine([
          {
            appId: "app_gdrive_exporter",
            toolId: "mcp.gdrive.download_file_content",
            scope: "external_api.read",
            mode: "auto_allow"
          },
          {
            appId: "app_gdrive_exporter",
            toolId: "save_artifact",
            scope: "artifact.write",
            mode: "auto_allow"
          }
        ])
      },
      runtimeConfig
    );

    const discoverResponse = await app.inject({
      method: "POST",
      url: "/v1/tools/discover/mcp",
      payload: {
        provider_id: "gdrive"
      }
    });
    assert.equal(discoverResponse.statusCode, 200);
    assert.ok(
      discoverResponse
        .json()
        .tools_discovered.some(
          (tool: { tool_id: string }) =>
            tool.tool_id === "mcp.gdrive.download_file_content"
        )
    );

    const response = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_skill",
        app_id: "app_gdrive_exporter",
        session_id: "sess_gdrive_exporter",
        skill_id: "google_drive_download_file",
        input: {
          fileId: "file-1"
        }
      }
    });

    assert.equal(response.statusCode, 200);
    assert.equal(response.json().status, "completed");
    assert.equal(response.json().result.file_id, "file-1");
    assert.equal(response.json().result.artifact_type, "google_drive_export");
    assert.match(response.json().result.path, /app_gdrive_exporter/);
    assert.match(response.json().result.path, /google_drive_export/);
    assert.equal(response.json().result.artifacts?.length, 1);
    assert.equal(
      response.json().result.artifacts?.[0]?.artifact_type,
      "google_drive_export"
    );
      assert.equal(
        response.json().result.artifacts?.[0]?.display_name,
        "Quarterly Plan.pdf"
      );
    assert.equal(
      response.json().execution_provenance?.[0]?.execution_path,
      "mcp"
    );
  });

  it("records rest fallback provenance when Google Drive download falls back from MCP to Drive REST", async () => {
    globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);

      if (url.startsWith("https://www.googleapis.com/drive/v3/files/file-2?fields=")) {
        return new Response(
          JSON.stringify({
            id: "file-2",
            name: "Quarterly Plan.pdf",
            mimeType: "application/pdf"
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }

      if (url === "https://www.googleapis.com/drive/v3/files/file-2?alt=media") {
        return new Response(Buffer.from("pdf-content"), {
          status: 200,
          headers: { "Content-Type": "application/pdf" }
        });
      }

      const payload = JSON.parse(String(init?.body ?? "{}")) as { method?: string };

      if (payload.method === "initialize") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 1,
            result: { protocolVersion: "2025-06-18" }
          }),
          {
            status: 200,
            headers: {
              "Content-Type": "application/json",
              "Mcp-Session-Id": "gdrive-session-fallback"
            }
          }
        );
      }

      if (payload.method === "notifications/initialized") {
        return new Response("", {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (payload.method === "tools/list") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 2,
            result: {
              tools: [
                {
                  name: "download_file_content",
                  title: "Download File Content"
                }
              ]
            }
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" }
          }
        );
      }

      return new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          id: 3,
          result: {
            content: [{ type: "text", text: "The caller does not have permission" }],
            isError: true
          }
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" }
        }
      );
    }) as typeof fetch;

    const sourceEnv = {
      DATABASE_URL:
        "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
      GOOGLE_DRIVE_MCP_ACCESS_TOKEN: "gdrive-token",
      ARTIFACT_STORAGE_ROOT: path.join(repositoryOutputsRoot, "test-artifacts-runtime"),
      MCP_SERVERS_JSON: JSON.stringify([
        {
          id: "gdrive",
          transport: "http",
          baseUrl: "https://drivemcp.googleapis.com/mcp/v1",
          authTokenEnv: "GOOGLE_DRIVE_MCP_ACCESS_TOKEN",
          allowedToolNames: ["download_file_content"],
          enabled: true
        }
      ])
    } as NodeJS.ProcessEnv;
    const runtimeConfig = buildRuntimeConfig(getEnv(sourceEnv), sourceEnv);
    app = buildApp(
      {
        permissionEngine: new PermissionEngine([
          {
            appId: "app_gdrive_exporter",
            toolId: "mcp.gdrive.download_file_content",
            scope: "external_api.read",
            mode: "auto_allow"
          },
          {
            appId: "app_gdrive_exporter",
            toolId: "save_artifact",
            scope: "artifact.write",
            mode: "auto_allow"
          }
        ])
      },
      runtimeConfig
    );

    const response = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_skill",
        app_id: "app_gdrive_exporter",
        session_id: "sess_gdrive_exporter",
        skill_id: "google_drive_download_file",
        input: {
          fileId: "file-2"
        }
      }
    });

    assert.equal(response.statusCode, 200);
    assert.equal(response.json().status, "completed");
    assert.equal(
      response.json().execution_provenance?.[0]?.execution_path,
      "rest_fallback"
    );
    assert.equal(
      response.json().execution_provenance?.[0]?.fallback_reason,
      "mcp_permission_rejected"
    );
    assert.equal(response.json().execution_metadata?.used_fallback, true);
    assert.equal(response.json().execution_metadata?.fallback_count, 1);
    assert.deepEqual(response.json().execution_metadata?.tool_ids, [
      "mcp.gdrive.download_file_content",
      "save_artifact"
    ]);
    assert.match(response.json().logs_summary, /fallback path\(s\) used/i);

    const persistedResponse = await app.inject({
      method: "GET",
      url: `/v1/executions/${response.json().execution_id}?app_id=app_gdrive_exporter&session_id=sess_gdrive_exporter`
    });

    assert.equal(persistedResponse.statusCode, 200);
    assert.equal(
      persistedResponse.json().execution_provenance?.[0]?.execution_path,
      "rest_fallback"
    );
    assert.equal(
      persistedResponse.json().execution_metadata?.used_fallback,
      true
    );
    assert.equal(
      persistedResponse.json().execution_metadata?.fallback_count,
      1
    );

    const diagnosticsResponse = await app.inject({
      method: "GET",
      url: "/v1/executions/diagnostics/recent?app_id=app_gdrive_exporter&session_id=sess_gdrive_exporter&used_fallback=true&execution_path=rest_fallback&limit=10"
    });

    assert.equal(diagnosticsResponse.statusCode, 200);
    assert.equal(diagnosticsResponse.json().items.length, 1);
    assert.equal(diagnosticsResponse.json().summary.total_executions, 1);
    assert.equal(diagnosticsResponse.json().summary.fallback_executions, 1);
    assert.equal(
      diagnosticsResponse.json().summary.by_execution_path.rest_fallback,
      1
    );
    assert.equal(diagnosticsResponse.json().summary.by_provider.gdrive, 1);
    assert.equal(
      diagnosticsResponse.json().summary.by_tool[
        "mcp.gdrive.download_file_content"
      ],
      1
    );
    assert.equal(
      diagnosticsResponse.json().items[0]?.execution_id,
      response.json().execution_id
    );
    assert.equal(
      diagnosticsResponse.json().items[0]?.execution_metadata?.used_fallback,
      true
    );
  });

  it("confirms and completes a Gmail draft with app-scoped artifact attachments", async () => {
    let gmailCallArguments: Record<string, unknown> | undefined;
    globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      const payload = JSON.parse(String(init?.body ?? "{}")) as {
        method?: string;
        params?: { arguments?: Record<string, unknown> };
      };

      if (payload.method === "initialize") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 1,
            result: { protocolVersion: "2025-06-18" }
          }),
          {
            status: 200,
            headers: {
              "Content-Type": "application/json",
              "Mcp-Session-Id": url.includes("drivemcp")
                ? "gdrive-session-3"
                : "gmail-session-attachment"
            }
          }
        );
      }

      if (payload.method === "notifications/initialized") {
        return new Response("", {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (payload.method === "tools/list") {
        if (url.includes("drivemcp")) {
          return new Response(
            JSON.stringify({
              jsonrpc: "2.0",
              id: 2,
              result: {
                tools: [
                  {
                    name: "download_file_content",
                    title: "Download File Content"
                  }
                ]
              }
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" }
            }
          );
        }

        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 2,
            result: {
              tools: [
                {
                  name: "create_draft",
                  title: "Create Draft"
                }
              ]
            }
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" }
          }
        );
      }

      if (url.includes("drivemcp")) {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 3,
            result: {
              structuredContent: {
                file_id: "file-attachment-1",
                name: "Quarterly Plan.pdf",
                mime_type: "application/pdf",
                content: "cGRmLWNvbnRlbnQ=",
                content_encoding: "base64"
              }
            }
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" }
          }
        );
      }

      gmailCallArguments = payload.params?.arguments;
      return new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          id: 3,
          result: {
            structuredContent: {
              id: "draft-attachment-1",
              status: "draft_created",
              threadId: "thread-attachment-1"
            }
          }
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" }
        }
      );
    }) as typeof fetch;

    const sourceEnv = {
      DATABASE_URL:
        "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
      GOOGLE_DRIVE_MCP_ACCESS_TOKEN: "gdrive-token",
      GMAIL_MCP_ACCESS_TOKEN: "gmail-token",
      ARTIFACT_STORAGE_ROOT: path.join(repositoryOutputsRoot, "test-artifacts-runtime"),
      MCP_SERVERS_JSON: JSON.stringify([
        {
          id: "gdrive",
          transport: "http",
          baseUrl: "https://drivemcp.googleapis.com/mcp/v1",
          authTokenEnv: "GOOGLE_DRIVE_MCP_ACCESS_TOKEN",
          allowedToolNames: ["download_file_content"],
          enabled: true
        },
        {
          id: "gmail",
          transport: "http",
          baseUrl: "https://gmailmcp.googleapis.com/mcp/v1",
          authTokenEnv: "GMAIL_MCP_ACCESS_TOKEN",
          allowedToolNames: ["create_draft"],
          enabled: true
        }
      ])
    } as NodeJS.ProcessEnv;
    const runtimeConfig = buildRuntimeConfig(getEnv(sourceEnv), sourceEnv);
    app = buildApp(
      {
        permissionEngine: new PermissionEngine([
          {
            appId: "app_gmail_attachment_writer",
            toolId: "mcp.gdrive.download_file_content",
            scope: "external_api.read",
            mode: "auto_allow"
          },
          {
            appId: "app_gmail_attachment_writer",
            toolId: "save_artifact",
            scope: "artifact.write",
            mode: "auto_allow"
          },
          {
            appId: "app_gmail_attachment_writer",
            toolId: "mcp.gmail.create_draft_with_attachments",
            scope: "artifact.read",
            mode: "auto_allow"
          },
          {
            appId: "app_gmail_attachment_writer",
            toolId: "mcp.gmail.create_draft_with_attachments",
            scope: "external_api.write",
            mode: "require_confirmation"
          }
        ])
      },
      runtimeConfig
    );

    await app.inject({
      method: "POST",
      url: "/v1/tools/discover/mcp",
      payload: { provider_id: "gdrive" }
    });
    await app.inject({
      method: "POST",
      url: "/v1/tools/discover/mcp",
      payload: { provider_id: "gmail" }
    });

    const exportResponse = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_skill",
        app_id: "app_gmail_attachment_writer",
        session_id: "sess_gmail_attachment_writer",
        skill_id: "google_drive_download_file",
        input: {
          fileId: "file-attachment-1"
        }
      }
    });
    assert.equal(exportResponse.statusCode, 200);
    const artifactId = exportResponse.json().result.artifact_id;

    const draftResponse = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_skill",
        app_id: "app_gmail_attachment_writer",
        session_id: "sess_gmail_attachment_writer",
        skill_id: "gmail_create_draft_with_attachments",
        input: {
          to: "alice@example.com",
          subject: "Hello",
          body: "Draft content",
          artifactIds: [artifactId]
        }
      }
    });
    assert.equal(draftResponse.statusCode, 202);
    const executionId = draftResponse.json().execution_id;

    const confirmResponse = await app.inject({
      method: "POST",
      url: `/v1/executions/${executionId}/confirm?app_id=app_gmail_attachment_writer&session_id=sess_gmail_attachment_writer`,
      payload: {
        confirmation_id: draftResponse.json().result.confirmation_id
      }
    });

    assert.equal(confirmResponse.statusCode, 200);
    assert.equal(confirmResponse.json().status, "completed");
    assert.deepEqual(gmailCallArguments, {
      to: ["alice@example.com"],
      subject: "Hello",
      body: "Draft content",
      attachments: [
        {
          filename: "Quarterly Plan.pdf",
          mimeType: "application/pdf",
          content: "cGRmLWNvbnRlbnQ="
        }
      ]
    });
  });

  it("creates and then sends a Gmail draft that carries app-scoped artifact attachments", async () => {
    let gmailDraftCallArguments: Record<string, unknown> | undefined;
    let gmailSendDraftArguments: Record<string, unknown> | undefined;

    globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
      const payload = JSON.parse(String(init?.body ?? "{}")) as {
        method?: string;
        params?: { name?: string; arguments?: Record<string, unknown> };
      };
      const url = String(input);

      if (payload.method === "initialize") {
        const sessionId = url.includes("drivemcp")
          ? "gdrive-session-attachment-send"
          : "gmail-session-attachment-send";
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 1,
            result: { protocolVersion: "2025-06-18" }
          }),
          {
            status: 200,
            headers: {
              "Content-Type": "application/json",
              "Mcp-Session-Id": sessionId
            }
          }
        );
      }

      if (payload.method === "notifications/initialized") {
        return new Response("", {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (payload.method === "tools/list") {
        if (url.includes("drivemcp")) {
          return new Response(
            JSON.stringify({
              jsonrpc: "2.0",
              id: 2,
              result: {
                tools: [
                  {
                    name: "download_file_content",
                    title: "Download File Content"
                  }
                ]
              }
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" }
            }
          );
        }

        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 2,
            result: {
              tools: [
                {
                  name: "create_draft",
                  title: "Create Draft"
                },
                {
                  name: "send_draft",
                  title: "Send Draft"
                }
              ]
            }
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" }
          }
        );
      }

      if (url.includes("drivemcp")) {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 3,
            result: {
              structuredContent: {
                file_id: "file-attachment-2",
                name: "Execution Summary.pdf",
                mime_type: "application/pdf",
                content: "cGRmLWF0dGFjaG1lbnQ=",
                content_encoding: "base64"
              }
            }
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" }
          }
        );
      }

      if (payload.params?.name === "create_draft") {
        gmailDraftCallArguments = payload.params.arguments;
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 3,
            result: {
              structuredContent: {
                id: "draft-attachment-send-1",
                status: "draft_created",
                threadId: "thread-attachment-send-1"
              }
            }
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" }
          }
        );
      }

      gmailSendDraftArguments = payload.params?.arguments;
      return new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          id: 4,
          result: {
            structuredContent: {
              id: "sent-message-attachment-1",
              status: "sent",
              threadId: "thread-attachment-send-1"
            }
          }
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" }
        }
      );
    }) as typeof fetch;

    const sourceEnv = {
      DATABASE_URL:
        "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
      GOOGLE_DRIVE_MCP_ACCESS_TOKEN: "gdrive-token",
      GMAIL_MCP_ACCESS_TOKEN: "gmail-token",
      ARTIFACT_STORAGE_ROOT: path.join(repositoryOutputsRoot, "test-artifacts-runtime"),
      MCP_SERVERS_JSON: JSON.stringify([
        {
          id: "gdrive",
          transport: "http",
          baseUrl: "https://drivemcp.googleapis.com/mcp/v1",
          authTokenEnv: "GOOGLE_DRIVE_MCP_ACCESS_TOKEN",
          allowedToolNames: ["download_file_content"],
          enabled: true
        },
        {
          id: "gmail",
          transport: "http",
          baseUrl: "https://gmailmcp.googleapis.com/mcp/v1",
          authTokenEnv: "GMAIL_MCP_ACCESS_TOKEN",
          allowedToolNames: ["create_draft", "send_draft"],
          enabled: true
        }
      ])
    } as NodeJS.ProcessEnv;
    const runtimeConfig = buildRuntimeConfig(getEnv(sourceEnv), sourceEnv);
    app = buildApp(
      {
        permissionEngine: new PermissionEngine([
          {
            appId: "app_gmail_attachment_sender",
            toolId: "mcp.gdrive.download_file_content",
            scope: "external_api.read",
            mode: "auto_allow"
          },
          {
            appId: "app_gmail_attachment_sender",
            toolId: "save_artifact",
            scope: "artifact.write",
            mode: "auto_allow"
          },
          {
            appId: "app_gmail_attachment_sender",
            toolId: "mcp.gmail.create_draft_with_attachments",
            scope: "artifact.read",
            mode: "auto_allow"
          },
          {
            appId: "app_gmail_attachment_sender",
            toolId: "mcp.gmail.create_draft_with_attachments",
            scope: "external_api.write",
            mode: "require_confirmation"
          },
          {
            appId: "app_gmail_attachment_sender",
            toolId: "mcp.gmail.send_draft",
            scope: "external_api.write",
            mode: "require_confirmation"
          }
        ])
      },
      runtimeConfig
    );

    await app.inject({
      method: "POST",
      url: "/v1/tools/discover/mcp",
      payload: { provider_id: "gdrive" }
    });
    await app.inject({
      method: "POST",
      url: "/v1/tools/discover/mcp",
      payload: { provider_id: "gmail" }
    });

    const exportResponse = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_skill",
        app_id: "app_gmail_attachment_sender",
        session_id: "sess_gmail_attachment_sender",
        skill_id: "google_drive_download_file",
        input: {
          fileId: "file-attachment-2"
        }
      }
    });
    assert.equal(exportResponse.statusCode, 200);
    const artifactId = exportResponse.json().result.artifact_id;

    const createDraftResponse = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_skill",
        app_id: "app_gmail_attachment_sender",
        session_id: "sess_gmail_attachment_sender",
        skill_id: "gmail_create_draft_with_attachments",
        input: {
          to: "alice@example.com",
          subject: "Attachment Flow",
          body: "Please review the attached summary.",
          artifactIds: [artifactId]
        }
      }
    });
    assert.equal(createDraftResponse.statusCode, 202);

    const createDraftExecutionId = createDraftResponse.json().execution_id;
    const confirmDraftResponse = await app.inject({
      method: "POST",
      url: `/v1/executions/${createDraftExecutionId}/confirm?app_id=app_gmail_attachment_sender&session_id=sess_gmail_attachment_sender`,
      payload: {
        confirmation_id: createDraftResponse.json().result.confirmation_id
      }
    });

    assert.equal(confirmDraftResponse.statusCode, 200);
    assert.equal(confirmDraftResponse.json().status, "completed");
    assert.deepEqual(gmailDraftCallArguments, {
      to: ["alice@example.com"],
      subject: "Attachment Flow",
      body: "Please review the attached summary.",
      attachments: [
        {
          filename: "Execution Summary.pdf",
          mimeType: "application/pdf",
          content: "cGRmLWF0dGFjaG1lbnQ="
        }
      ]
    });

    const draftId = confirmDraftResponse.json().result.id;
    const sendDraftResponse = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_skill",
        app_id: "app_gmail_attachment_sender",
        session_id: "sess_gmail_attachment_sender",
        skill_id: "gmail_send_draft",
        input: {
          draftId
        }
      }
    });
    assert.equal(sendDraftResponse.statusCode, 202);
    assert.equal(sendDraftResponse.json().status, "pending_confirmation");

    const sendDraftExecutionId = sendDraftResponse.json().execution_id;
    const confirmSendDraftResponse = await app.inject({
      method: "POST",
      url: `/v1/executions/${sendDraftExecutionId}/confirm?app_id=app_gmail_attachment_sender&session_id=sess_gmail_attachment_sender`,
      payload: {
        confirmation_id: sendDraftResponse.json().result.confirmation_id
      }
    });

    assert.equal(confirmSendDraftResponse.statusCode, 200);
    assert.equal(confirmSendDraftResponse.json().status, "completed");
    assert.deepEqual(gmailSendDraftArguments, {
      draftId: "draft-attachment-send-1"
    });
    assert.deepEqual(confirmSendDraftResponse.json().result, {
      id: "sent-message-attachment-1",
      status: "sent",
      threadId: "thread-attachment-send-1"
    });
  });

  it("confirms and completes Gmail draft creation through the Gmail MCP provider", async () => {
    globalThis.fetch = (async (_input: string | URL | Request, init?: RequestInit) => {
      const payload = JSON.parse(String(init?.body ?? "{}")) as { method?: string };

      if (payload.method === "initialize") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 1,
            result: { protocolVersion: "2025-06-18" }
          }),
          {
            status: 200,
            headers: {
              "Content-Type": "application/json",
              "Mcp-Session-Id": "gmail-session-2"
            }
          }
        );
      }

      if (payload.method === "notifications/initialized") {
        return new Response("", {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (payload.method === "tools/list") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 2,
            result: {
              tools: [
                {
                  name: "create_draft",
                  title: "Create Draft"
                }
              ]
            }
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" }
          }
        );
      }

      return new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          id: 3,
          result: {
            structuredContent: {
              id: "draft-1",
              status: "draft_created",
              threadId: "thread-1"
            }
          }
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" }
        }
      );
    }) as typeof fetch;

    const sourceEnv = {
      DATABASE_URL:
        "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
      GMAIL_MCP_ACCESS_TOKEN: "gmail-token",
      MCP_SERVERS_JSON: JSON.stringify([
        {
          id: "gmail",
          transport: "http",
          baseUrl: "https://gmailmcp.googleapis.com/mcp/v1",
          authTokenEnv: "GMAIL_MCP_ACCESS_TOKEN",
          allowedToolNames: ["search_messages", "create_draft"],
          enabled: true
        }
      ])
    } as NodeJS.ProcessEnv;
    const runtimeConfig = buildRuntimeConfig(getEnv(sourceEnv), sourceEnv);
    app = buildApp(
      {
        permissionEngine: new PermissionEngine([
          {
            appId: "app_gmail_writer",
            toolId: "mcp.gmail.create_draft",
            scope: "external_api.write",
            mode: "require_confirmation"
          }
        ])
      },
      runtimeConfig
    );

    const discoverResponse = await app.inject({
      method: "POST",
      url: "/v1/tools/discover/mcp",
      payload: {
        provider_id: "gmail"
      }
    });
    assert.equal(discoverResponse.statusCode, 200);

    const createResponse = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_skill",
        app_id: "app_gmail_writer",
        session_id: "sess_gmail_writer",
        skill_id: "gmail_create_draft",
        input: {
          to: "alice@example.com",
          subject: "Hello",
          body: "Draft content"
        }
      }
    });

    assert.equal(createResponse.statusCode, 202);
    assert.equal(createResponse.json().status, "pending_confirmation");
    const executionId = createResponse.json().execution_id;

    const confirmResponse = await app.inject({
      method: "POST",
      url: `/v1/executions/${executionId}/confirm?app_id=app_gmail_writer&session_id=sess_gmail_writer`,
      payload: {
        confirmation_id: createResponse.json().result.confirmation_id
      }
    });

    assert.equal(confirmResponse.statusCode, 200);
    assert.equal(confirmResponse.json().status, "completed");
    assert.deepEqual(confirmResponse.json().result, {
      id: "draft-1",
      status: "draft_created",
      threadId: "thread-1"
    });
  });

  it("confirms and completes Gmail draft send through the Gmail MCP provider", async () => {
    globalThis.fetch = (async (_input: string | URL | Request, init?: RequestInit) => {
      const payload = JSON.parse(String(init?.body ?? "{}")) as { method?: string };

      if (payload.method === "initialize") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 1,
            result: { protocolVersion: "2025-06-18" }
          }),
          {
            status: 200,
            headers: {
              "Content-Type": "application/json",
              "Mcp-Session-Id": "gmail-session-3"
            }
          }
        );
      }

      if (payload.method === "notifications/initialized") {
        return new Response("", {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (payload.method === "tools/list") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 2,
            result: {
              tools: [
                {
                  name: "send_draft",
                  title: "Send Draft"
                }
              ]
            }
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" }
          }
        );
      }

      return new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          id: 3,
          result: {
            structuredContent: {
              id: "sent-message-1",
              status: "sent",
              threadId: "thread-1"
            }
          }
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" }
        }
      );
    }) as typeof fetch;

    const sourceEnv = {
      DATABASE_URL:
        "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
      GMAIL_MCP_ACCESS_TOKEN: "gmail-token",
      MCP_SERVERS_JSON: JSON.stringify([
        {
          id: "gmail",
          transport: "http",
          baseUrl: "https://gmailmcp.googleapis.com/mcp/v1",
          authTokenEnv: "GMAIL_MCP_ACCESS_TOKEN",
          allowedToolNames: ["search_messages", "create_draft", "send_draft"],
          enabled: true
        }
      ])
    } as NodeJS.ProcessEnv;
    const runtimeConfig = buildRuntimeConfig(getEnv(sourceEnv), sourceEnv);
    app = buildApp(
      {
        permissionEngine: new PermissionEngine([
          {
            appId: "app_gmail_sender",
            toolId: "mcp.gmail.send_draft",
            scope: "external_api.write",
            mode: "require_confirmation"
          }
        ])
      },
      runtimeConfig
    );

    const discoverResponse = await app.inject({
      method: "POST",
      url: "/v1/tools/discover/mcp",
      payload: {
        provider_id: "gmail"
      }
    });
    assert.equal(discoverResponse.statusCode, 200);

    const createResponse = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_skill",
        app_id: "app_gmail_sender",
        session_id: "sess_gmail_sender",
        skill_id: "gmail_send_draft",
        input: {
          draftId: "draft-1"
        }
      }
    });

    assert.equal(createResponse.statusCode, 202);
    assert.equal(createResponse.json().status, "pending_confirmation");
    const executionId = createResponse.json().execution_id;

    const confirmResponse = await app.inject({
      method: "POST",
      url: `/v1/executions/${executionId}/confirm?app_id=app_gmail_sender&session_id=sess_gmail_sender`,
      payload: {
        confirmation_id: createResponse.json().result.confirmation_id
      }
    });

    assert.equal(confirmResponse.statusCode, 200);
    assert.equal(confirmResponse.json().status, "completed");
    assert.deepEqual(confirmResponse.json().result, {
      id: "sent-message-1",
      status: "sent",
      threadId: "thread-1"
    });
  });

  it("confirms and completes Gmail direct send through the Gmail MCP provider", async () => {
    let gmailSendMessageArguments: Record<string, unknown> | undefined;
    globalThis.fetch = (async (_input: string | URL | Request, init?: RequestInit) => {
      const payload = JSON.parse(String(init?.body ?? "{}")) as {
        method?: string;
        params?: { arguments?: Record<string, unknown> };
      };

      if (payload.method === "initialize") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 1,
            result: { protocolVersion: "2025-06-18" }
          }),
          {
            status: 200,
            headers: {
              "Content-Type": "application/json",
              "Mcp-Session-Id": "gmail-session-4"
            }
          }
        );
      }

      if (payload.method === "notifications/initialized") {
        return new Response("", {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (payload.method === "tools/list") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 2,
            result: {
              tools: [
                {
                  name: "send_message",
                  title: "Send Message"
                }
              ]
            }
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" }
          }
        );
      }

      gmailSendMessageArguments = payload.params?.arguments;
      return new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          id: 3,
          result: {
            structuredContent: {
              id: "sent-message-2",
              status: "sent",
              threadId: "thread-2"
            }
          }
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" }
        }
      );
    }) as typeof fetch;

    const sourceEnv = {
      DATABASE_URL:
        "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
      GMAIL_MCP_ACCESS_TOKEN: "gmail-token",
      MCP_SERVERS_JSON: JSON.stringify([
        {
          id: "gmail",
          transport: "http",
          baseUrl: "https://gmailmcp.googleapis.com/mcp/v1",
          authTokenEnv: "GMAIL_MCP_ACCESS_TOKEN",
          allowedToolNames: ["search_messages", "create_draft", "send_draft", "send_message"],
          enabled: true
        }
      ])
    } as NodeJS.ProcessEnv;
    const runtimeConfig = buildRuntimeConfig(getEnv(sourceEnv), sourceEnv);
    app = buildApp(
      {
        permissionEngine: new PermissionEngine([
          {
            appId: "app_gmail_direct_sender",
            toolId: "mcp.gmail.send_message",
            scope: "external_api.write",
            mode: "require_confirmation"
          }
        ])
      },
      runtimeConfig
    );

    const discoverResponse = await app.inject({
      method: "POST",
      url: "/v1/tools/discover/mcp",
      payload: {
        provider_id: "gmail"
      }
    });
    assert.equal(discoverResponse.statusCode, 200);

    const createResponse = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_skill",
        app_id: "app_gmail_direct_sender",
        session_id: "sess_gmail_direct_sender",
        skill_id: "gmail_send_message",
        input: {
          to: "alice@example.com",
          subject: "Hello",
          body: "Direct send content"
        }
      }
    });

    assert.equal(createResponse.statusCode, 202);
    assert.equal(createResponse.json().status, "pending_confirmation");
    const executionId = createResponse.json().execution_id;

    const confirmResponse = await app.inject({
      method: "POST",
      url: `/v1/executions/${executionId}/confirm?app_id=app_gmail_direct_sender&session_id=sess_gmail_direct_sender`,
      payload: {
        confirmation_id: createResponse.json().result.confirmation_id
      }
    });

    assert.equal(confirmResponse.statusCode, 200);
    assert.equal(confirmResponse.json().status, "completed");
    assert.deepEqual(gmailSendMessageArguments, {
      to: ["alice@example.com"],
      subject: "Hello",
      body: "Direct send content"
    });
    assert.deepEqual(confirmResponse.json().result, {
      id: "sent-message-2",
      status: "sent",
      threadId: "thread-2"
    });
  });

  it("returns validation error for unknown skill", async () => {
    app = buildApp();

    const response = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_skill",
        app_id: "app_001",
        session_id: "sess_001",
        skill_id: "unknown_skill",
        input: {
          prompt: "Explain RAG simply",
          duration: 30
        }
      }
    });

    assert.equal(response.statusCode, 404);
    assert.equal(response.json().error.code, "SKILL_NOT_FOUND");
  });
});
