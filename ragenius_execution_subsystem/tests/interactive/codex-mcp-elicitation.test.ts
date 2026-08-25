import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  McpElicitationDecodeError,
  decodeCodexMcpElicitation,
  translateMcpElicitationResponse
} from "../../src/core/interactive/codex-mcp-elicitation.js";

const context = {
  activeThreadId: "thread-1",
  activeTurnId: "turn-1",
  allowedAuthenticationHosts: ["accounts.google.com"],
  authorizationBound: true,
  providerRequestId: 41
} as const;

function form(requestedSchema: Record<string, unknown>, mode = "form") {
  return {
    threadId: "thread-1",
    turnId: "turn-1",
    serverName: "gmail",
    mode,
    message: "Continue with this operation?",
    requestedSchema,
    _meta: null
  };
}

describe("Codex MCP elicitation", () => {
  it("classifies empty and boolean forms as bound approvals", () => {
    for (const schema of [
      { type: "object", properties: {} },
      { type: "object", properties: { confirm: { type: "boolean" } }, required: ["confirm"] }
    ]) {
      const decoded = decodeCodexMcpElicitation(form(schema), context);
      assert.equal(decoded.interactionType, "approval");
      assert.deepEqual(decoded.responseBinding, { kind: "approval" });
    }
  });

  it("refuses to convert a boolean form into consent without bound authorization", () => {
    assert.throws(
      () => decodeCodexMcpElicitation(form({
        type: "object",
        properties: { confirm: { type: "boolean" } }
      }), { ...context, authorizationBound: false }),
      (error) => error instanceof McpElicitationDecodeError && error.code === "MCP_ELICITATION_UNSUPPORTED"
    );
  });

  it("classifies one enum field as a bounded selection", () => {
    const decoded = decodeCodexMcpElicitation(form({
      type: "object",
      properties: { format: { type: "string", enum: ["markdown", "plain"] } },
      required: ["format"]
    }), context);

    assert.equal(decoded.interactionType, "selection");
    assert.deepEqual(decoded.options, [
      { id: "markdown", label: "markdown" },
      { id: "plain", label: "plain" }
    ]);
    assert.deepEqual(decoded.responseBinding, { kind: "field", propertyName: "format" });
  });

  it("classifies one bounded non-secret string field as clarification", () => {
    const decoded = decodeCodexMcpElicitation(form({
      type: "object",
      properties: { audience: { type: "string", maxLength: 200 } },
      required: ["audience"]
    }, "openai/form"), context);

    assert.equal(decoded.interactionType, "clarification");
    assert.equal(decoded.allowsFreeText, true);
    assert.deepEqual(decoded.responseBinding, { kind: "field", propertyName: "audience" });
  });

  it("normalizes an approved HTTPS URL without exposing it in presentation", () => {
    const decoded = decodeCodexMcpElicitation({
      threadId: "thread-1",
      turnId: "turn-1",
      serverName: "gmail",
      mode: "url",
      message: "Sign in to Gmail.",
      url: "https://accounts.google.com/o/oauth2/auth?client_id=protected",
      elicitationId: "elicitation-1",
      _meta: null
    }, context);

    assert.equal(decoded.interactionType, "authentication_handoff");
    assert.deepEqual(decoded.presentation, {
      launchAvailable: true,
      targetHost: "accounts.google.com",
      targetLabel: "gmail"
    });
    assert.deepEqual(decoded.protectedLaunchTarget, {
      kind: "https_url",
      url: "https://accounts.google.com/o/oauth2/auth?client_id=protected"
    });
  });

  it("rejects secrets, unsupported shapes, and oversized values", () => {
    const rejected = [
      form({ type: "object", properties: { password: { type: "string", maxLength: 100 } } }),
      form({ type: "object", properties: { a: { type: "string", maxLength: 10 }, b: { type: "string", maxLength: 10 } } }),
      form({ type: "object", properties: { count: { type: "number" } } }),
      form({ type: "object", properties: { tags: { type: "array" } } }),
      form({ type: "object", properties: { note: { type: "string", maxLength: 8001 } } }),
      form({
        type: "object",
        properties: { note: { type: "string", maxLength: 100 } },
        required: ["different_field"]
      }),
      form({
        type: "object",
        properties: { note: { type: "string", maxLength: 100, widget: "password" } }
      }, "openai/form"),
      { ...form({ type: "object", properties: {} }), message: "x".repeat(2001) }
    ];
    for (const value of rejected) {
      assert.throws(() => decodeCodexMcpElicitation(value, context), McpElicitationDecodeError);
    }
  });

  it("rejects scope mismatch and blocked authentication targets", () => {
    assert.throws(
      () => decodeCodexMcpElicitation({ ...form({ type: "object", properties: {} }), threadId: "other" }, context),
      (error) => error instanceof McpElicitationDecodeError && error.code === "MCP_ELICITATION_SCOPE_MISMATCH"
    );
    for (const url of [
      "http://accounts.google.com/",
      "https://user@accounts.google.com/",
      "https://login.example.com/"
    ]) {
      assert.throws(() => decodeCodexMcpElicitation({
        threadId: "thread-1", turnId: "turn-1", serverName: "gmail",
        mode: "url", message: "Sign in.", url, elicitationId: "e-1", _meta: null
      }, context), (error) =>
        error instanceof McpElicitationDecodeError && error.code === "MCP_ELICITATION_TARGET_BLOCKED"
      );
    }
  });

  it("translates provider-neutral responses into exact MCP responses", () => {
    const selection = decodeCodexMcpElicitation(form({
      type: "object",
      properties: { format: { type: "string", enum: ["markdown", "plain"] } }
    }), context);
    assert.deepEqual(
      translateMcpElicitationResponse(selection, { kind: "selection", option_ids: ["plain"] }),
      { action: "accept", content: { format: "plain" }, _meta: null }
    );
    assert.deepEqual(
      translateMcpElicitationResponse(selection, { kind: "approval", decision: "deny" }),
      { action: "decline", content: null, _meta: null }
    );
    assert.deepEqual(
      translateMcpElicitationResponse(selection, { kind: "approval", decision: "cancel_execution" }),
      { action: "cancel", content: null, _meta: null }
    );
  });
});
