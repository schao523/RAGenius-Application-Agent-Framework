import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";

import { McpHttpClient } from "../../src/core/tools/providers/mcp-http-client.js";

const originalFetch = globalThis.fetch;

describe("mcp http client", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("sends bearer auth, initializes, and reuses returned session id", async () => {
    const seenHeaders: Array<Record<string, string | null>> = [];
    globalThis.fetch = (async (_input: string | URL | Request, init?: RequestInit) => {
      const headers = new Headers(init?.headers);
      seenHeaders.push({
        accept: headers.get("Accept"),
        authorization: headers.get("Authorization"),
        method: headers.get("Mcp-Method"),
        protocolVersion: headers.get("Mcp-Protocol-Version"),
        session: headers.get("Mcp-Session-Id")
      });

      const payload = JSON.parse(String(init?.body ?? "{}")) as {
        method?: string;
      };
      if (payload.method === "initialize") {
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 1,
            result: {
              protocolVersion: "2025-06-18"
            }
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json", "Mcp-Session-Id": "session-123" }
          }
        );
      }

      return new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          result: {
            tools: []
          }
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" }
        }
      );
    }) as typeof fetch;

    const client = new McpHttpClient({
      authToken: "token-abc",
      baseUrl: "https://gmailmcp.googleapis.com/mcp/v1"
    });

    await client.initialize();
    await client.listTools();

    assert.equal(seenHeaders[0]?.authorization, "Bearer token-abc");
    assert.equal(seenHeaders[0]?.accept, "application/json, text/event-stream");
    assert.equal(seenHeaders[0]?.method, "initialize");
    assert.equal(seenHeaders[0]?.protocolVersion, "2025-06-18");
    assert.equal(seenHeaders[0]?.session, null);
    assert.equal(seenHeaders[1]?.method, "notifications/initialized");
    assert.equal(seenHeaders[1]?.session, "session-123");
    assert.equal(seenHeaders[2]?.method, "tools/list");
  });

  it("lists tools and returns normalized remote tool definitions", async () => {
    globalThis.fetch = (async () =>
      new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          result: {
            tools: [
              {
                name: "search_messages",
                title: "Search Gmail Messages",
                description: "Search messages by query",
                inputSchema: {
                  type: "object",
                  properties: {
                    query: { type: "string" }
                  },
                  required: ["query"]
                }
              }
            ]
          }
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" }
        }
      )) as typeof fetch;

    const client = new McpHttpClient({
      baseUrl: "https://gmailmcp.googleapis.com/mcp/v1"
    });

    const tools = await client.listTools();

    assert.equal(tools.length, 1);
    assert.equal(tools[0]?.name, "search_messages");
  });

  it("calls a remote tool and prefers structured content", async () => {
    globalThis.fetch = (async () =>
      new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          result: {
            structuredContent: {
              results: [{ id: "msg-1", subject: "Hello" }]
            }
          }
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" }
        }
      )) as typeof fetch;

    const client = new McpHttpClient({
      baseUrl: "https://gmailmcp.googleapis.com/mcp/v1"
    });

    const result = await client.callTool("search_messages", { query: "hello" });

    assert.deepEqual(result, {
      results: [{ id: "msg-1", subject: "Hello" }]
    });
  });

  it("includes remote auth failure body in MCP provider auth errors", async () => {
    globalThis.fetch = (async () =>
      new Response(
        JSON.stringify({
          error: {
            code: 403,
            message: "Forbidden"
          }
        }),
        {
          status: 403,
          headers: { "Content-Type": "application/json" }
        }
      )) as typeof fetch;

    const client = new McpHttpClient({
      authToken: "token-abc",
      baseUrl: "https://drivemcp.googleapis.com/mcp/v1"
    });

    await assert.rejects(
      () => client.initialize(),
      (error: unknown) => {
        assert.equal(
          (error as { code?: string }).code,
          "MCP_PROVIDER_AUTH_FAILED"
        );
        assert.match(
          String(
            (error as { details?: { response_body?: string } }).details
              ?.response_body ?? ""
          ),
          /Forbidden/
        );
        return true;
      }
    );
  });

  it("includes remote response body in generic MCP transport failures", async () => {
    globalThis.fetch = (async () =>
      new Response(
        JSON.stringify({
          error: {
            code: 400,
            message: "Bad Request"
          }
        }),
        {
          status: 400,
          headers: { "Content-Type": "application/json" }
        }
      )) as typeof fetch;

    const client = new McpHttpClient({
      authToken: "token-abc",
      baseUrl: "https://gmailmcp.googleapis.com/mcp/v1"
    });

    await assert.rejects(
      () => client.initialize(),
      (error: unknown) => {
        assert.equal(
          (error as { code?: string }).code,
          "MCP_TRANSPORT_FAILED"
        );
        assert.match(
          String(
            (error as { details?: { response_body?: string } }).details
              ?.response_body ?? ""
          ),
          /Bad Request/
        );
        return true;
      }
    );
  });
});
