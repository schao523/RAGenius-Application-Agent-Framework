import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { it } from "node:test";

import { OpenClawGatewayClient } from "../../src/core/interactive/openclaw-gateway-client.js";
import { buildOpenClawInteractiveSessionKey } from "../../src/core/interactive/openclaw-gateway-events.js";

const enabled = process.env.OPENCLAW_GATEWAY_INTERACTIVE_SMOKE === "1";

it("runs and cancels through the live OpenClaw Gateway", { skip: !enabled }, async () => {
  const credentialEnv = process.env.OPENCLAW_GATEWAY_APPROVAL_CREDENTIAL_ENV
    || "OPENCLAW_GATEWAY_APPROVAL_TOKEN";
  const credential = process.env[credentialEnv];
  assert.ok(credential, `Set ${credentialEnv} before running the OpenClaw Gateway smoke test.`);
  const client = await new OpenClawGatewayClient({
    credential,
    gatewayUrl: process.env.OPENCLAW_GATEWAY_URL || "ws://127.0.0.1:18789",
    maxMessageBytes: 1048576,
    reconnectBaseDelayMs: 250,
    reconnectMaxAttempts: 3,
    rpcTimeoutMs: 130000,
    scopes: ["operator.admin", "operator.approvals"]
  }).connect();

  try {
    assert.equal(client.hello.serverVersion, "2026.6.8");
    const suffix = randomUUID().replaceAll("-", "");
    const sessionKey = buildOpenClawInteractiveSessionKey({
      appId: "smoke",
      sessionId: `session_${suffix}`,
      agentSessionId: `agent_${suffix}`
    });
    const started = await client.request("agent", {
      agentId: process.env.OPENCLAW_AGENT_ID || "main",
      deliver: false,
      idempotencyKey: `smoke_${suffix}`,
      message: "Reply exactly: RAGENIUS_OPENCLAW_GATEWAY_SMOKE_OK",
      sessionKey
    });
    const runId = stringField(started, "runId");
    assert.ok(runId);
    const completed = await client.request("agent.wait", { runId, timeoutMs: 120000 });
    assert.ok(["completed", "ok", "success"].includes(stringField(completed, "status")));

    const cancelStarted = await client.request("agent", {
      agentId: process.env.OPENCLAW_AGENT_ID || "main",
      deliver: false,
      idempotencyKey: `cancel_${suffix}`,
      message: "Wait for 30 seconds before replying.",
      sessionKey
    });
    const cancelRunId = stringField(cancelStarted, "runId");
    assert.ok(cancelRunId);
    await client.request("chat.abort", {
      agentId: process.env.OPENCLAW_AGENT_ID || "main",
      runId: cancelRunId,
      sessionKey
    });
    const cancelled = await client.request("agent.wait", {
      runId: cancelRunId,
      timeoutMs: 15000
    });
    const cancelStatus = stringField(cancelled, "stopReason")
      || stringField(cancelled, "error")
      || stringField(cancelled, "status");
    assert.ok(["aborted", "cancelled"].includes(cancelStatus));
  } finally {
    await client.close();
  }
});

function stringField(value: unknown, key: string): string {
  if (!value || typeof value !== "object" || Array.isArray(value)) return "";
  const field = (value as Record<string, unknown>)[key];
  return typeof field === "string" ? field : "";
}
