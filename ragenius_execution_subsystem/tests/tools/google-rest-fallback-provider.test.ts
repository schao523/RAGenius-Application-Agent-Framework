import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";

import { AppError } from "../../src/core/errors/app-error.js";
import { GoogleRestFallbackProvider } from "../../src/core/tools/providers/google-rest-fallback-provider.js";

const originalFetch = globalThis.fetch;

describe("google rest fallback provider", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("downloads Drive file content with non-secret auth context", async () => {
    globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      const authHeader = new Headers(init?.headers).get("Authorization");
      assert.equal(authHeader, "Bearer drive-token");

      if (url.startsWith("https://www.googleapis.com/drive/v3/files/file-1?fields=")) {
        return new Response(
          JSON.stringify({
            id: "file-1",
            name: "Quarterly Plan.pdf",
            mimeType: "application/pdf"
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }

      assert.equal(url, "https://www.googleapis.com/drive/v3/files/file-1?alt=media");
      return new Response(Buffer.from("pdf-content"), {
        status: 200,
        headers: { "Content-Type": "application/pdf" }
      });
    }) as typeof fetch;

    const provider = new GoogleRestFallbackProvider();
    const result = await provider.downloadDriveFileContent(
      {
        id: "gdrive",
        transport: "http",
        baseUrl: "https://drivemcp.googleapis.com/mcp/v1",
        authTokenEnv: "GOOGLE_DRIVE_MCP_ACCESS_TOKEN",
        authToken: "drive-token",
        allowedToolNames: ["download_file_content"],
        enabled: true
      },
      { fileId: "file-1" }
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

  it("creates a Gmail draft with attachments and non-secret auth context", async () => {
    let rawMessage = "";
    globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
      assert.equal(String(input), "https://gmail.googleapis.com/gmail/v1/users/me/drafts");
      const authHeader = new Headers(init?.headers).get("Authorization");
      assert.equal(authHeader, "Bearer gmail-token");
      const body = JSON.parse(String(init?.body ?? "{}")) as {
        message?: { raw?: string };
      };
      rawMessage = String(body.message?.raw ?? "");

      return new Response(
        JSON.stringify({
          id: "draft-1",
          message: {
            id: "message-1",
            threadId: "thread-1"
          }
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    const provider = new GoogleRestFallbackProvider();
    const result = await provider.createGmailDraft(
      {
        id: "gmail",
        transport: "http",
        baseUrl: "https://gmailmcp.googleapis.com/mcp/v1",
        authTokenEnv: "GMAIL_MCP_ACCESS_TOKEN",
        authToken: "gmail-token",
        allowedToolNames: ["create_draft"],
        enabled: true
      },
      {
        to: "alice@example.com",
        subject: "Hello",
        body: "Draft body",
        attachments: [
          {
            filename: "Quarterly Plan.pdf",
            mime_type: "application/pdf",
            content: "cGRmLWNvbnRlbnQ="
          }
        ]
      }
    );

    const decoded = Buffer.from(
      rawMessage.replace(/-/g, "+").replace(/_/g, "/"),
      "base64"
    ).toString("utf-8");
    assert.match(decoded, /To: alice@example\.com/);
    assert.match(decoded, /Subject: Hello/);
    assert.match(decoded, /filename="Quarterly Plan\.pdf"/);
    assert.match(decoded, /cGRmLWNvbnRlbnQ=/);
    assert.deepEqual(result, {
      id: "draft-1",
      status: "draft_created",
      threadId: "thread-1",
      auth_context: {
        provider_id: "gmail",
        auth_token_env: "GMAIL_MCP_ACCESS_TOKEN",
        auth_source: "mcp_server_auth_token"
      }
    });
  });

  it("fails without an OAuth token", async () => {
    const provider = new GoogleRestFallbackProvider();

    await assert.rejects(
      provider.createGmailDraft(
        {
          id: "gmail",
          transport: "http",
          baseUrl: "https://gmailmcp.googleapis.com/mcp/v1",
          authTokenEnv: "GMAIL_MCP_ACCESS_TOKEN",
          allowedToolNames: ["create_draft"],
          enabled: true
        },
        { to: "alice@example.com", subject: "Hello", body: "Draft body" }
      ),
      (error: unknown) =>
        error instanceof AppError && error.code === "MCP_PROVIDER_AUTH_FAILED"
    );
  });
});
