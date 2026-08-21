import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";

import { OpenClawGatewayClient } from "../src/core/interactive/openclaw-gateway-client.js";
import { buildOpenClawInteractiveSessionKey } from "../src/core/interactive/openclaw-gateway-events.js";

type Evidence = {
  id: string;
  result: "pass" | "fail" | "observation";
  elapsed_ms?: number;
  detail: Record<string, unknown>;
};

type TurnResult = {
  elapsedMs: number;
  output: string;
  runId: string;
  status: string;
  stopReason: string;
};

const rawCredential = process.env.OPENCLAW_GATEWAY_APPROVAL_TOKEN?.trim();
assert.ok(rawCredential, "OPENCLAW_GATEWAY_APPROVAL_TOKEN is required.");
const credential: string = rawCredential;

const gatewayUrl = process.env.OPENCLAW_GATEWAY_URL || "ws://127.0.0.1:18789";
const agentId = process.env.OPENCLAW_AGENT_ID || "main";
const expectedVersion = process.env.OPENCLAW_GATEWAY_EXPECTED_VERSION || "2026.6.8";
const suffix = randomUUID().replaceAll("-", "");
const sessionKey = buildOpenClawInteractiveSessionKey({
  appId: "taskflow_probe",
  sessionId: `session_${suffix}`,
  agentSessionId: `agent_${suffix}`
});
const evidence: Evidence[] = [];
let client = await connect();
let outputByRun = new Map<string, string>();
attachCapture(client);

try {
  evidence.push({
    id: "CL-01",
    result: client.hello.serverVersion === expectedVersion ? "pass" : "fail",
    detail: {
      server_version: client.hello.serverVersion,
      expected_version: expectedVersion,
      protocol_version: client.hello.protocolVersion,
      scopes: client.hello.scopes
    }
  });

  const marker = `TF-${suffix.slice(0, 8)}`;
  const initial = await turn(
    `/taskflow Use the TaskFlow skill for this safe conversational workflow. Do not use tools, files, network, browser, or external actions. Remember marker ${marker}. Propose exactly three short titles for a local report about reliable AI assistants. End by asking me to choose 1, 2, or 3.`,
    `initial_${suffix}`
  );
  recordTurn("CL-03", initial, /(?:1[.)]|2[.)]|3[.)])/);
  evidence.push({
    id: "CL-04",
    result: successful(initial.status) && Boolean(initial.runId) ? "pass" : "fail",
    elapsed_ms: initial.elapsedMs,
    detail: turnDetail(initial)
  });

  const selection = await turn(
    "I select title 2. State the selected title, repeat the exact marker from the earlier turn, and ask one bounded clarification question about the intended audience. Do not use tools.",
    `selection_${suffix}`
  );
  evidence.push({
    id: "CL-05/CL-06/CL-07-question",
    result: successful(selection.status) && selection.output.includes(marker) ? "pass" : "fail",
    elapsed_ms: selection.elapsedMs,
    detail: turnDetail(selection)
  });

  const clarification = await turn(
    "The audience is software administrators. Create a four-bullet outline using the selected title and that audience. End with exactly: Choose Continue, Revise, or Cancel.",
    `clarification_${suffix}`
  );
  evidence.push({
    id: "CL-07/CL-08-review",
    result: successful(clarification.status) && /software administrators/i.test(clarification.output)
      ? "pass"
      : "fail",
    elapsed_ms: clarification.elapsedMs,
    detail: turnDetail(clarification)
  });

  const revision = await turn(
    "Revise the outline once: make bullet 3 focus on audit evidence. Show all four bullets again and end with exactly: Choose Continue or Cancel.",
    `revision_${suffix}`
  );
  evidence.push({
    id: "CL-09-revise",
    result: successful(revision.status) && /audit evidence/i.test(revision.output) ? "pass" : "fail",
    elapsed_ms: revision.elapsedMs,
    detail: turnDetail(revision)
  });

  const continued = await turn(
    "Continue. Produce the final concise Markdown report in your response only, using the revised outline. Do not create a file and do not use tools.",
    `continue_${suffix}`
  );
  evidence.push({
    id: "CL-08/CL-09-continue",
    result: successful(continued.status) && /audit evidence/i.test(continued.output)
      ? "pass"
      : "fail",
    elapsed_ms: continued.elapsedMs,
    detail: turnDetail(continued)
  });

  const graceful = await turn(
    "Start a new harmless three-step conversational draft, but do not execute tools. Pause after naming the steps and ask whether to continue.",
    `graceful_start_${suffix}`
  );
  const gracefulCancel = await turn(
    "Cancel this draft gracefully. Do not continue any remaining steps. Return only a short cancellation summary.",
    `graceful_cancel_${suffix}`
  );
  evidence.push({
    id: "CL-10",
    result: successful(graceful.status) && successful(gracefulCancel.status)
      && /cancel/i.test(gracefulCancel.output) ? "pass" : "fail",
    elapsed_ms: graceful.elapsedMs + gracefulCancel.elapsedMs,
    detail: turnDetail(gracefulCancel)
  });

  const duplicateKey = `duplicate_${suffix}`;
  const duplicateFirst = await turn(
    "Reply exactly: DUPLICATE_PROBE_OK",
    duplicateKey
  );
  const duplicateSecond = await turn(
    "Reply exactly: DUPLICATE_PROBE_OK",
    duplicateKey
  );
  evidence.push({
    id: "CL-12-provider-observation",
    result: "observation",
    elapsed_ms: duplicateFirst.elapsedMs + duplicateSecond.elapsedMs,
    detail: {
      first: turnDetail(duplicateFirst),
      second: turnDetail(duplicateSecond),
      same_run_id: duplicateFirst.runId === duplicateSecond.runId
    }
  });

  const activeOne = startTurn(
    "Wait silently for 8 seconds, then reply exactly: CONCURRENT_ONE",
    `concurrent_one_${suffix}`
  );
  await delay(250);
  const activeTwo = startTurn(
    "Reply exactly: CONCURRENT_TWO",
    `concurrent_two_${suffix}`
  );
  const concurrent = await Promise.allSettled([activeOne, activeTwo]);
  evidence.push({
    id: "CL-13-provider-observation",
    result: "observation",
    detail: {
      outcomes: concurrent.map((item) => item.status === "fulfilled"
        ? turnDetail(item.value)
        : { rejected: bounded(item.reason instanceof Error ? item.reason.message : String(item.reason), 500) })
    }
  });

  await client.close();
  outputByRun = new Map<string, string>();
  client = await connect();
  attachCapture(client);
  const reconnect = await turn(
    `After adapter reconnect, reply with the exact marker remembered from this session and nothing else.`,
    `reconnect_${suffix}`
  );
  evidence.push({
    id: "CL-15",
    result: successful(reconnect.status) && reconnect.output.includes(marker) ? "pass" : "fail",
    elapsed_ms: reconnect.elapsedMs,
    detail: turnDetail(reconnect)
  });

  const cancelStartedAt = Date.now();
  const cancelStarted = await client.request("agent", {
    agentId,
    deliver: false,
    idempotencyKey: `authoritative_cancel_${suffix}`,
    message: "Wait silently for 30 seconds, then reply exactly: SHOULD_NOT_COMPLETE",
    sessionKey
  });
  const cancelRunId = stringField(cancelStarted, "runId");
  assert.ok(cancelRunId);
  await delay(500);
  const abort = await client.request("chat.abort", { agentId, runId: cancelRunId, sessionKey });
  const cancelWait = await client.request("agent.wait", { runId: cancelRunId, timeoutMs: 15000 });
  const cancelStatus = stringField(cancelWait, "error")
    || stringField(cancelWait, "stopReason")
    || stringField(cancelWait, "status");
  evidence.push({
    id: "CL-11",
    result: ["aborted", "cancelled"].includes(cancelStatus) ? "pass" : "fail",
    elapsed_ms: Date.now() - cancelStartedAt,
    detail: {
      run_id_hash: hash(cancelRunId),
      abort_acknowledged: recordBoolean(abort, "aborted"),
      wait_status: cancelStatus
    }
  });

  const sessions = await client.request("sessions.list", {});
  const sessionRecord = findSession(sessions, sessionKey);
  evidence.push({
    id: "CL-05-session-identity",
    result: sessionRecord ? "pass" : "fail",
    detail: {
      canonical_session_hash: hash(sessionKey),
      provider_session_id_hash: hash(stringField(sessionRecord, "sessionId")),
      has_active_run: recordBoolean(sessionRecord, "hasActiveRun")
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
  await client.close().catch(() => undefined);
  process.stdout.write(`${JSON.stringify({
    generated_at: new Date().toISOString(),
    gateway_url: gatewayUrl,
    agent_id: agentId,
    canonical_session_hash: hash(sessionKey),
    evidence
  }, null, 2)}\n`);
}

async function connect(): Promise<OpenClawGatewayClient> {
  return new OpenClawGatewayClient({
    credential,
    gatewayUrl,
    maxMessageBytes: 1048576,
    reconnectBaseDelayMs: 250,
    reconnectMaxAttempts: 3,
    rpcTimeoutMs: 150000,
    scopes: ["operator.admin", "operator.approvals"]
  }).connect();
}

function attachCapture(target: OpenClawGatewayClient): void {
  target.onEvent(async (frame) => {
    if (stringField(frame, "event") !== "agent") return;
    const payload = recordField(frame, "payload");
    if (stringField(payload, "stream") !== "assistant") return;
    const runId = stringField(payload, "runId");
    const data = recordField(payload, "data");
    const delta = stringField(data, "delta") || stringField(data, "text");
    if (!runId || !delta) return;
    outputByRun.set(runId, bounded(`${outputByRun.get(runId) || ""}${delta}`, 12000));
  });
}

async function turn(message: string, idempotencyKey: string): Promise<TurnResult> {
  return startTurn(message, idempotencyKey);
}

async function startTurn(message: string, idempotencyKey: string): Promise<TurnResult> {
  const startedAt = Date.now();
  const started = await client.request("agent", {
    agentId,
    deliver: false,
    idempotencyKey,
    message,
    sessionKey
  });
  const runId = stringField(started, "runId");
  assert.ok(runId, `OpenClaw did not return a run id for ${idempotencyKey}.`);
  const waited = await client.request("agent.wait", { runId, timeoutMs: 140000 });
  await delay(150);
  return {
    elapsedMs: Date.now() - startedAt,
    output: outputByRun.get(runId) || "",
    runId,
    status: stringField(waited, "error") || stringField(waited, "status"),
    stopReason: stringField(waited, "stopReason")
  };
}

function recordTurn(id: string, result: TurnResult, outputPattern: RegExp): void {
  evidence.push({
    id,
    result: successful(result.status) && outputPattern.test(result.output) ? "pass" : "fail",
    elapsed_ms: result.elapsedMs,
    detail: turnDetail(result)
  });
}

function turnDetail(result: TurnResult): Record<string, unknown> {
  return {
    run_id_hash: hash(result.runId),
    status: result.status,
    stop_reason: result.stopReason,
    output_excerpt: bounded(result.output.replace(/\s+/g, " ").trim(), 700)
  };
}

function successful(status: string): boolean {
  return ["completed", "ok", "success"].includes(status);
}

function findSession(value: unknown, key: string): Record<string, unknown> {
  const root = asRecord(value);
  const sessions = Array.isArray(root.sessions) ? root.sessions : [];
  return sessions.map(asRecord).find((session) => {
    const candidate = stringField(session, "key") || stringField(session, "sessionKey");
    return candidate === key || candidate === `agent:${agentId}:${key}`;
  }) || {};
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

function recordBoolean(value: unknown, key: string): boolean | null {
  const field = asRecord(value)[key];
  return typeof field === "boolean" ? field : null;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
