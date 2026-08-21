import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { randomUUID } from "node:crypto";
import { it } from "node:test";
import { promisify } from "node:util";

import { OpenClawGatewayClient } from "../../src/core/interactive/openclaw-gateway-client.js";
import { buildOpenClawInteractiveSessionKey } from "../../src/core/interactive/openclaw-gateway-events.js";

const enabled = process.env.OPENCLAW_GATEWAY_INTERACTIVE_SMOKE === "1";
const approvalEnabled = process.env.OPENCLAW_GATEWAY_APPROVAL_SMOKE === "1";
const execFileAsync = promisify(execFile);

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
    const cancelStatus = stringField(cancelled, "error")
      || stringField(cancelled, "stopReason")
      || stringField(cancelled, "status");
    assert.ok(
      ["aborted", "cancelled"].includes(cancelStatus),
      `Unexpected cancellation response: ${JSON.stringify(cancelled)}`
    );
  } finally {
    await client.close();
  }
});

it("mediates live OpenClaw approvals under the temporary test policy", {
  skip: !approvalEnabled
}, async () => {
  const credentialEnv = process.env.OPENCLAW_GATEWAY_APPROVAL_CREDENTIAL_ENV
    || "OPENCLAW_GATEWAY_APPROVAL_TOKEN";
  const credential = process.env[credentialEnv];
  assert.ok(credential, `Set ${credentialEnv} before running the OpenClaw approval smoke test.`);
  const client = await gatewayClient(credential, ["operator.admin", "operator.approvals"]);
  const events: Array<Record<string, unknown>> = [];
  client.onEvent(async (event) => { events.push(event); });

  try {
    assert.ok(client.hello.scopes.includes("operator.admin"));
    assert.ok(client.hello.scopes.includes("operator.approvals"));
    const suffix = randomUUID().replaceAll("-", "");
    const allowSession = buildOpenClawInteractiveSessionKey({
      appId: "smoke",
      sessionId: `session_allow_${suffix}`,
      agentSessionId: `agent_allow_${suffix}`
    });
    const allowMarker = `/tmp/ragenius-openclaw-write-${suffix}.txt`;
    const allowRun = await client.request("agent", {
      agentId: process.env.OPENCLAW_AGENT_ID || "main",
      deliver: false,
      idempotencyKey: `approval_allow_${suffix}`,
      message: `Use the exec tool to run exactly this command once, then reply DONE: printf 'marker\\n' >> ${allowMarker}`,
      sessionKey: allowSession
    });
    const allowRunId = stringField(allowRun, "runId");
    const allowRequest = await waitForApproval(events, allowSession);
    const allowId = stringField(allowRequest, "id");
    assert.ok(allowId);
    assert.deepEqual(await client.request("exec.approval.resolve", {
      id: allowId, decision: "allow-once"
    }), { ok: true });
    assert.ok(["completed", "ok", "success"].includes(stringField(
      await client.request("agent.wait", { runId: allowRunId, timeoutMs: 120000 }),
      "status"
    )));
    assert.equal(await wslLineCount(allowMarker), 1);

    const resolvedBeforeDuplicate = countResolved(events, allowId);
    assert.deepEqual(await client.request("exec.approval.resolve", {
      id: allowId, decision: "allow-once"
    }), { ok: true });
    await delay(250);
    assert.equal(countResolved(events, allowId), resolvedBeforeDuplicate);

    const denySession = buildOpenClawInteractiveSessionKey({
      appId: "smoke",
      sessionId: `session_deny_${suffix}`,
      agentSessionId: `agent_deny_${suffix}`
    });
    const denyMarker = `/tmp/ragenius-openclaw-blocked-${suffix}.txt`;
    const denyRun = await client.request("agent", {
      agentId: process.env.OPENCLAW_AGENT_ID || "main",
      deliver: false,
      idempotencyKey: `approval_deny_${suffix}`,
      message: `Use the exec tool to run exactly this command once, then reply DONE: printf 'marker\\n' >> ${denyMarker}`,
      sessionKey: denySession
    });
    const denyRequest = await waitForApproval(events, denySession);
    assert.deepEqual(await client.request("exec.approval.resolve", {
      id: stringField(denyRequest, "id"), decision: "deny"
    }), { ok: true });
    await client.request("agent.wait", {
      runId: stringField(denyRun, "runId"), timeoutMs: 120000
    });
    assert.equal(await wslFileExists(denyMarker), false);

    const expiryId = `ragenius-expiry-${suffix}`;
    const expiry = await client.request("exec.approval.request", {
      id: expiryId,
      command: "printf expiry",
      cwd: "/tmp",
      host: "gateway",
      security: "allowlist",
      ask: "on-miss",
      agentId: process.env.OPENCLAW_AGENT_ID || "main",
      sessionKey: allowSession,
      suppressDelivery: true,
      timeoutMs: 1000
    });
    assert.equal(stringField(expiry, "id"), expiryId);
    assert.equal((expiry as Record<string, unknown>).decision, null);
  } finally {
    await client.close();
  }

  const reduced = await gatewayClient(credential, ["operator.approvals"]);
  try {
    assert.equal(reduced.hello.scopes.includes("operator.admin"), false);
    assert.equal(reduced.hello.scopes.includes("operator.approvals"), true);
  } finally {
    await reduced.close();
  }
});

async function gatewayClient(
  credential: string,
  scopes: string[]
): Promise<OpenClawGatewayClient> {
  return new OpenClawGatewayClient({
    credential,
    gatewayUrl: process.env.OPENCLAW_GATEWAY_URL || "ws://127.0.0.1:18789",
    maxMessageBytes: 1048576,
    reconnectBaseDelayMs: 250,
    reconnectMaxAttempts: 3,
    rpcTimeoutMs: 130000,
    scopes
  }).connect();
}

async function waitForApproval(
  events: Array<Record<string, unknown>>,
  sessionKey: string
): Promise<Record<string, unknown>> {
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    for (const event of events) {
      if (stringField(event, "event") !== "exec.approval.requested") continue;
      const payload = recordField(event, "payload");
      const request = recordField(payload, "request");
      const providerSessionKey = stringField(request, "sessionKey");
      if (
        providerSessionKey === sessionKey
        || providerSessionKey === `agent:${process.env.OPENCLAW_AGENT_ID || "main"}:${sessionKey}`
      ) return payload;
    }
    await delay(50);
  }
  throw new Error(`Timed out waiting for OpenClaw approval for ${sessionKey}.`);
}

function countResolved(events: Array<Record<string, unknown>>, id: string): number {
  return events.filter((event) => (
    stringField(event, "event") === "exec.approval.resolved"
    && stringField(recordField(event, "payload"), "id") === id
  )).length;
}

async function wslLineCount(path: string): Promise<number> {
  const { stdout } = await execFileAsync("wsl", [
    "-d", process.env.OPENCLAW_WSL_DISTRO || "OpenClawGateway",
    "--", "wc", "-l", path
  ]);
  return Number.parseInt(stdout.trim().split(/\s+/)[0] || "", 10);
}

async function wslFileExists(path: string): Promise<boolean> {
  try {
    await execFileAsync("wsl", [
      "-d", process.env.OPENCLAW_WSL_DISTRO || "OpenClawGateway",
      "--", "test", "-f", path
    ]);
    return true;
  } catch {
    return false;
  }
}

function recordField(value: unknown, key: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const field = (value as Record<string, unknown>)[key];
  return field && typeof field === "object" && !Array.isArray(field)
    ? field as Record<string, unknown>
    : {};
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function stringField(value: unknown, key: string): string {
  if (!value || typeof value !== "object" || Array.isArray(value)) return "";
  const field = (value as Record<string, unknown>)[key];
  return typeof field === "string" ? field : "";
}
