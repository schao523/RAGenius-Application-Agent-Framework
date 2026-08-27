import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { evaluateCodexInteractiveOperations } from "../../src/core/interactive/codex-interactive-result-evaluator.js";

const requiredSend = {
  operation_id: "agent_external_write",
  kind: "external_write" as const,
  description: "Send one message.",
  required: true,
  minimum_verification: "provider_reported" as const
};

describe("Codex interactive result evaluator", () => {
  it("keeps a denied required MCP operation terminally failed", () => {
    const result = evaluateCodexInteractiveOperations({
      operationPlan: [requiredSend],
      outcomes: [{
        errorCode: "permission_denied",
        itemId: "mcp-1",
        operationId: "agent_external_write",
        status: "failed",
        toolName: "gmail.send_message"
      }]
    });
    assert.equal(result.statusOverride, "failed");
    assert.equal(result.failureCode, "MCP_OPERATION_BLOCKED");
    assert.equal(result.operationVerification[0]?.status, "failed");
  });

  it("accepts provider-observed success and ignores optional failures", () => {
    const result = evaluateCodexInteractiveOperations({
      operationPlan: [requiredSend, { ...requiredSend, operation_id: "optional", required: false }],
      outcomes: [
        { itemId: "mcp-1", operationId: "agent_external_write", status: "completed", toolName: "gmail.send_message" },
        { errorCode: "not_found", itemId: "mcp-2", operationId: "optional", status: "failed", toolName: "gmail.lookup" }
      ]
    });
    assert.equal(result.statusOverride, "completed");
    assert.equal(result.failureCode, null);
  });

  it("accepts a successful retry after a non-denial provider failure", () => {
    const result = evaluateCodexInteractiveOperations({
      operationPlan: [requiredSend],
      outcomes: [
        {
          errorCode: "provider_error",
          itemId: "mcp-1",
          status: "failed",
          toolName: "chrome.get_window_state"
        },
        {
          itemId: "mcp-2",
          status: "completed",
          toolName: "chrome.get_window_state"
        }
      ]
    });

    assert.equal(result.statusOverride, "completed");
    assert.equal(result.failureCode, null);
    assert.equal(result.operationVerification[0]?.status, "completed");
  });

  it("requires explicit correlation when more than one required operation exists", () => {
    const result = evaluateCodexInteractiveOperations({
      operationPlan: [requiredSend, { ...requiredSend, operation_id: "second_required" }],
      outcomes: [{ itemId: "mcp-1", status: "completed", toolName: "gmail.lookup" }]
    });
    assert.equal(result.statusOverride, "failed");
    assert.equal(result.operationVerification[0]?.status, "not_run");
  });

  it("binds unlabelled evidence only to a sole required operation", () => {
    const result = evaluateCodexInteractiveOperations({
      operationPlan: [requiredSend],
      outcomes: [{ itemId: "mcp-1", status: "completed", toolName: "gmail.send_message" }]
    });
    assert.equal(result.statusOverride, "completed");
    assert.equal(result.operationVerification[0]?.status, "completed");
  });
});
