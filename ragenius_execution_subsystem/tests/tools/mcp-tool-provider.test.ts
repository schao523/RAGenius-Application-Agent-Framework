import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";

import { buildDefaultRuntimePolicyConfig } from "../../src/config/policy-config.js";
import { AppError } from "../../src/core/errors/app-error.js";
import { McpToolProvider } from "../../src/core/tools/providers/mcp-tool-provider.js";

const originalFetch = globalThis.fetch;

describe("mcp tool provider", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("discovers only allowlisted Gmail tools and maps them into registry definitions", async () => {
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
        return new Response("", { status: 200, headers: { "Content-Type": "application/json" } });
      }

      return new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          id: 2,
          result: {
            tools: [
              {
                name: "search_messages",
                title: "Search Messages",
                inputSchema: {
                  type: "object",
                  properties: {
                    query: { type: "string" }
                  },
                  required: ["query"]
                }
              },
              { name: "send_message", title: "Send Message" }
            ]
          }
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    const provider = new McpToolProvider({
      servers: [
        {
          id: "gmail",
          transport: "http",
          baseUrl: "https://gmailmcp.googleapis.com/mcp/v1",
          authTokenEnv: "GMAIL_MCP_ACCESS_TOKEN",
          authToken: "gmail-token",
          allowedToolNames: ["search_messages"],
          enabled: true
        }
      ]
    });

    const discovered = await provider.discover("gmail");

    assert.equal(discovered.length, 1);
    assert.equal(discovered[0]?.id, "mcp.gmail.search_messages");
    assert.deepEqual(discovered[0]?.permissionScopes, ["external_api.read"]);
    assert.deepEqual(discovered[0]?.metadata?.remoteInputSchema, {
      type: "object",
      properties: {
        query: { type: "string" }
      },
      required: ["query"]
    });
  });

  it("invokes an allowlisted discovered Gmail tool through the provider", async () => {
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
        return new Response("", { status: 200, headers: { "Content-Type": "application/json" } });
      }

      if (payload.method === "tools/list") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 2,
            result: {
              tools: [{ name: "search_messages", title: "Search Messages" }]
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
              results: [{ id: "msg-1", subject: "Hello" }]
            }
          }
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    const provider = new McpToolProvider({
      servers: [
        {
          id: "gmail",
          transport: "http",
          baseUrl: "https://gmailmcp.googleapis.com/mcp/v1",
          authTokenEnv: "GMAIL_MCP_ACCESS_TOKEN",
          authToken: "gmail-token",
          allowedToolNames: ["search_messages"],
          enabled: true
        }
      ]
    });

    const [tool] = await provider.discover("gmail");
    assert.ok(tool);
    const result = await provider.execute(
      tool,
      { query: "homepage" },
      { appId: "app_001" }
    );

    assert.deepEqual(result, {
      results: [{ id: "msg-1", subject: "Hello" }]
    });
  });

  it("discovers and executes the Google Docs search tool as a read-only MCP path", async () => {
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
        return new Response("", { status: 200, headers: { "Content-Type": "application/json" } });
      }

      if (payload.method === "tools/list") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 2,
            result: {
              tools: [{ name: "search_documents", title: "Search Documents" }]
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
              results: [{ id: "doc-1", title: "Product Strategy" }]
            }
          }
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    const provider = new McpToolProvider({
      servers: [
        {
          id: "gdocs",
          transport: "http",
          baseUrl: "https://google-docs-mcp.example.com/mcp/v1",
          authTokenEnv: "GOOGLE_DOCS_MCP_ACCESS_TOKEN",
          authToken: "gdocs-token",
          allowedToolNames: ["search_documents"],
          enabled: true
        }
      ]
    });

    const [tool] = await provider.discover("gdocs");
    assert.ok(tool);
    assert.equal(tool.id, "mcp.gdocs.search_documents");
    assert.equal(tool.sideEffecting, false);
    assert.deepEqual(tool.permissionScopes, ["external_api.read"]);

    const result = await provider.execute(
      tool,
      { query: "strategy" },
      { appId: "app_001" }
    );

    assert.deepEqual(result, {
      results: [{ id: "doc-1", title: "Product Strategy" }]
    });
  });

  it("discovers and executes the Google Drive search tool as a read-only MCP path", async () => {
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
        return new Response("", { status: 200, headers: { "Content-Type": "application/json" } });
      }

      if (payload.method === "tools/list") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 2,
            result: {
              tools: [{ name: "search_files", title: "Search Files" }]
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
              results: [{ id: "file-1", name: "Quarterly Plan.pdf" }]
            }
          }
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    const provider = new McpToolProvider({
      servers: [
        {
          id: "gdrive",
          transport: "http",
          baseUrl: "https://google-drive-mcp.example.com/mcp/v1",
          authTokenEnv: "GOOGLE_DRIVE_MCP_ACCESS_TOKEN",
          authToken: "gdrive-token",
          allowedToolNames: ["search_files"],
          enabled: true
        }
      ]
    });

    const [tool] = await provider.discover("gdrive");
    assert.ok(tool);
    assert.equal(tool.id, "mcp.gdrive.search_files");
    assert.equal(tool.sideEffecting, false);
    assert.deepEqual(tool.permissionScopes, ["external_api.read"]);

    const result = await provider.execute(
      tool,
      { query: "quarterly" },
      { appId: "app_001" }
    );

    assert.deepEqual(result, {
      results: [{ id: "file-1", name: "Quarterly Plan.pdf" }]
    });
  });

  it("discovers and executes the Google Drive download tool as a read-only MCP path", async () => {
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
        return new Response("", { status: 200, headers: { "Content-Type": "application/json" } });
      }

      if (payload.method === "tools/list") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 2,
            result: {
              tools: [{ name: "download_file_content", title: "Download File Content" }]
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
              file_id: "file-1",
              name: "Quarterly Plan.pdf",
              mime_type: "application/pdf",
              content: "cGRmLWNvbnRlbnQ=",
              content_encoding: "base64"
            }
          }
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    const provider = new McpToolProvider({
      servers: [
        {
          id: "gdrive",
          transport: "http",
          baseUrl: "https://drivemcp.googleapis.com/mcp/v1",
          authTokenEnv: "GOOGLE_DRIVE_MCP_ACCESS_TOKEN",
          authToken: "gdrive-token",
          allowedToolNames: ["download_file_content"],
          enabled: true
        }
      ]
    });

    const [tool] = await provider.discover("gdrive");
    assert.ok(tool);
    assert.equal(tool.id, "mcp.gdrive.download_file_content");
    assert.equal(tool.sideEffecting, false);
    assert.deepEqual(tool.permissionScopes, ["external_api.read"]);

    const result = await provider.execute(
      tool,
      { fileId: "file-1" },
      { appId: "app_001" }
    );

    assert.deepEqual(result, {
      file_id: "file-1",
      name: "Quarterly Plan.pdf",
      mime_type: "application/pdf",
      content: "cGRmLWNvbnRlbnQ=",
      content_encoding: "base64"
    });
  });

  it("falls back to Drive REST download when the managed Drive MCP tool rejects a readable file", async () => {
    globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);

      if (url.startsWith("https://www.googleapis.com/drive/v3/files/file-1?fields=")) {
        const authHeader = new Headers(init?.headers).get("Authorization");
        assert.equal(authHeader, "Bearer gdrive-token");
        return new Response(
          JSON.stringify({
            id: "file-1",
            name: "Quarterly Plan.pdf",
            mimeType: "application/pdf"
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }

      if (url === "https://www.googleapis.com/drive/v3/files/file-1?alt=media") {
        const authHeader = new Headers(init?.headers).get("Authorization");
        assert.equal(authHeader, "Bearer gdrive-token");
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
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }

      if (payload.method === "notifications/initialized") {
        return new Response("", { status: 200, headers: { "Content-Type": "application/json" } });
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
                  title: "Download File Content",
                  inputSchema: {
                    type: "object",
                    properties: {
                      fileId: { type: "string" }
                    },
                    required: ["fileId"]
                  }
                }
              ]
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
            content: [{ type: "text", text: "The caller does not have permission" }],
            isError: true
          }
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    const provider = new McpToolProvider({
      servers: [
        {
          id: "gdrive",
          transport: "http",
          baseUrl: "https://drivemcp.googleapis.com/mcp/v1",
          authTokenEnv: "GOOGLE_DRIVE_MCP_ACCESS_TOKEN",
          authToken: "gdrive-token",
          allowedToolNames: ["download_file_content"],
          enabled: true
        }
      ]
    });

    const [tool] = await provider.discover("gdrive");
    assert.ok(tool);

    const result = await provider.execute(
      tool,
      { fileId: "file-1" },
      { appId: "app_001" }
    );

    assert.deepEqual(result, {
      file_id: "file-1",
      name: "Quarterly Plan.pdf",
      mime_type: "application/pdf",
      content: Buffer.from("pdf-content").toString("base64"),
      content_encoding: "base64",
      auth_context: {
        provider_id: "gdrive",
        auth_token_env: "GOOGLE_DRIVE_MCP_ACCESS_TOKEN",
        auth_source: "mcp_server_auth_token"
      }
    });
  });

  it("does not use Drive REST fallback when fallback policy disables it", async () => {
    const defaultPolicy = buildDefaultRuntimePolicyConfig();
    globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);

      if (url.includes("www.googleapis.com/drive/v3/files/")) {
        assert.fail(
          "Drive REST fallback should not run when fallback policy disables it."
        );
      }

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
        return new Response("", { status: 200, headers: { "Content-Type": "application/json" } });
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
                  title: "Download File Content",
                  inputSchema: {
                    type: "object",
                    properties: {
                      fileId: { type: "string" }
                    },
                    required: ["fileId"]
                  }
                }
              ]
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
            content: [{ type: "text", text: "The caller does not have permission" }],
            isError: true
          }
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    const provider = new McpToolProvider(
      {
        servers: [
          {
            id: "gdrive",
            transport: "http",
            baseUrl: "https://drivemcp.googleapis.com/mcp/v1",
            authTokenEnv: "GOOGLE_DRIVE_MCP_ACCESS_TOKEN",
            authToken: "gdrive-token",
            allowedToolNames: ["download_file_content"],
            enabled: true
          }
        ]
      },
      {
        policy: {
          ...defaultPolicy,
          fallbacks: {
            ...defaultPolicy.fallbacks,
            tools: {
              ...defaultPolicy.fallbacks.tools,
              "mcp.gdrive.download_file_content": {
                enabled: false,
                strategy: "rest_api",
                allowedErrorClasses: ["permission_rejected"]
              }
            }
          }
        }
      }
    );

    const [tool] = await provider.discover("gdrive");
    assert.ok(tool);

    await assert.rejects(
      () => provider.execute(tool, { fileId: "file-1" }, { appId: "app_001" }),
      (error: unknown) =>
        error instanceof AppError && error.code === "MCP_TOOL_CALL_FAILED"
    );
  });

  it("discovers and executes the Gmail draft tool as a side-effecting write path", async () => {
    let callArguments: Record<string, unknown> | undefined;
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
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }

      if (payload.method === "notifications/initialized") {
        return new Response("", { status: 200, headers: { "Content-Type": "application/json" } });
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

      callArguments = payload.params?.arguments;
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
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    const provider = new McpToolProvider({
      servers: [
        {
          id: "gmail",
          transport: "http",
          baseUrl: "https://gmailmcp.googleapis.com/mcp/v1",
          authTokenEnv: "GMAIL_MCP_ACCESS_TOKEN",
          authToken: "gmail-token",
          allowedToolNames: ["create_draft"],
          enabled: true
        }
      ]
    });

    const [tool] = await provider.discover("gmail");
    assert.ok(tool);
    assert.equal(tool.id, "mcp.gmail.create_draft");
    assert.equal(tool.sideEffecting, true);
    assert.deepEqual(tool.permissionScopes, ["external_api.write"]);

    const result = await provider.execute(
      tool,
      {
        to: "alice@example.com",
        subject: "Hello",
        body: "Draft content"
      },
      { appId: "app_001" }
    );

    assert.deepEqual(callArguments, {
      to: ["alice@example.com"],
      subject: "Hello",
      body: "Draft content"
    });
    assert.deepEqual(result, {
      id: "draft-1",
      status: "draft_created",
      threadId: "thread-1"
    });
  });

  it("discovers and executes the Gmail attachment draft tool using app-scoped artifacts", async () => {
    let callArguments: Record<string, unknown> | undefined;
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
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }

      if (payload.method === "notifications/initialized") {
        return new Response("", { status: 200, headers: { "Content-Type": "application/json" } });
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

      callArguments = payload.params?.arguments;
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
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    const provider = new McpToolProvider(
      {
        servers: [
          {
            id: "gmail",
            transport: "http",
            baseUrl: "https://gmailmcp.googleapis.com/mcp/v1",
            authTokenEnv: "GMAIL_MCP_ACCESS_TOKEN",
            authToken: "gmail-token",
            allowedToolNames: ["create_draft"],
            enabled: true
          }
        ]
      },
      {
        artifactStore: {
          async load(appId: string, artifactId: string) {
            assert.equal(appId, "app_001");
            if (artifactId === "artifact_1") {
              return {
                artifact_id: artifactId,
                artifact_type: "google_drive_export",
                path: "/tmp/artifact_1.json",
                content: {
                  name: "Quarterly Plan.pdf",
                  mime_type: "application/pdf",
                  content: "cGRmLWNvbnRlbnQ=",
                  content_encoding: "base64"
                }
              };
            }
            assert.equal(artifactId, "artifact_2");
            return {
              artifact_id: artifactId,
              artifact_type: "chat_export",
              display_name: "session-chat-export.md",
              path: "/tmp/artifact_2.json",
              content: {
                name: "session-chat-export.md",
                mime_type: "text/markdown",
                content: "# Exported chat"
              }
            };
          }
        } as never
      }
    );

    const discovered = await provider.discover("gmail");
    const tool = discovered.find(
      (entry) => entry.id === "mcp.gmail.create_draft_with_attachments"
    );
    assert.ok(tool);
    assert.deepEqual(tool.permissionScopes, ["external_api.write", "artifact.read"]);

    const result = await provider.execute(
      tool,
      {
        to: "alice@example.com",
        subject: "Hello",
        body: "Draft content",
        artifactIds: ["artifact_1", "artifact_2"]
      },
      { appId: "app_001" }
    );

    assert.deepEqual(callArguments, {
      to: ["alice@example.com"],
      subject: "Hello",
      body: "Draft content",
      attachments: [
        {
          filename: "Quarterly Plan.pdf",
          mimeType: "application/pdf",
          content: "cGRmLWNvbnRlbnQ="
        },
        {
          filename: "session-chat-export.md",
          mimeType: "text/markdown",
          content: "IyBFeHBvcnRlZCBjaGF0"
        }
      ]
    });
    assert.deepEqual(result, {
      id: "draft-attachment-1",
      status: "draft_created",
      threadId: "thread-attachment-1"
    });
  });

  it("fails cleanly when an attachment artifact cannot satisfy binary payload consumption", async () => {
    globalThis.fetch = (async (_input: string | URL | Request, init?: RequestInit) => {
      const payload = JSON.parse(String(init?.body ?? "{}")) as {
        method?: string;
      };

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
        return new Response("", { status: 200, headers: { "Content-Type": "application/json" } });
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

      assert.fail("Remote Gmail tool should not be called when artifact resolution fails.");
    }) as typeof fetch;

    const provider = new McpToolProvider(
      {
        servers: [
          {
            id: "gmail",
            transport: "http",
            baseUrl: "https://gmailmcp.googleapis.com/mcp/v1",
            authTokenEnv: "GMAIL_MCP_ACCESS_TOKEN",
            authToken: "gmail-token",
            allowedToolNames: ["create_draft"],
            enabled: true
          }
        ]
      },
      {
        artifactStore: {
          async load(appId: string, artifactId: string) {
            assert.equal(appId, "app_001");
            assert.equal(artifactId, "artifact_1");
            return {
              artifact_id: artifactId,
              artifact_type: "google_drive_export",
              display_name: "Quarterly Plan.pdf",
              app_id: appId,
              created_at: new Date().toISOString(),
              provider_origin: "local",
              path: "/tmp/artifact_1.json",
              status: "ready",
              content: {
                name: "Quarterly Plan.pdf",
                mime_type: "application/pdf"
              }
            };
          }
        } as never
      }
    );

    const discovered = await provider.discover("gmail");
    const tool = discovered.find(
      (entry) => entry.id === "mcp.gmail.create_draft_with_attachments"
    );
    assert.ok(tool);

    await assert.rejects(
      () =>
        provider.execute(
          tool,
          {
            to: "alice@example.com",
            subject: "Hello",
            body: "Draft content",
            artifactIds: ["artifact_1"]
          },
          { appId: "app_001" }
        ),
      (error: unknown) =>
        error instanceof AppError &&
        error.code === "ARTIFACT_CONSUMPTION_UNAVAILABLE"
    );
  });

  it("falls back to Gmail REST draft creation when the managed Gmail MCP tool rejects a draft create", async () => {
    let gmailRestBody: Record<string, unknown> | undefined;
    globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);

      if (url === "https://gmail.googleapis.com/gmail/v1/users/me/drafts") {
        const authHeader = new Headers(init?.headers).get("Authorization");
        assert.equal(authHeader, "Bearer gmail-token");
        gmailRestBody = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
        return new Response(
          JSON.stringify({
            id: "draft-rest-1",
            message: {
              id: "msg-rest-1",
              threadId: "thread-rest-1"
            }
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }

      const payload = JSON.parse(String(init?.body ?? "{}")) as {
        method?: string;
      };

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
        return new Response("", { status: 200, headers: { "Content-Type": "application/json" } });
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
            content: [{ type: "text", text: "The caller does not have permission" }],
            isError: true
          }
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    const provider = new McpToolProvider(
      {
        servers: [
          {
            id: "gmail",
            transport: "http",
            baseUrl: "https://gmailmcp.googleapis.com/mcp/v1",
            authTokenEnv: "GMAIL_MCP_ACCESS_TOKEN",
            authToken: "gmail-token",
            allowedToolNames: ["create_draft"],
            enabled: true
          }
        ]
      },
      {
        artifactStore: {
          async load(appId: string, artifactId: string) {
            assert.equal(appId, "app_001");
            assert.equal(artifactId, "artifact_1");
            return {
              artifact_id: artifactId,
              artifact_type: "google_drive_export",
              path: "/tmp/artifact_1.json",
              content: {
                name: "Quarterly Plan.pdf",
                mime_type: "application/pdf",
                content: "cGRmLWNvbnRlbnQ=",
                content_encoding: "base64"
              }
            };
          }
        } as never
      }
    );

    const discovered = await provider.discover("gmail");
    const tool = discovered.find(
      (entry) => entry.id === "mcp.gmail.create_draft_with_attachments"
    );
    assert.ok(tool);

    const result = await provider.execute(
      tool,
      {
        to: "alice@example.com",
        subject: "Hello",
        body: "Draft content",
        artifactIds: ["artifact_1"]
      },
      { appId: "app_001" }
    );

    const raw = String(
      ((gmailRestBody?.message as { raw?: unknown } | undefined)?.raw ?? "")
    );
    const decoded = Buffer.from(
      raw.replace(/-/g, "+").replace(/_/g, "/"),
      "base64"
    ).toString("utf-8");
    assert.match(decoded, /To: alice@example\.com/);
    assert.match(decoded, /Subject: Hello/);
    assert.match(decoded, /filename="Quarterly Plan\.pdf"/);
    assert.match(decoded, /Content-Transfer-Encoding: base64/);
    assert.match(decoded, /cGRmLWNvbnRlbnQ=/);
    assert.deepEqual(result, {
      id: "draft-rest-1",
      status: "draft_created",
      threadId: "thread-rest-1",
      auth_context: {
        provider_id: "gmail",
        auth_token_env: "GMAIL_MCP_ACCESS_TOKEN",
        auth_source: "mcp_server_auth_token"
      }
    });
  });

  it("discovers and executes the Gmail send-draft tool as a side-effecting write path", async () => {
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
        return new Response("", { status: 200, headers: { "Content-Type": "application/json" } });
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
              status: "sent",
              threadId: "thread-1"
            }
          }
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    const provider = new McpToolProvider({
      servers: [
        {
          id: "gmail",
          transport: "http",
          baseUrl: "https://gmailmcp.googleapis.com/mcp/v1",
          authTokenEnv: "GMAIL_MCP_ACCESS_TOKEN",
          authToken: "gmail-token",
          allowedToolNames: ["send_draft"],
          enabled: true
        }
      ]
    });

    const [tool] = await provider.discover("gmail");
    assert.ok(tool);
    assert.equal(tool.id, "mcp.gmail.send_draft");
    assert.equal(tool.sideEffecting, true);
    assert.deepEqual(tool.permissionScopes, ["external_api.write"]);

    const result = await provider.execute(
      tool,
      {
        draftId: "draft-1"
      },
      { appId: "app_001" }
    );

    assert.deepEqual(result, {
      id: "sent-message-1",
      status: "sent",
      threadId: "thread-1"
    });
  });

  it("discovers and executes the Gmail send-message tool as a side-effecting write path", async () => {
    let callArguments: Record<string, unknown> | undefined;
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
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }

      if (payload.method === "notifications/initialized") {
        return new Response("", { status: 200, headers: { "Content-Type": "application/json" } });
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

      callArguments = payload.params?.arguments;
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
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    const provider = new McpToolProvider({
      servers: [
        {
          id: "gmail",
          transport: "http",
          baseUrl: "https://gmailmcp.googleapis.com/mcp/v1",
          authTokenEnv: "GMAIL_MCP_ACCESS_TOKEN",
          authToken: "gmail-token",
          allowedToolNames: ["send_message"],
          enabled: true
        }
      ]
    });

    const [tool] = await provider.discover("gmail");
    assert.ok(tool);
    assert.equal(tool.id, "mcp.gmail.send_message");
    assert.equal(tool.sideEffecting, true);
    assert.deepEqual(tool.permissionScopes, ["external_api.write"]);

    const result = await provider.execute(
      tool,
      {
        to: "alice@example.com",
        subject: "Hello",
        body: "Direct send content"
      },
      { appId: "app_001" }
    );

    assert.deepEqual(callArguments, {
      to: ["alice@example.com"],
      subject: "Hello",
      body: "Direct send content"
    });
    assert.deepEqual(result, {
      id: "sent-message-2",
      status: "sent",
      threadId: "thread-2"
    });
  });
});
