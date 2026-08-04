import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { AppError } from "../../src/core/errors/app-error.js";
import { PermissionEngine } from "../../src/core/permissions/permission-engine.js";
import { ToolEngine } from "../../src/core/tools/tool-engine.js";
import { ToolRegistry } from "../../src/core/tools/tool-registry.js";
import { buildApp } from "../../src/app.js";
import type { FastifyInstance } from "fastify";
import { getEnv } from "../../src/config/env.js";
import { buildRuntimeConfig } from "../../src/config/runtime-config.js";

const originalFetch = globalThis.fetch;

describe("permission block placeholder", () => {
  it("returns require-confirmation before tool execution", async () => {
    const registry = new ToolRegistry();
    const permissions = new PermissionEngine([
      {
        appId: "app_001",
        toolId: "mock_video_generation_tool",
        scope: "external_api.write",
        mode: "require_confirmation"
      }
    ]);
    const engine = new ToolEngine(undefined, permissions);

    await assert.rejects(
      () =>
        engine.execute(
          registry.get("mock_video_generation_tool"),
          {
            prompt: "hello",
            duration: 30
          },
          { appId: "app_001" }
        ),
      (error: unknown) =>
        error instanceof AppError &&
        error.code === "PERMISSION_CONFIRMATION_REQUIRED"
    );
  });

  it("blocks restricted conditions that do not pass", async () => {
    const registry = new ToolRegistry();
    const permissions = new PermissionEngine([
      {
        appId: "app_001",
        toolId: "mock_video_generation_tool",
        scope: "external_api.write",
        mode: "restricted",
        conditions: { maxDuration: 10 }
      }
    ]);
    const engine = new ToolEngine(undefined, permissions);

    await assert.rejects(
      () =>
        engine.execute(
          registry.get("mock_video_generation_tool"),
          {
            prompt: "hello",
            duration: 30
          },
          { appId: "app_001" }
        ),
      (error: unknown) =>
        error instanceof AppError && error.code === "PERMISSION_BLOCKED"
    );
  });

  it("returns pending confirmation from POST /v1/executions", async () => {
    const app: FastifyInstance = buildApp({
      permissionEngine: new PermissionEngine([
        {
          appId: "app_001",
          toolId: "mock_video_generation_tool",
          scope: "external_api.write",
          mode: "require_confirmation"
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

    assert.equal(response.statusCode, 202);
    assert.equal(response.json().status, "pending_confirmation");

    await app.close();
  });

  it("confirms a pending execution and completes it with the same execution id", async () => {
    const app: FastifyInstance = buildApp({
      permissionEngine: new PermissionEngine([
        {
          appId: "app_001",
          toolId: "mock_video_generation_tool",
          scope: "external_api.write",
          mode: "require_confirmation"
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
    const confirmResponse = await app.inject({
      method: "POST",
      url: `/v1/executions/${executionId}/confirm?app_id=app_001&session_id=sess_001`,
      payload: {
        confirmation_id: createResponse.json().result.confirmation_id
      }
    });

    assert.equal(confirmResponse.statusCode, 200);
    assert.equal(confirmResponse.json().status, "completed");
    assert.equal(confirmResponse.json().execution_id, executionId);

    const lookupResponse = await app.inject({
      method: "GET",
      url: `/v1/executions/${executionId}?app_id=app_001&session_id=sess_001`
    });

    assert.equal(lookupResponse.statusCode, 200);
    assert.equal(lookupResponse.json().status, "completed");

    await app.close();
  });

  it("returns pending confirmation before executing a mutation skill", async () => {
    const app: FastifyInstance = buildApp({
      permissionEngine: new PermissionEngine([
        {
          appId: "app_writer",
          toolId: "write_file",
          scope: "filesystem.write",
          mode: "require_confirmation"
        }
      ])
    });

    const response = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_skill",
        app_id: "app_writer",
        session_id: "sess_writer",
        skill_id: "content_replace",
        input: {
          path: "D:/GitHub/Codex-RAGenius-System/docs/test.md",
          content: "updated"
        }
      }
    });

    assert.equal(response.statusCode, 202);
    assert.equal(response.json().status, "pending_confirmation");

    await app.close();
  });

  it("returns pending confirmation before executing an MCP write skill", async () => {
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
    const app: FastifyInstance = buildApp(
      {
        permissionEngine: new PermissionEngine([
          {
            appId: "app_mcp_writer",
            toolId: "mcp.cms.create_page",
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
        provider_id: "cms"
      }
    });
    assert.equal(discoverResponse.statusCode, 200);

    const response = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_skill",
        app_id: "app_mcp_writer",
        session_id: "sess_mcp_writer",
        skill_id: "mcp_page_create",
        input: {
          title: "Release Notes"
        }
      }
    });

    assert.equal(response.statusCode, 202);
    assert.equal(response.json().status, "pending_confirmation");

    await app.close();
  });

  it("fails cleanly when the Gmail MCP provider is configured without its shared token", async () => {
    const runtimeConfig = buildRuntimeConfig(
      getEnv({
        DATABASE_URL:
          "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
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
      })
    );
    const app: FastifyInstance = buildApp({}, runtimeConfig);

    const response = await app.inject({
      method: "POST",
      url: "/v1/tools/discover/mcp",
      payload: {
        provider_id: "gmail"
      }
    });

    assert.equal(response.statusCode, 502);
    assert.equal(response.json().error.code, "MCP_PROVIDER_AUTH_FAILED");

    await app.close();
  });

  it("fails cleanly when the Google Docs MCP provider is configured without its shared token", async () => {
    const runtimeConfig = buildRuntimeConfig(
      getEnv({
        DATABASE_URL:
          "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
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
      })
    );
    const app: FastifyInstance = buildApp({}, runtimeConfig);

    const response = await app.inject({
      method: "POST",
      url: "/v1/tools/discover/mcp",
      payload: {
        provider_id: "gdocs"
      }
    });

    assert.equal(response.statusCode, 502);
    assert.equal(response.json().error.code, "MCP_PROVIDER_AUTH_FAILED");

    await app.close();
  });

  it("fails cleanly when the Google Drive MCP provider is configured without its shared token", async () => {
    const runtimeConfig = buildRuntimeConfig(
      getEnv({
        DATABASE_URL:
          "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
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
      })
    );
    const app: FastifyInstance = buildApp({}, runtimeConfig);

    const response = await app.inject({
      method: "POST",
      url: "/v1/tools/discover/mcp",
      payload: {
        provider_id: "gdrive"
      }
    });

    assert.equal(response.statusCode, 502);
    assert.equal(response.json().error.code, "MCP_PROVIDER_AUTH_FAILED");

    await app.close();
  });

  it("returns pending confirmation before creating a Gmail draft", async () => {
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
    const app: FastifyInstance = buildApp(
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

      if (payload.method === "tools/list") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 2,
            result: {
              tools: [{ name: "create_draft", title: "Create Draft" }]
            }
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }

      return new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          id: 3,
          result: {
            structuredContent: {
              id: "draft-1",
              status: "draft_created"
            }
          }
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    const discoverResponse = await app.inject({
      method: "POST",
      url: "/v1/tools/discover/mcp",
      payload: {
        provider_id: "gmail"
      }
    });
    assert.equal(discoverResponse.statusCode, 200);

    const response = await app.inject({
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

    assert.equal(response.statusCode, 202);
    assert.equal(response.json().status, "pending_confirmation");

    await app.close();
    globalThis.fetch = originalFetch;
  });

  it("returns pending confirmation before creating a Gmail draft with attachments", async () => {
    const sourceEnv = {
      DATABASE_URL:
        "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
      GMAIL_MCP_ACCESS_TOKEN: "gmail-token",
      ARTIFACT_STORAGE_ROOT:
        "D:/GitHub/Codex-RAGenius-System/outputs/test-artifacts-runtime",
      MCP_SERVERS_JSON: JSON.stringify([
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
    const app: FastifyInstance = buildApp(
      {
        permissionEngine: new PermissionEngine([
          {
            appId: "app_gmail_attachment_writer",
            toolId: "mcp.gmail.create_draft_with_attachments",
            scope: "external_api.write",
            mode: "require_confirmation"
          },
          {
            appId: "app_gmail_attachment_writer",
            toolId: "mcp.gmail.create_draft_with_attachments",
            scope: "artifact.read",
            mode: "auto_allow"
          }
        ])
      },
      runtimeConfig
    );

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

      if (payload.method === "tools/list") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 2,
            result: {
              tools: [{ name: "create_draft", title: "Create Draft" }]
            }
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }

      return new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          id: 3,
          result: {
            structuredContent: {
              id: "draft-attachment-1",
              status: "draft_created"
            }
          }
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    const discoverResponse = await app.inject({
      method: "POST",
      url: "/v1/tools/discover/mcp",
      payload: {
        provider_id: "gmail"
      }
    });
    assert.equal(discoverResponse.statusCode, 200);

    const response = await app.inject({
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
          artifactIds: ["artifact_1"]
        }
      }
    });

    assert.equal(response.statusCode, 202);
    assert.equal(response.json().status, "pending_confirmation");

    await app.close();
    globalThis.fetch = originalFetch;
  });

  it("returns pending confirmation before sending a Gmail draft", async () => {
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
    const app: FastifyInstance = buildApp(
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

      if (payload.method === "tools/list") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 2,
            result: {
              tools: [{ name: "send_draft", title: "Send Draft" }]
            }
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }

      return new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          id: 3,
          result: {
            structuredContent: {
              id: "sent-message-1",
              status: "sent"
            }
          }
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    const discoverResponse = await app.inject({
      method: "POST",
      url: "/v1/tools/discover/mcp",
      payload: {
        provider_id: "gmail"
      }
    });
    assert.equal(discoverResponse.statusCode, 200);

    const response = await app.inject({
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

    assert.equal(response.statusCode, 202);
    assert.equal(response.json().status, "pending_confirmation");

    await app.close();
    globalThis.fetch = originalFetch;
  });

  it("returns pending confirmation before sending a Gmail message directly", async () => {
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
    const app: FastifyInstance = buildApp(
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

      if (payload.method === "tools/list") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 2,
            result: {
              tools: [{ name: "send_message", title: "Send Message" }]
            }
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }

      return new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          id: 3,
          result: {
            structuredContent: {
              id: "sent-message-2",
              status: "sent"
            }
          }
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    const discoverResponse = await app.inject({
      method: "POST",
      url: "/v1/tools/discover/mcp",
      payload: {
        provider_id: "gmail"
      }
    });
    assert.equal(discoverResponse.statusCode, 200);

    const response = await app.inject({
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

    assert.equal(response.statusCode, 202);
    assert.equal(response.json().status, "pending_confirmation");

    await app.close();
    globalThis.fetch = originalFetch;
  });
});
