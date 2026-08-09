import assert from "node:assert/strict";

type JsonObject = Record<string, unknown>;

const baseUrl = String(
  process.env.AGENT_SKILL_SMOKE_BASE_URL ?? "http://127.0.0.1:3001/v1"
).replace(/\/$/, "");
const appId = required("AGENT_SKILL_SMOKE_APP_ID");
const sessionId = required("AGENT_SKILL_SMOKE_SESSION_ID");
const backend = required("AGENT_SKILL_SMOKE_BACKEND");
const agentSkillId = required("AGENT_SKILL_SMOKE_ID");
const approvedFingerprint = required("AGENT_SKILL_SMOKE_FINGERPRINT");
const query = required("AGENT_SKILL_SMOKE_QUERY");
const token = String(process.env.AGENT_SKILL_SMOKE_SERVICE_TOKEN ?? "").trim();
const autoConfirm = process.env.AGENT_SKILL_SMOKE_AUTO_CONFIRM === "true";
const timeoutMs = Number(process.env.AGENT_SKILL_SMOKE_TIMEOUT_MS ?? 300000);
const pollMs = Number(process.env.AGENT_SKILL_SMOKE_POLL_MS ?? 1000);

assert.ok(["codex_cli", "openclaw_cli"].includes(backend), "Unsupported smoke backend.");
assert.ok(Number.isFinite(timeoutMs) && timeoutMs > 0, "Smoke timeout must be positive.");

function required(name: string): string {
  const value = String(process.env[name] ?? "").trim();
  assert.ok(value, `Set ${name}.`);
  return value;
}

function headers(): Record<string, string> {
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {})
  };
}

async function requestJson(pathname: string, init?: RequestInit): Promise<JsonObject> {
  const response = await fetch(`${baseUrl}${pathname}`, {
    ...init,
    headers: { ...headers(), ...(init?.headers ?? {}) }
  });
  const text = await response.text();
  const body = text ? JSON.parse(text) as JsonObject : {};
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}: ${JSON.stringify(body)}`);
  }
  return body;
}

function scopeQuery(): string {
  return new URLSearchParams({ app_id: appId, session_id: sessionId }).toString();
}

async function waitForTerminal(executionId: string): Promise<JsonObject> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const result = await requestJson(`/executions/${encodeURIComponent(executionId)}?${scopeQuery()}`);
    const status = String(result.status ?? "").toLowerCase();
    if (!["pending_confirmation", "queued", "running"].includes(status)) {
      return result;
    }
    await new Promise((resolve) => setTimeout(resolve, pollMs));
  }
  throw new Error(`Execution ${executionId} did not reach terminal status within ${timeoutMs} ms.`);
}

async function main(): Promise<void> {
  const inventoryQuery = new URLSearchParams({ app_id: appId, backend }).toString();
  const inventory = await requestJson(`/agent-skills/inventory?${inventoryQuery}`);
  assert.equal(inventory.projection_status, "active", "Agent Skill projection is not active.");
  const inventoryItems = Array.isArray(inventory.items) ? inventory.items as JsonObject[] : [];
  const selected = inventoryItems.find((item) => item.agent_skill_id === agentSkillId);
  assert.ok(selected, `Agent Skill ${agentSkillId} is not bound to ${appId}/${backend}.`);
  assert.equal(
    selected.approved_fingerprint,
    approvedFingerprint,
    "Configured smoke fingerprint does not match active projection."
  );

  let execution = await requestJson("/executions", {
    method: "POST",
    body: JSON.stringify({
      request_type: "execute_agent",
      app_id: appId,
      session_id: sessionId,
      agent_backend: backend,
      agent_query: query,
      agent_skill_ref: {
        agent_skill_id: agentSkillId,
        approved_fingerprint: approvedFingerprint
      },
      execution_options: { mode: "async" },
      context: { execution_mode: "async" }
    })
  });

  const executionId = String(execution.execution_id ?? "").trim();
  assert.ok(executionId, "Execution submission did not return execution_id.");
  if (execution.status === "pending_confirmation") {
    assert.ok(autoConfirm, "Execution requires confirmation; set AGENT_SKILL_SMOKE_AUTO_CONFIRM=true to continue.");
    const result = execution.result && typeof execution.result === "object"
      ? execution.result as JsonObject
      : {};
    const confirmationId = String(result.confirmation_id ?? "").trim();
    assert.ok(confirmationId, "Pending execution did not return confirmation_id.");
    execution = await requestJson(`/executions/${encodeURIComponent(executionId)}/confirm?${scopeQuery()}`, {
      method: "POST",
      body: JSON.stringify({ confirmation_id: confirmationId })
    });
  }

  const terminal = ["queued", "running", "pending_confirmation"].includes(String(execution.status ?? ""))
    ? await waitForTerminal(executionId)
    : execution;
  assert.equal(terminal.status, "completed", JSON.stringify(terminal));
  const result = terminal.result && typeof terminal.result === "object"
    ? terminal.result as JsonObject
    : {};
  console.log(JSON.stringify({
    app_id: appId,
    session_id: sessionId,
    backend,
    inventory_revision: inventory.inventory_revision,
    selected_agent_skill_id: agentSkillId,
    approved_fingerprint: approvedFingerprint,
    execution_id: executionId,
    status: terminal.status,
    agent_skill_activation: result.agent_skill_activation ?? null,
    provider_status: result.status ?? null
  }, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
