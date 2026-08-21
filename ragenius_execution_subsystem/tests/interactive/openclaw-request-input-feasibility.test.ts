import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, it } from "node:test";

import { OpenClawGatewayClient } from "../../src/core/interactive/openclaw-gateway-client.js";
import {
  RequestInputRegistry
} from "../fixtures/openclaw-yield-feasibility/src/request-input-registry.js";

const roots: string[] = [];

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { force: true, recursive: true })));
});

it("runs a disposable live yielded selection through the authenticated Gateway", {
  skip: process.env.OPENCLAW_REQUEST_INPUT_FEASIBILITY_SMOKE !== "1",
  timeout: 180_000
}, async () => {
  const credential = process.env.OPENCLAW_GATEWAY_APPROVAL_TOKEN;
  assert.ok(credential, "Set OPENCLAW_GATEWAY_APPROVAL_TOKEN for the live feasibility test.");
  const client = await new OpenClawGatewayClient({
    credential,
    gatewayUrl: process.env.OPENCLAW_GATEWAY_URL || "ws://127.0.0.1:18789",
    maxMessageBytes: 1_048_576,
    reconnectBaseDelayMs: 250,
    reconnectMaxAttempts: 3,
    rpcTimeoutMs: 130_000,
    scopes: ["operator.admin"]
  }).connect();
  const suffix = `ri-${Date.now().toString(36)}`;
  const baseScope = {
    app_id: "task10",
    execution_id: `execution-${suffix}`,
    session_id: `session-${suffix}`
  };
  let cleanupScope: Record<string, string> | null = null;

  try {
    const started = asRecord(await client.request("ragenius.interaction.start", {
      ...baseScope,
      mode: "selection",
      suffix
    }));
    const bindingNonces = Array.isArray(started.binding_nonces)
      ? started.binding_nonces.filter((value): value is string => typeof value === "string")
      : [];
    assert.equal(bindingNonces.length > 0, true);
    const providerSessionKey = requiredRecordText(started, "provider_session_key");
    const scope = { ...baseScope, provider_session_key: providerSessionKey };
    cleanupScope = scope;
    const pending = await waitForPendingRequest(client, scope);
    const requestRecord = asRecord(pending.request);
    const requestId = requiredRecordText(requestRecord, "request_id");
    const bindingNonce = bindingNonces.find((value) => (
      sha256(value) === requiredRecordText(requestRecord, "binding_nonce_hash")
    ));
    assert.ok(bindingNonce, "The request must consume one start-time binding nonce.");
    const identity = {
      ...scope,
      binding_nonce: bindingNonce,
      provider_run_id: requiredRecordText(requestRecord, "provider_run_id"),
      request_id: requestId,
      tool_call_id: requiredRecordText(requestRecord, "tool_call_id")
    };
    const response = { kind: "selection", option_ids: ["alpha"] };
    const applied = asRecord(await client.request("ragenius.interaction.resolve", {
      ...identity,
      idempotency_key: "task10-response-1",
      response
    }));
    assert.equal(applied.outcome, "applied");
    assert.ok(requiredRecordText(applied, "continuation_run_id"));
    assert.equal(asRecord(await client.request("ragenius.interaction.resolve", {
      ...identity,
      idempotency_key: "task10-response-1",
      response
    })).outcome, "replay");
    assert.equal(asRecord(await client.request("ragenius.interaction.resolve", {
      ...identity,
      idempotency_key: "task10-response-2",
      response: { kind: "selection", option_ids: ["beta"] }
    })).outcome, "conflict");
    const completed = asRecord(await client.request("ragenius.interaction.wait", {
      runId: requiredRecordText(applied, "continuation_run_id"),
      timeoutMs: 120_000
    }));
    assert.ok(["completed", "ok", "success"].includes(requiredRecordText(completed, "status")));
    const transcript = JSON.stringify(await client.request("ragenius.interaction.messages", scope));
    assert.match(transcript, /alpha/i);
    assert.equal(asRecord(await client.request("ragenius.interaction.clear", scope)).removed, 1);
  } finally {
    if (cleanupScope) {
      await client.request("ragenius.interaction.clear", cleanupScope).catch(() => undefined);
    }
    await client.close();
  }
});

describe("disposable OpenClaw request-input protocol", () => {
  it("persists a bounded typed request from trusted runtime identity", async () => {
    const test = await registry();
    test.registry.bindSession(scope("execution-a", "session-a", "provider-session-a"));

    const created = await test.registry.create({
      allows_free_text: false,
      options: [
        { id: "alpha", label: "Alpha" },
        { id: "beta", label: "Beta", description: "Second choice" }
      ],
      question: "Choose one option.",
      trusted: trusted("provider-session-a", "run-a", "tool-a")
    });

    assert.equal(created.request.secret_input, false);
    assert.equal(created.request.plugin_protocol_version, "1");
    assert.equal(created.request.provider_run_id, "run-a");
    assert.equal(created.request.tool_call_id, "tool-a");
    assert.equal(created.request.execution_id, "execution-a");
    assert.equal(created.request.binding_nonce_hash.length, 64);
    assert.equal(created.binding_nonce.length >= 32, true);
    assert.equal(test.registry.getBindingNonce(created.request.request_id), created.binding_nonce);
    const persisted = JSON.parse(await readFile(test.statePath, "utf8"));
    assert.equal(JSON.stringify(persisted).includes(created.binding_nonce), false);
    assert.equal(persisted.requests[0].request.question, "Choose one option.");
  });

  it("maps an OpenClaw runtime session alias to the canonical RAGenius scope", async () => {
    const test = await registry();
    const agentRuntime = new RequestInputRegistry({ statePath: test.statePath });
    await agentRuntime.initialize();
    const canonical = scope("execution-a", "session-a", "provider-session-a");
    test.registry.bindSession(canonical);
    test.registry.bindTrustedSessionKey("agent:main:provider-session-a", canonical);
    const nonces = test.registry.prepareBindingNonces([
      canonical.provider_session_key,
      "agent:main:provider-session-a"
    ], 2);
    await test.registry.persistBindings();

    const created = await request(
      agentRuntime,
      "agent:main:provider-session-a",
      "run-a",
      "tool-a"
    );

    assert.equal(created.request.provider_session_key, canonical.provider_session_key);
    assert.equal(created.request.execution_id, canonical.execution_id);
    assert.equal(created.binding_nonce, "");
    const firstNonce = nonces[0];
    assert.ok(firstNonce);
    assert.equal(created.request.binding_nonce_hash, sha256(firstNonce));
    assert.equal((await readFile(test.statePath, "utf8")).includes(firstNonce), false);
  });

  it("resolves once, replays one idempotency key, and rejects another", async () => {
    const test = await registry();
    test.registry.bindSession(scope("execution-a", "session-a", "provider-session-a"));
    const created = await request(test.registry, "provider-session-a", "run-a", "tool-a");
    const identity = resolutionIdentity(created, scope("execution-a", "session-a", "provider-session-a"));

    const prepared = await test.registry.resolve({
      ...identity,
      idempotency_key: "response-1",
      response: { kind: "selection", option_ids: ["alpha"] }
    });
    const retryBeforeContinuation = await test.registry.resolve({
      ...identity,
      idempotency_key: "response-1",
      response: { kind: "selection", option_ids: ["alpha"] }
    });
    const applied = await test.registry.completeContinuation(
      created.request.request_id,
      "response-1",
      "continuation-run-a"
    );
    const replay = await test.registry.resolve({
      ...identity,
      idempotency_key: "response-1",
      response: { kind: "selection", option_ids: ["alpha"] }
    });
    const conflict = await test.registry.resolve({
      ...identity,
      idempotency_key: "response-2",
      response: { kind: "selection", option_ids: ["beta"] }
    });

    assert.equal(prepared.outcome, "continuation_required");
    assert.deepEqual(prepared.response, { kind: "selection", option_ids: ["alpha"] });
    assert.equal(retryBeforeContinuation.outcome, "continuation_required");
    assert.equal(applied.outcome, "applied");
    assert.equal(replay.outcome, "replay");
    assert.equal(replay.continuation_run_id, "continuation-run-a");
    assert.equal(conflict.outcome, "conflict");
  });

  it("accepts bounded non-secret clarification text exactly once", async () => {
    const test = await registry();
    const bound = scope("execution-a", "session-a", "provider-session-a");
    test.registry.bindSession(bound);
    const created = await test.registry.create({
      allows_free_text: true,
      question: "Name one color.",
      trusted: trusted(bound.provider_session_key, "run-a", "tool-a")
    });
    const result = await test.registry.resolve({
      ...resolutionIdentity(created, bound),
      idempotency_key: "clarification-1",
      response: { kind: "clarification", text: "  blue  " }
    });

    assert.equal(result.outcome, "continuation_required");
    assert.deepEqual(result.response, {
      kind: "clarification",
      text: "blue"
    });
    assert.equal((await test.registry.completeContinuation(
      created.request.request_id,
      "clarification-1",
      "continuation-run-clarification"
    )).outcome, "applied");
  });

  it("fails closed for wrong scope, run, tool call, or binding nonce", async () => {
    const test = await registry();
    const bound = scope("execution-a", "session-a", "provider-session-a");
    test.registry.bindSession(bound);
    const created = await request(test.registry, bound.provider_session_key, "run-a", "tool-a");
    const identity = resolutionIdentity(created, bound);

    for (const mismatch of [
      { ...identity, app_id: "app-other" },
      { ...identity, session_id: "session-other" },
      { ...identity, provider_run_id: "run-other" },
      { ...identity, tool_call_id: "tool-other" },
      { ...identity, binding_nonce: "wrong-nonce" }
    ]) {
      const result = await test.registry.resolve({
        ...mismatch,
        idempotency_key: `mismatch-${Math.random()}`,
        response: { kind: "selection", option_ids: ["alpha"] }
      });
      assert.equal(result.outcome, "not_found");
    }
    assert.equal(test.registry.get(created.request.request_id)?.state, "pending");
  });

  it("expires and cancels without accepting a late response", async () => {
    let now = 1_000;
    const test = await registry(() => now);
    const bound = scope("execution-a", "session-a", "provider-session-a");
    test.registry.bindSession(bound);
    const expired = await request(test.registry, bound.provider_session_key, "run-a", "tool-a", 50);
    now = 1_051;
    assert.equal((await test.registry.expire()).expired, 1);
    assert.equal((await resolve(test.registry, expired, bound, "late-expired")).outcome, "expired");

    const cancelled = await request(test.registry, bound.provider_session_key, "run-b", "tool-b", 100);
    assert.equal((await test.registry.cancel({
      ...resolutionIdentity(cancelled, bound),
      reason: "run_cancelled"
    })).outcome, "cancelled");
    assert.equal((await resolve(test.registry, cancelled, bound, "late-cancelled")).outcome, "cancelled");
  });

  it("marks pending requests interrupted on restart and never restores a nonce", async () => {
    const test = await registry();
    const bound = scope("execution-a", "session-a", "provider-session-a");
    test.registry.bindSession(bound);
    const created = await request(test.registry, bound.provider_session_key, "run-a", "tool-a");
    const continuationPending = await request(
      test.registry,
      bound.provider_session_key,
      "run-b",
      "tool-b"
    );
    assert.equal((await test.registry.resolve({
      ...resolutionIdentity(continuationPending, bound),
      idempotency_key: "before-restart",
      response: { kind: "selection", option_ids: ["alpha"] }
    })).outcome, "continuation_required");

    const restarted = new RequestInputRegistry({
      now: () => 2_000,
      processId: 999_999,
      statePath: test.statePath
    });
    await restarted.initialize();

    assert.equal(restarted.get(created.request.request_id)?.state, "interrupted");
    assert.equal(restarted.get(continuationPending.request.request_id)?.state, "interrupted");
    assert.equal(restarted.getBindingNonce(created.request.request_id), null);
    assert.equal((await resolve(restarted, created, bound, "after-restart")).outcome, "interrupted");
  });

  it("isolates concurrent sessions and supports repeated requests", async () => {
    const test = await registry();
    const left = scope("execution-left", "session-left", "provider-left");
    const right = scope("execution-right", "session-right", "provider-right");
    test.registry.bindSession(left);
    test.registry.bindSession(right);
    const [leftFirst, rightFirst] = await Promise.all([
      request(test.registry, left.provider_session_key, "run-left-1", "tool-left-1"),
      request(test.registry, right.provider_session_key, "run-right-1", "tool-right-1")
    ]);

    assert.equal((await resolve(test.registry, leftFirst, left, "left-1")).outcome, "applied");
    assert.equal(test.registry.get(rightFirst.request.request_id)?.state, "pending");
    assert.equal((await resolve(test.registry, rightFirst, right, "right-1")).outcome, "applied");
    const leftSecond = await request(
      test.registry, left.provider_session_key, "run-left-2", "tool-left-2"
    );
    assert.notEqual(leftFirst.request.request_id, leftSecond.request.request_id);
    assert.equal((await resolve(test.registry, leftSecond, left, "left-2")).outcome, "applied");
  });

  it("lists only exact-scope requests and removes disposable state", async () => {
    const test = await registry();
    const left = scope("execution-left", "session-left", "provider-left");
    const right = scope("execution-right", "session-right", "provider-right");
    test.registry.bindSession(left);
    test.registry.bindSession(right);
    const leftRequest = await request(test.registry, left.provider_session_key, "run-left", "tool-left");
    await request(test.registry, right.provider_session_key, "run-right", "tool-right");

    assert.deepEqual(
      test.registry.list(left).map((record) => record.request.request_id),
      [leftRequest.request.request_id]
    );
    assert.equal(JSON.stringify(test.registry.list(left)).includes(leftRequest.binding_nonce), false);
    assert.equal(await test.registry.clear(left), 1);
    assert.deepEqual(test.registry.list(left), []);
    assert.equal(test.registry.list(right).length, 1);
    const refreshed = new RequestInputRegistry({ statePath: test.statePath });
    await refreshed.initialize();
    assert.equal(await refreshed.isTrustedSessionBound(left.provider_session_key), false);
    assert.equal(await refreshed.isTrustedSessionBound(right.provider_session_key), true);
  });

  it("persists removal when clearing a binding with no requests", async () => {
    const test = await registry();
    const empty = scope("execution-empty", "session-empty", "provider-empty");
    test.registry.bindSession(empty);
    await test.registry.persistBindings();

    assert.equal(await test.registry.clear(empty), 0);
    const refreshed = new RequestInputRegistry({ statePath: test.statePath });
    await refreshed.initialize();
    assert.equal(await refreshed.isTrustedSessionBound(empty.provider_session_key), false);
  });

  it("rejects secrets, authorization requests, malformed choices, and resource overflow", async () => {
    const test = await registry();
    test.registry.bindSession(scope("execution-a", "session-a", "provider-session-a"));
    const base = { trusted: trusted("provider-session-a", "run-a", "tool-a") };

    await assert.rejects(
      test.registry.create({ ...base, question: "Enter your password", allows_free_text: true }),
      /secret input/
    );
    await assert.rejects(
      test.registry.create({
        ...base,
        question: "Approve publishing this video?",
        options: [{ id: "approve", label: "Approve" }],
        allows_free_text: false
      }),
      /authorization/
    );
    await assert.rejects(
      test.registry.create({
        ...base,
        question: "Choose",
        options: [{ id: "same", label: "One" }, { id: "same", label: "Two" }],
        allows_free_text: false
      }),
      /unique/
    );
    await assert.rejects(
      test.registry.create({ ...base, question: "x".repeat(2001), allows_free_text: true }),
      /question/
    );

    const bounded = await registry(undefined, 1);
    bounded.registry.bindSession(scope("execution-a", "session-a", "provider-session-a"));
    await request(bounded.registry, "provider-session-a", "run-a", "tool-a");
    await assert.rejects(
      request(bounded.registry, "provider-session-a", "run-b", "tool-b"),
      /pending request limit/
    );
  });
});

async function registry(now: (() => number) = () => 1_000, maxPending = 10) {
  const root = await mkdtemp(join(tmpdir(), "ragenius-request-input-"));
  roots.push(root);
  const statePath = join(root, "state.json");
  const instance = new RequestInputRegistry({ maxPending, now, statePath });
  await instance.initialize();
  return { registry: instance, statePath };
}

function scope(executionId: string, sessionId: string, providerSessionKey: string) {
  return {
    app_id: "app-a",
    execution_id: executionId,
    session_id: sessionId,
    provider_session_key: providerSessionKey
  };
}

function trusted(providerSessionKey: string, providerRunId: string, toolCallId: string) {
  return {
    agent_id: "main",
    provider_session_key: providerSessionKey,
    provider_run_id: providerRunId,
    tool_call_id: toolCallId
  };
}

async function request(
  registry: RequestInputRegistry,
  providerSessionKey: string,
  providerRunId: string,
  toolCallId: string,
  ttlMs = 1_000
) {
  return registry.create({
    allows_free_text: false,
    options: [{ id: "alpha", label: "Alpha" }, { id: "beta", label: "Beta" }],
    question: "Choose one.",
    trusted: trusted(providerSessionKey, providerRunId, toolCallId),
    ttl_ms: ttlMs
  });
}

function resolutionIdentity(
  created: Awaited<ReturnType<typeof request>>,
  bound: ReturnType<typeof scope>
) {
  return {
    ...bound,
    binding_nonce: created.binding_nonce,
    provider_run_id: created.request.provider_run_id,
    request_id: created.request.request_id,
    tool_call_id: created.request.tool_call_id
  };
}

async function resolve(
  registry: RequestInputRegistry,
  created: Awaited<ReturnType<typeof request>>,
  bound: ReturnType<typeof scope>,
  idempotencyKey: string
) {
  const result = await registry.resolve({
    ...resolutionIdentity(created, bound),
    idempotency_key: idempotencyKey,
    response: { kind: "selection", option_ids: ["alpha"] }
  });
  if (result.outcome !== "continuation_required") return result;
  return registry.completeContinuation(
    created.request.request_id,
    idempotencyKey,
    `continuation-${idempotencyKey}`
  );
}

async function waitForPendingRequest(
  client: OpenClawGatewayClient,
  scopeValue: Record<string, string>
): Promise<Record<string, unknown>> {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    const response = asRecord(await client.request("ragenius.interaction.get", scopeValue));
    const requests = Array.isArray(response.requests) ? response.requests : [];
    const pending = requests.map(asRecord).find((value) => value.state === "pending");
    if (pending) return pending;
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 250));
  }
  throw new Error("Timed out waiting for the disposable request-input record.");
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function requiredRecordText(value: Record<string, unknown>, key: string): string {
  const field = value[key];
  if (typeof field !== "string") throw new Error(`${key} must be returned as text.`);
  assert.ok(field.length > 0, `${key} must not be empty.`);
  return field;
}

function sha256(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}
