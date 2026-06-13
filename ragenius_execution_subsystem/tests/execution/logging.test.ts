import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { createAuditRecord } from "../../src/core/logging/audit-log.js";
import { ExecutionLogger } from "../../src/core/logging/logger.js";
import { redactSensitiveValue } from "../../src/utils/redact.js";

describe("logging and redaction", () => {
  it("redacts secrets from nested log payloads", () => {
    const redacted = redactSensitiveValue({
      authorization: "Bearer secret-token",
      nested: {
        password: "super-secret",
        safe: "value"
      }
    });

    assert.equal(redacted.authorization, "[REDACTED]");
    assert.equal(redacted.nested.password, "[REDACTED]");
    assert.equal(redacted.nested.safe, "value");
  });

  it("creates redacted execution log events", () => {
    const logger = new ExecutionLogger();
    const event = logger.createEvent({
      level: "info",
      eventType: "tool.called",
      message: "Tool call completed.",
      summary: {
        api_key: "secret",
        tool_id: "mock_video_generation_tool"
      }
    });

    assert.equal(event.summary?.api_key, "[REDACTED]");
    assert.equal(event.summary?.tool_id, "mock_video_generation_tool");
  });

  it("creates audit records with execution context", () => {
    const record = createAuditRecord({
      executionId: "exec_001",
      appId: "app_001",
      sessionId: "sess_001",
      skillId: "video_director_skill",
      level: "audit",
      eventType: "execution.completed",
      message: "Execution completed."
    });

    assert.equal(record.executionId, "exec_001");
    assert.equal(record.skillId, "video_director_skill");
  });
});
