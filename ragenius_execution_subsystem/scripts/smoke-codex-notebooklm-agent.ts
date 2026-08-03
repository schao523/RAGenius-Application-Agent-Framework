import assert from "node:assert/strict";
import type { AddressInfo } from "node:net";

import { buildApp } from "../src/app.js";
import { getEnv } from "../src/config/env.js";
import { buildRuntimeConfig } from "../src/config/runtime-config.js";

type JsonRecord = Record<string, unknown>;
let embeddedApiBase: string | undefined;

function requiredEnv(name: string): string {
  const value = String(process.env[name] ?? "").trim();
  if (!value) {
    throw new Error(`${name} is required for the real Codex NotebookLM smoke test.`);
  }
  return value;
}

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
  const payload = await response.json() as JsonRecord;
  return { status: response.status, body: payload };
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
  if (process.env.CODEX_NOTEBOOKLM_REAL_SMOKE !== "1") {
    console.log("Skipped real Codex NotebookLM smoke test; set CODEX_NOTEBOOKLM_REAL_SMOKE=1 to enable it.");
    return;
  }

  const appId = requiredEnv("RAGENIUS_SMOKE_APP_ID");
  const sessionId = requiredEnv("RAGENIUS_SMOKE_SESSION_ID");
  const artifactId = requiredEnv("RAGENIUS_SMOKE_ARTIFACT_ID");
  const notebookTitle = String(
    process.env.RAGENIUS_SMOKE_NOTEBOOK_TITLE ?? "Testing"
  ).trim();
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
  const submission = await jsonRequest("POST", "/executions", {
    request_type: "execute_agent",
    app_id: appId,
    session_id: sessionId,
    agent_backend: "codex_cli",
    agent_skill_hint: "notebooklm",
    agent_query:
      `Use notebooklm. Add the selected artifact as a source to the ${notebookTitle} notebook, then create a study report answering all questions in that notebook.`,
    execution_options: { mode: "async" },
    artifact_refs: [{
      artifact_id: artifactId,
      role: "source",
      reuse_mode: "file_backed"
    }]
  });
  assert.equal(submission.status, 202);
  assert.equal(submission.body.status, "pending_confirmation");
  const executionId = String(submission.body.execution_id ?? "").trim();
  const confirmationId = String(resultOf(submission.body).confirmation_id ?? "").trim();
  assert.ok(executionId);
  assert.ok(confirmationId);

  const scope = `app_id=${encodeURIComponent(appId)}&session_id=${encodeURIComponent(sessionId)}`;
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

  const observed = await pollExecution(
    executionId,
    scope,
    [String(confirmed.body.status ?? "")]
  );
  if (observed.terminal.status !== "completed") {
    const failedResult = resultOf(observed.terminal);
    const diagnostics = resultOf({ result: failedResult.diagnostics });
    console.error(JSON.stringify({
      codex_notebooklm_failure: {
        errors: observed.terminal.errors,
        execution_id: executionId,
        logs_summary: observed.terminal.logs_summary,
        operation_verification: arrayOf(failedResult, "operation_verification"),
        primary_failure: {
          code: diagnostics.failure_code,
          message: diagnostics.failure_message
        },
        provider_status: failedResult.status,
        summary: failedResult.summary
      }
    }, null, 2));
  }
  assert.equal(observed.terminal.status, "completed");
  assert.ok(observed.statuses.includes("queued"));
  assert.ok(observed.statuses.includes("running"));
  const result = resultOf(observed.terminal);
  const metadata = resultOf({ result: result.provider_metadata });
  const stagedInputs = arrayOf(result, "staged_inputs");
  const operations = arrayOf(result, "operation_verification");
  assert.equal(metadata.confirmation_state, "confirmed");
  assert.equal(stagedInputs.length, 1);
  assert.match(String(stagedInputs[0]?.workspace_relative_path ?? ""), /^inputs\//);

  const source = operations.find(
    (operation) => operation.operation_id === "notebooklm_source_add"
  );
  const report = operations.find(
    (operation) => operation.operation_id === "notebooklm_report_generate"
  );
  assert.equal(source?.level, "independently_verified");
  assert.ok(String(source?.external_id ?? "").trim());
  assert.ok(String(report?.external_id ?? "").trim());
  assert.ok(["accepted", "processing", "completed"].includes(String(report?.status ?? "")));
  const inventory = await assertInventoryBackedArtifacts(result, scope);

  const duplicate = await jsonRequest(
    "POST",
    `/executions/${encodeURIComponent(executionId)}/confirm?${scope}`,
    { confirmation_id: confirmationId }
  );
  assert.equal(duplicate.status, 200);
  assert.equal(duplicate.body.execution_id, executionId);
  assert.deepEqual(
    arrayOf(resultOf(duplicate.body), "operation_verification"),
    operations
  );

  console.log(JSON.stringify({
    execution_id: executionId,
    status: observed.terminal.status,
    observed_statuses: observed.statuses,
    confirmation_state: metadata.confirmation_state,
    staged_inputs: stagedInputs.map((item) => ({
      artifact_id: item.artifact_id,
      workspace_relative_path: item.workspace_relative_path,
      sha256: item.sha256
    })),
    operation_verification: operations,
    duplicate_confirmation_status: duplicate.body.status,
    persisted_artifact_ids: arrayOf(result, "artifacts").map((item) => item.artifact_id),
    scoped_inventory_count: inventory.length
  }, null, 2));
  } finally {
    await embeddedApp?.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
