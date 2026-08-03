import assert from "node:assert/strict";
import type { AddressInfo } from "node:net";

import { buildApp } from "../src/app.js";
import { getEnv } from "../src/config/env.js";
import { buildRuntimeConfig } from "../src/config/runtime-config.js";

type JsonRecord = Record<string, unknown>;
let embeddedApiBase: string | undefined;

function apiBase(): string {
  if (embeddedApiBase) {
    return embeddedApiBase;
  }
  const base = String(
    process.env.RAGENIUS_EXECUTION_BASE_URL ?? "http://127.0.0.1:3001"
  ).replace(/\/+$/, "");
  return base.endsWith("/v1") ? base : `${base}/v1`;
}

async function jsonRequest(
  method: string,
  path: string,
  body?: JsonRecord
): Promise<{ status: number; body: JsonRecord }> {
  const token = String(process.env.RAGENIUS_EXECUTION_SERVICE_TOKEN ?? "").trim();
  const response = await fetch(`${apiBase()}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    ...(body ? { body: JSON.stringify(body) } : {})
  });
  return { status: response.status, body: await response.json() as JsonRecord };
}

function resultOf(payload: JsonRecord): JsonRecord {
  return payload.result && typeof payload.result === "object"
    ? payload.result as JsonRecord
    : {};
}

function arrayOf(payload: JsonRecord, key: string): JsonRecord[] {
  return Array.isArray(payload[key])
    ? (payload[key] as unknown[]).filter(
        (item): item is JsonRecord => Boolean(item) && typeof item === "object"
      )
    : [];
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function pollExecution(
  executionId: string,
  scope: string,
  initialStatuses: string[] = []
): Promise<{ terminal: JsonRecord; statuses: string[] }> {
  const timeoutMs = Number(process.env.RAGENIUS_SMOKE_POLL_TIMEOUT_MS ?? 300_000);
  const deadline = Date.now() + timeoutMs;
  const statuses = [...initialStatuses];
  while (Date.now() < deadline) {
    const response = await jsonRequest(
      "GET",
      `/executions/${encodeURIComponent(executionId)}?${scope}`
    );
    assert.equal(response.status, 200);
    const status = String(response.body.status ?? "");
    if (statuses.at(-1) !== status) {
      statuses.push(status);
    }
    if (["completed", "failed"].includes(status)) {
      return { terminal: response.body, statuses };
    }
    await sleep(100);
  }
  throw new Error(`Execution ${executionId} did not reach a terminal state.`);
}

async function assertInventoryBackedArtifacts(
  result: JsonRecord,
  scope: string
): Promise<JsonRecord[]> {
  const inventory = await jsonRequest("GET", `/artifacts?${scope}&status=ready`);
  assert.equal(inventory.status, 200);
  const items = arrayOf(inventory.body, "items");
  const inventoryIds = new Set(items.map((item) => String(item.artifact_id ?? "")));
  for (const artifact of arrayOf(result, "artifacts")) {
    const artifactId = String(artifact.artifact_id ?? "");
    assert.ok(artifactId && inventoryIds.has(artifactId));
    assert.equal("path" in artifact, false);
    assert.equal("file_path" in artifact, false);
  }
  return items;
}

async function main(): Promise<void> {
  if (process.env.OPENCLAW_REAL_SMOKE !== "1") {
    console.log("Skipped real OpenClaw smoke test; set OPENCLAW_REAL_SMOKE=1 to enable it.");
    return;
  }

  const embeddedApp =
    process.env.RAGENIUS_SMOKE_EMBEDDED_SERVICE === "1"
      ? buildApp({}, buildRuntimeConfig(getEnv()))
      : undefined;
  if (embeddedApp) {
    await embeddedApp.listen({ host: "127.0.0.1", port: 0 });
    const address = embeddedApp.server.address() as AddressInfo;
    embeddedApiBase = `http://127.0.0.1:${address.port}/v1`;
  }

  try {
  const appId = String(process.env.RAGENIUS_SMOKE_APP_ID ?? "smoke_app").trim();
  const sessionId = String(
    process.env.RAGENIUS_SMOKE_SESSION_ID ?? `openclaw-smoke-${Date.now()}`
  ).trim();
  const scope = `app_id=${encodeURIComponent(appId)}&session_id=${encodeURIComponent(sessionId)}`;

  const readSubmission = await jsonRequest("POST", "/executions", {
    request_type: "execute_agent",
    app_id: appId,
    session_id: sessionId,
    agent_backend: "openclaw_cli",
    agent_query: "Reply with exactly: OK.",
    execution_options: { mode: "async" }
  });
  assert.equal(readSubmission.status, 202);
  assert.equal(readSubmission.body.status, "queued");
  const readExecutionId = String(readSubmission.body.execution_id ?? "");
  assert.ok(readExecutionId);
  const readObserved = await pollExecution(
    readExecutionId,
    scope,
    [String(readSubmission.body.status ?? "")]
  );
  assert.equal(readObserved.terminal.status, "completed");
  assert.ok(readObserved.statuses.includes("queued"));
  assert.ok(readObserved.statuses.includes("running"));
  const readResult = resultOf(readObserved.terminal);
  const readOutput = String(readResult.output_text ?? "").trim();
  if (!/(?:^|\n)OK\.?(?:\n|$)/.test(readOutput)) {
    console.error(JSON.stringify({
      read_only_diagnostic: {
        errors: readObserved.terminal.errors,
        logs_summary: readObserved.terminal.logs_summary,
        result_keys: Object.keys(readResult).sort(),
        status: readObserved.terminal.status,
        summary: readResult.summary
      }
    }, null, 2));
  }
  assert.match(readOutput, /(?:^|\n)OK\.?(?:\n|$)/);

  const outputRequest: JsonRecord = {
    request_type: "execute_agent",
    app_id: appId,
    session_id: sessionId,
    agent_backend: "openclaw_cli",
    agent_query: "Create the required markdown file containing exactly: # OpenClaw Smoke Test",
    execution_options: { mode: "async" },
    expected_outputs: [{
      output_id: "smoke_markdown",
      display_name: "openclaw-smoke.md",
      media_type: "text/markdown",
      required: true,
      persist_as_artifact: true,
      artifact_type: "agent_output",
      min_size_bytes: 1
    }]
  };
  const pending = await jsonRequest("POST", "/executions", outputRequest);
  assert.equal(pending.status, 202);
  assert.equal(pending.body.status, "pending_confirmation");
  const executionId = String(pending.body.execution_id ?? "");
  const confirmationId = String(resultOf(pending.body).confirmation_id ?? "");
  assert.ok(executionId);
  assert.ok(confirmationId);

  const confirmed = await jsonRequest(
    "POST",
    `/executions/${encodeURIComponent(executionId)}/confirm?${scope}`,
    { confirmation_id: confirmationId }
  );
  assert.equal(confirmed.status, 202);
  assert.equal(confirmed.body.status, "queued");
  const duplicateWhileActive = await jsonRequest(
    "POST",
    `/executions/${encodeURIComponent(executionId)}/confirm?${scope}`,
    { confirmation_id: confirmationId }
  );
  assert.ok([200, 202].includes(duplicateWhileActive.status));
  assert.equal(duplicateWhileActive.body.execution_id, executionId);

  const outputObserved = await pollExecution(
    executionId,
    scope,
    [String(confirmed.body.status ?? "")]
  );
  assert.equal(outputObserved.terminal.status, "completed");
  assert.ok(outputObserved.statuses.includes("queued"));
  assert.ok(outputObserved.statuses.includes("running"));
  const result = resultOf(outputObserved.terminal);
  const verification = arrayOf(result, "verification_results")[0];
  assert.equal(verification?.verified, true);
  assert.equal(verification?.persistence_status, "persisted");
  const inventory = await assertInventoryBackedArtifacts(result, scope);

  const duplicateTerminal = await jsonRequest(
    "POST",
    `/executions/${encodeURIComponent(executionId)}/confirm?${scope}`,
    { confirmation_id: confirmationId }
  );
  assert.equal(duplicateTerminal.status, 200);
  assert.equal(duplicateTerminal.body.execution_id, executionId);
  assert.deepEqual(
    arrayOf(resultOf(duplicateTerminal.body), "artifacts"),
    arrayOf(result, "artifacts")
  );

  console.log(JSON.stringify({
    read_only: {
      execution_id: readExecutionId,
      status: readObserved.terminal.status,
      observed_statuses: readObserved.statuses
    },
    output_required: {
      execution_id: executionId,
      status: outputObserved.terminal.status,
      observed_statuses: outputObserved.statuses,
      verification: {
        output_id: verification?.output_id,
        verified: verification?.verified,
        persistence_status: verification?.persistence_status
      },
      persisted_artifact_ids: arrayOf(result, "artifacts").map((item) => item.artifact_id),
      scoped_inventory_count: inventory.length,
      duplicate_confirmation_status: duplicateTerminal.body.status
    }
  }, null, 2));
  } finally {
    await embeddedApp?.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
