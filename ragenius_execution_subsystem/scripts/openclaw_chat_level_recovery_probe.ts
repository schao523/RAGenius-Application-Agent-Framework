import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { promisify } from "node:util";

import { OpenClawGatewayClient } from "../src/core/interactive/openclaw-gateway-client.js";
import { buildOpenClawInteractiveSessionKey } from "../src/core/interactive/openclaw-gateway-events.js";

type Evidence = {
  id: string;
  result: "pass" | "fail" | "observation";
  detail: Record<string, unknown>;
};

const rawCredential = process.env.OPENCLAW_GATEWAY_APPROVAL_TOKEN?.trim();
assert.ok(rawCredential, "OPENCLAW_GATEWAY_APPROVAL_TOKEN is required.");
const credential: string = rawCredential;
const gatewayUrl = process.env.OPENCLAW_GATEWAY_URL || "ws://127.0.0.1:18789";
const agentId = process.env.OPENCLAW_AGENT_ID || "main";
const execFileAsync = promisify(execFile);
const suffix = randomUUID().replaceAll("-", "");
const evidence: Evidence[] = [];
let client = await connectWithRetry();
let outputByRun = new Map<string, string>();
attachCapture(client);

try {
  const idleKey = sessionKey(`idle_${suffix}`);
  const marker = `RESTART-${suffix.slice(0, 8)}`;
  const beforeRestart = await runTurn(idleKey, `Remember marker ${marker}. Reply exactly: READY`, `idle_start_${suffix}`);
  await client.close();
  await restartGateway();
  client = await connectWithRetry();
  outputByRun = new Map<string, string>();
  attachCapture(client);
  const afterRestart = await runTurn(
    idleKey,
    "Reply with the exact marker remembered before the Gateway restart and nothing else.",
    `idle_resume_${suffix}`
  );
  evidence.push({
    id: "CL-17",
    result: isOk(beforeRestart.status) && isOk(afterRestart.status) && afterRestart.output.includes(marker)
      ? "pass"
      : "fail",
    detail: {
      before_run_hash: hash(beforeRestart.runId),
      after_run_hash: hash(afterRestart.runId),
      marker_retained: afterRestart.output.includes(marker),
      output_excerpt: bounded(afterRestart.output, 300)
    }
  });

  const disconnectKey = sessionKey(`disconnect_${suffix}`);
  const disconnectStarted = await client.request("agent", {
    agentId,
    deliver: false,
    idempotencyKey: `disconnect_${suffix}`,
    message: "Wait silently for 3 seconds, then reply exactly: DISCONNECT_RECOVERED",
    sessionKey: disconnectKey
  });
  const disconnectRunId = stringField(disconnectStarted, "runId");
  assert.ok(disconnectRunId);
  await client.close();
  await delay(4500);
  client = await connectWithRetry();
  outputByRun = new Map<string, string>();
  attachCapture(client);
  const disconnectWait = await client.request("agent.wait", {
    runId: disconnectRunId,
    timeoutMs: 15000
  });
  evidence.push({
    id: "CL-16",
    result: isOk(waitStatus(disconnectWait)) ? "pass" : "fail",
    detail: {
      accepted_run_hash: hash(disconnectRunId),
      reconciled_status: waitStatus(disconnectWait),
      method: "agent.wait"
    }
  });

  const activeKey = sessionKey(`active_${suffix}`);
  const activeStarted = await client.request("agent", {
    agentId,
    deliver: false,
    idempotencyKey: `active_restart_${suffix}`,
    message: "Wait silently for 30 seconds, then reply exactly: ACTIVE_RESTART_UNEXPECTED_SUCCESS",
    sessionKey: activeKey
  });
  const activeRunId = stringField(activeStarted, "runId");
  assert.ok(activeRunId);
  await delay(500);
  await client.close();
  await restartGateway();
  client = await connectWithRetry();
  outputByRun = new Map<string, string>();
  attachCapture(client);
  let activeOutcome = "";
  try {
    activeOutcome = waitStatus(await client.request("agent.wait", {
      runId: activeRunId,
      timeoutMs: 15000
    }));
  } catch (error) {
    activeOutcome = `error:${bounded(error instanceof Error ? error.message : String(error), 500)}`;
  }
  evidence.push({
    id: "CL-18",
    result: isOk(activeOutcome) ? "fail" : "pass",
    detail: {
      run_id_hash: hash(activeRunId),
      reconciled_outcome: activeOutcome,
      success_claimed: isOk(activeOutcome)
    }
  });

  const timeoutKey = sessionKey(`timeout_${suffix}`);
  const timeoutStarted = await client.request("agent", {
    agentId,
    deliver: false,
    idempotencyKey: `timeout_${suffix}`,
    message: "Wait silently for 20 seconds, then reply exactly: TIMEOUT_UNEXPECTED_SUCCESS",
    sessionKey: timeoutKey
  });
  const timeoutRunId = stringField(timeoutStarted, "runId");
  assert.ok(timeoutRunId);
  let timeoutOutcome = "";
  try {
    timeoutOutcome = waitStatus(await client.request("agent.wait", {
      runId: timeoutRunId,
      timeoutMs: 1000
    }));
  } catch (error) {
    timeoutOutcome = `error:${bounded(error instanceof Error ? error.message : String(error), 300)}`;
  }
  await client.request("chat.abort", { agentId, runId: timeoutRunId, sessionKey: timeoutKey });
  const timeoutAbort = waitStatus(await client.request("agent.wait", {
    runId: timeoutRunId,
    timeoutMs: 15000
  }));
  evidence.push({
    id: "CL-21",
    result: !isOk(timeoutOutcome) && ["aborted", "cancelled"].includes(timeoutAbort) ? "pass" : "fail",
    detail: {
      run_id_hash: hash(timeoutRunId),
      timeout_outcome: timeoutOutcome,
      post_abort_outcome: timeoutAbort
    }
  });

  const deletedKey = sessionKey(`deleted_${suffix}`);
  await runTurn(deletedKey, "Remember marker DELETED_SESSION. Reply exactly: STORED", `deleted_start_${suffix}`);
  const deletedRecord = findSession(await client.request("sessions.list", {}), deletedKey);
  const storedKey = stringField(deletedRecord, "key") || stringField(deletedRecord, "sessionKey");
  assert.ok(storedKey, "Disposable session was not listed before deletion.");
  await client.request("sessions.delete", { key: storedKey, agentId, deleteTranscript: true });
  const recreated = await runTurn(
    deletedKey,
    "If you remember the marker from the deleted session, reply with it. Otherwise reply exactly: CONTEXT_MISSING",
    `deleted_followup_${suffix}`
  );
  evidence.push({
    id: "CL-20-provider-observation",
    result: "observation",
    detail: {
      provider_accepted_replacement: isOk(recreated.status),
      replacement_run_hash: hash(recreated.runId),
      output_excerpt: bounded(recreated.output, 300),
      required_ragenius_behavior: "reject before provider contact"
    }
  });
} catch (error) {
  evidence.push({
    id: "HARNESS",
    result: "fail",
    detail: { error: bounded(error instanceof Error ? error.message : String(error), 1000) }
  });
  process.exitCode = 1;
} finally {
  const cleanup = await cleanupProbeSessions(client).catch((error) => ({
    deleted: 0,
    error: bounded(error instanceof Error ? error.message : String(error), 500)
  }));
  evidence.push({ id: "CLEANUP", result: "observation", detail: cleanup });
  await client.close().catch(() => undefined);
  process.stdout.write(`${JSON.stringify({ generated_at: new Date().toISOString(), evidence }, null, 2)}\n`);
}

async function connectWithRetry(): Promise<OpenClawGatewayClient> {
  let lastError: Error | undefined;
  for (let attempt = 0; attempt < 20; attempt += 1) {
    try {
      return await new OpenClawGatewayClient({
        credential,
        gatewayUrl,
        maxMessageBytes: 1048576,
        reconnectBaseDelayMs: 250,
        reconnectMaxAttempts: 3,
        rpcTimeoutMs: 30000,
        scopes: ["operator.admin", "operator.approvals"]
      }).connect();
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));
      await delay(500);
    }
  }
  throw lastError ?? new Error("Gateway did not become ready.");
}

function attachCapture(target: OpenClawGatewayClient): void {
  target.onEvent(async (frame) => {
    if (stringField(frame, "event") !== "agent") return;
    const payload = recordField(frame, "payload");
    if (stringField(payload, "stream") !== "assistant") return;
    const runId = stringField(payload, "runId");
    const data = recordField(payload, "data");
    const delta = stringField(data, "delta") || stringField(data, "text");
    if (runId && delta) outputByRun.set(runId, bounded(`${outputByRun.get(runId) || ""}${delta}`, 5000));
  });
}

async function runTurn(key: string, message: string, idempotencyKey: string) {
  const started = await client.request("agent", {
    agentId,
    deliver: false,
    idempotencyKey,
    message,
    sessionKey: key
  });
  const runId = stringField(started, "runId");
  assert.ok(runId);
  const waited = await client.request("agent.wait", { runId, timeoutMs: 120000 });
  await delay(150);
  return { runId, status: waitStatus(waited), output: outputByRun.get(runId) || "" };
}

async function restartGateway(): Promise<void> {
  await execFileAsync("wsl", ["-d", "OpenClawGateway", "--", "openclaw", "gateway", "restart"]);
}

async function cleanupProbeSessions(target: OpenClawGatewayClient): Promise<Record<string, unknown>> {
  const listed = asRecord(await target.request("sessions.list", {}));
  const sessions = Array.isArray(listed.sessions) ? listed.sessions.map(asRecord) : [];
  const keys = sessions
    .map((session) => stringField(session, "key") || stringField(session, "sessionKey"))
    .filter((key) => key.includes("taskflow_probe"));
  let deleted = 0;
  for (const key of keys) {
    await target.request("sessions.delete", { key, agentId, deleteTranscript: true });
    deleted += 1;
  }
  return { matched: keys.length, deleted };
}

function sessionKey(label: string): string {
  return buildOpenClawInteractiveSessionKey({
    appId: "taskflow_probe",
    sessionId: `session_${label}`,
    agentSessionId: `agent_${label}`
  });
}

function findSession(value: unknown, key: string): Record<string, unknown> {
  const root = asRecord(value);
  const sessions = Array.isArray(root.sessions) ? root.sessions.map(asRecord) : [];
  return sessions.find((session) => {
    const candidate = stringField(session, "key") || stringField(session, "sessionKey");
    return candidate === key || candidate === `agent:${agentId}:${key}`;
  }) || {};
}

function waitStatus(value: unknown): string {
  return stringField(value, "error") || stringField(value, "status") || stringField(value, "stopReason");
}

function isOk(value: string): boolean {
  return ["completed", "ok", "success"].includes(value);
}

function hash(value: string): string {
  return value ? `sha256:${createHash("sha256").update(value).digest("hex")}` : "";
}

function bounded(value: string, max: number): string {
  return value.length <= max ? value : `${value.slice(0, max)}...[truncated]`;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function recordField(value: unknown, key: string): Record<string, unknown> {
  return asRecord(asRecord(value)[key]);
}

function stringField(value: unknown, key: string): string {
  const field = asRecord(value)[key];
  return typeof field === "string" ? field : "";
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
