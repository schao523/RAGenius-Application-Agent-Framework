import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";

import type { FastifyInstance } from "fastify";

import { buildApp } from "../../src/app.js";
import type { AgentProvider } from "../../src/core/agents/agent-provider.js";
import {
  AgentSkillSelectionError,
  type AgentSkillSelectionService
} from "../../src/core/agent-skills/agent-skill-selection-service.js";
import type { ResolvedAgentSkillSelection } from "../../src/core/agent-skills/agent-skill-types.js";
import { ConfirmationService } from "../../src/core/execution/confirmation-service.js";
import { InMemoryConfirmationStore } from "../../src/core/execution/confirmation-store.js";
import { ExecutionEngine } from "../../src/core/execution/execution-engine.js";
import { InMemoryExecutionStore } from "../../src/core/execution/execution-store.js";

function createAgentProvider(onExecute: () => Promise<void>): AgentProvider {
  return {
    backend: "codex_cli",
    async execute() {
      await onExecute();
      return {
        status: "completed",
        summary: "Agent completed.",
        output: { status: "completed" },
        raw_output: "{\"status\":\"completed\"}"
      };
    }
  };
}

describe("single-use confirmation state machine", () => {
  let app: FastifyInstance | undefined;

  afterEach(async () => {
    await app?.close();
    app = undefined;
  });

  it("rejects a public require_confirmation approval flag", async () => {
    app = buildApp();
    const response = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_agent",
        agent_backend: "codex_cli",
        app_id: "app_001",
        session_id: "sess_001",
        agent_query: "Create a draft.",
        execution_options: { require_confirmation: true }
      }
    });

    assert.equal(response.statusCode, 400);
    assert.equal(response.json().error.code, "VALIDATION_ERROR");
  });

  it("claims concurrent confirmations once and returns terminal results idempotently", async () => {
    let providerCalls = 0;
    let releaseProvider: (() => void) | undefined;
    const providerGate = new Promise<void>((resolve) => {
      releaseProvider = resolve;
    });
    const executionStore = new InMemoryExecutionStore();
    const confirmationStore = new InMemoryConfirmationStore();
    const confirmationService = new ConfirmationService(confirmationStore, {
      createId: () => "confirmation_concurrent",
      ttlMs: 60000
    });
    const engine = new ExecutionEngine({
      agentProviders: new Map([
        [
          "codex_cli",
          createAgentProvider(async () => {
            providerCalls += 1;
            await providerGate;
          })
        ]
      ]),
      confirmationService,
      executionStore
    });
    app = buildApp({
      confirmationService,
      confirmationStore,
      executionEngine: engine,
      executionStore
    });

    const pending = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_agent",
        agent_backend: "codex_cli",
        app_id: "app_001",
        session_id: "sess_001",
        agent_query: "Create a draft."
      }
    });
    const executionId = pending.json().execution_id;
    const confirmationId = pending.json().result.confirmation_id;
    const request = {
      method: "POST" as const,
      url: `/v1/executions/${executionId}/confirm?app_id=app_001&session_id=sess_001`,
      payload: { confirmation_id: confirmationId }
    };

    const firstConfirmation = app.inject(request);
    await new Promise((resolve) => setImmediate(resolve));
    const concurrentConfirmation = await app.inject(request);
    assert.equal(concurrentConfirmation.statusCode, 202);
    assert.equal(concurrentConfirmation.json().status, "running");
    assert.equal(providerCalls, 1);

    releaseProvider?.();
    const completed = await firstConfirmation;
    assert.equal(completed.statusCode, 200);
    assert.equal(completed.json().status, "completed");
    assert.equal(providerCalls, 1);

    const repeated = await app.inject(request);
    assert.equal(repeated.statusCode, 200);
    assert.equal(repeated.json().status, "completed");
    assert.equal(providerCalls, 1);
  });

  it("rejects expired confirmation without invoking the provider", async () => {
    let now = new Date("2026-07-24T00:00:00.000Z");
    let providerCalls = 0;
    const executionStore = new InMemoryExecutionStore();
    const confirmationStore = new InMemoryConfirmationStore();
    const confirmationService = new ConfirmationService(confirmationStore, {
      clock: () => now,
      createId: () => "confirmation_expired",
      ttlMs: 1000
    });
    const engine = new ExecutionEngine({
      agentProviders: new Map([
        [
          "codex_cli",
          createAgentProvider(async () => {
            providerCalls += 1;
          })
        ]
      ]),
      confirmationService,
      executionStore
    });
    app = buildApp({
      confirmationService,
      confirmationStore,
      executionEngine: engine,
      executionStore
    });

    const pending = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_agent",
        agent_backend: "codex_cli",
        app_id: "app_001",
        session_id: "sess_001",
        agent_query: "Create a draft."
      }
    });
    now = new Date("2026-07-24T00:00:02.000Z");

    const response = await app.inject({
      method: "POST",
      url: `/v1/executions/${pending.json().execution_id}/confirm?app_id=app_001&session_id=sess_001`,
      payload: {
        confirmation_id: pending.json().result.confirmation_id
      }
    });

    assert.equal(response.statusCode, 409);
    assert.equal(response.json().error.code, "CONFIRMATION_EXPIRED");
    assert.equal(providerCalls, 0);
  });

  it("does not reveal a confirmation through another app or session", async () => {
    const executionStore = new InMemoryExecutionStore();
    const confirmationStore = new InMemoryConfirmationStore();
    const confirmationService = new ConfirmationService(confirmationStore, {
      createId: () => "confirmation_scoped",
      ttlMs: 60000
    });
    const engine = new ExecutionEngine({
      agentProviders: new Map([
        ["codex_cli", createAgentProvider(async () => undefined)]
      ]),
      confirmationService,
      executionStore
    });
    app = buildApp({
      confirmationService,
      confirmationStore,
      executionEngine: engine,
      executionStore
    });
    const pending = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_agent",
        agent_backend: "codex_cli",
        app_id: "app_001",
        session_id: "sess_001",
        agent_query: "Create a draft."
      }
    });

    const wrongScope = await app.inject({
      method: "POST",
      url: `/v1/executions/${pending.json().execution_id}/confirm?app_id=app_001&session_id=sess_002`,
      payload: {
        confirmation_id: pending.json().result.confirmation_id
      }
    });
    const unknown = await app.inject({
      method: "POST",
      url: `/v1/executions/${pending.json().execution_id}/confirm?app_id=app_001&session_id=sess_001`,
      payload: { confirmation_id: "confirmation_unknown" }
    });

    assert.equal(wrongScope.statusCode, 404);
    assert.deepEqual(wrongScope.json(), unknown.json());
  });

  it("invalidates confirmation when the resolved skill fingerprint changes", async () => {
    let providerCalls = 0;
    let observedFingerprint = "sha256:v1:approved";
    const selectionService = {
      async resolve(): Promise<ResolvedAgentSkillSelection> {
        if (observedFingerprint !== "sha256:v1:approved") {
          throw new AgentSkillSelectionError(
            "AGENT_SKILL_FINGERPRINT_CHANGED",
            "Agent skill content changed after approval."
          );
        }
        return {
          activation_method: "codex_explicit_reference",
          agent_skill_id: "agent-skill-1",
          approved_fingerprint: "sha256:v1:approved",
          backend: "codex_cli",
          display_name: "Approved Skill",
          observed_fingerprint: observedFingerprint,
          protected_locator_ref: "protected-source-ref",
          provider_skill_name: "approved-skill",
          provider_skill_reference: "approved-skill",
          resolved_at: new Date().toISOString(),
          runtime_target_id: "codex-local-default",
          source_id: "source-1"
        };
      }
    } as unknown as AgentSkillSelectionService;
    const executionStore = new InMemoryExecutionStore();
    const confirmationStore = new InMemoryConfirmationStore();
    const confirmationService = new ConfirmationService(confirmationStore, {
      createId: () => "confirmation_skill_fingerprint",
      ttlMs: 60000
    });
    const engine = new ExecutionEngine({
      agentProviders: new Map([[
        "codex_cli",
        createAgentProvider(async () => { providerCalls += 1; })
      ]]),
      agentSkillSelectionService: selectionService,
      confirmationService,
      executionStore
    });
    app = buildApp({
      agentSkillSelectionService: selectionService,
      confirmationService,
      confirmationStore,
      executionEngine: engine,
      executionStore
    });

    const pending = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_agent",
        agent_backend: "codex_cli",
        app_id: "app_001",
        session_id: "sess_001",
        agent_query: "Create a draft.",
        agent_skill_ref: {
          agent_skill_id: "agent-skill-1",
          approved_fingerprint: "sha256:v1:approved"
        }
      }
    });
    assert.equal(pending.statusCode, 202);
    observedFingerprint = "sha256:v1:changed";

    const response = await app.inject({
      method: "POST",
      url: `/v1/executions/${pending.json().execution_id}/confirm?app_id=app_001&session_id=sess_001`,
      payload: { confirmation_id: pending.json().result.confirmation_id }
    });

    assert.equal(response.statusCode, 500);
    assert.equal(response.json().error.code, "CONFIRMATION_POLICY_CHANGED");
    assert.equal(providerCalls, 0);
  });
});
