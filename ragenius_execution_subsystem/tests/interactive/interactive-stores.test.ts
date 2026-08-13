import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { InMemoryAgentEventStore } from "../../src/core/interactive/agent-event-store.js";
import { InMemoryAgentInteractionStore } from "../../src/core/interactive/agent-interaction-store.js";
import { InMemoryAgentSessionStore } from "../../src/core/interactive/agent-session-store.js";
import {
  PrismaAgentEventStore,
  type AgentEventPrismaClient
} from "../../src/core/interactive/prisma-agent-event-store.js";
import {
  PrismaAgentInteractionStore,
  type AgentInteractionPrismaClient
} from "../../src/core/interactive/prisma-agent-interaction-store.js";
import {
  PrismaAgentSessionStore,
  type AgentSessionPrismaClient
} from "../../src/core/interactive/prisma-agent-session-store.js";
import type {
  AgentInteractionCapabilities,
  ExecutionScope
} from "../../src/core/interactive/interactive-agent-types.js";

const scope: ExecutionScope = {
  appId: "app_001",
  executionId: "execution_001",
  sessionId: "session_001"
};

const capabilities: AgentInteractionCapabilities = {
  cancellation: true,
  eventReplay: "none",
  interactionTypes: ["approval", "selection"],
  protocolTransport: true,
  reconnectReconciliation: true,
  sameSessionContinuation: true,
  sameTurnResume: false
};

describe("interactive agent stores", () => {
  it("creates one scoped session per execution and updates provider state", async () => {
    const store = new InMemoryAgentSessionStore();
    const created = await store.create({
      ...scope,
      agentSessionId: "agent_session_001",
      backend: "openclaw_cli",
      capabilitySnapshot: capabilities,
      continuationMode: "same_session_new_turn",
      protocolVersion: "2026.6.8",
      providerRunRef: null,
      providerSessionRef: "protected-session-ref",
      providerTurnRef: null,
      state: "starting",
      transport: "openclaw_gateway"
    });

    const duplicate = await store.create({
      ...scope,
      agentSessionId: "agent_session_002",
      backend: "openclaw_cli",
      capabilitySnapshot: capabilities,
      continuationMode: "same_session_new_turn",
      protocolVersion: "2026.6.8",
      providerRunRef: null,
      providerSessionRef: "other-ref",
      providerTurnRef: null,
      state: "starting",
      transport: "openclaw_gateway"
    });

    assert.equal(duplicate.agentSessionId, created.agentSessionId);
    assert.equal(
      await store.getByExecution({ ...scope, appId: "app_other" }),
      null
    );

    const updated = await store.update(
      { ...scope, agentSessionId: created.agentSessionId },
      {
        lastEventSeq: 2,
        providerRunRef: "run_002",
        state: "running"
      }
    );
    assert.equal(updated?.providerRunRef, "run_002");
    assert.equal(updated?.lastEventSeq, 2);

    await assert.rejects(
      store.create({
        ...scope,
        agentSessionId: "agent_session_other_scope",
        appId: "app_other",
        backend: "openclaw_cli",
        capabilitySnapshot: capabilities,
        continuationMode: "same_session_new_turn",
        protocolVersion: "2026.6.8",
        providerRunRef: null,
        providerSessionRef: "other-ref",
        providerTurnRef: null,
        state: "starting",
        transport: "openclaw_gateway"
      }),
      /does not match execution scope/
    );
  });

  it("assigns monotonic interaction sequences and permits multiple interactions", async () => {
    const store = new InMemoryAgentInteractionStore();
    const first = await store.create(interactionInput("interaction_001", "approval"));
    const second = await store.create(interactionInput("interaction_002", "selection"));

    assert.equal(first.sequence, 1);
    assert.equal(second.sequence, 2);
    assert.deepEqual(
      (await store.list(scope)).map((record) => record.interactionId),
      ["interaction_001", "interaction_002"]
    );
    assert.deepEqual(await store.list({ ...scope, sessionId: "other" }), []);
    await assert.rejects(
      store.create({
        ...interactionInput("interaction_001", "approval"),
        appId: "app_other"
      }),
      /does not match execution scope/
    );
  });

  it("claims once by scope and version, then replays the same idempotency key", async () => {
    const store = new InMemoryAgentInteractionStore();
    await store.create(interactionInput("interaction_001", "approval"));
    const input = {
      ...scope,
      expectedVersion: 1,
      idempotencyKey: "response-key-001",
      interactionId: "interaction_001",
      now: new Date("2026-08-13T00:00:10.000Z"),
      responseSummary: { decision: "allow_once", kind: "approval" }
    };

    const [first, second] = await Promise.all([
      store.claim(input),
      store.claim(input)
    ]);
    assert.equal(first.outcome, "claimed");
    assert.equal(second.outcome, "replay");
    assert.equal(first.record.state, "resolving");

    const conflict = await store.claim({
      ...input,
      idempotencyKey: "response-key-002"
    });
    assert.equal(conflict.outcome, "conflict");

    const resolved = await store.resolve({
      ...scope,
      idempotencyKey: input.idempotencyKey,
      interactionId: input.interactionId,
      now: new Date("2026-08-13T00:00:11.000Z"),
      responseSummary: input.responseSummary
    });
    assert.equal(resolved?.state, "resolved");
    assert.equal(resolved?.version, 3);

    const replay = await store.claim(input);
    assert.equal(replay.outcome, "replay");
    assert.equal(replay.record.state, "resolved");
  });

  it("expires pending interactions and cancels remaining scoped records", async () => {
    const store = new InMemoryAgentInteractionStore();
    await store.create(
      interactionInput("interaction_expired", "selection", {
        expiresAt: new Date("2026-08-13T00:00:01.000Z")
      })
    );
    await store.create(interactionInput("interaction_pending", "approval"));

    const expired = await store.claim({
      ...scope,
      expectedVersion: 1,
      idempotencyKey: "expired-key",
      interactionId: "interaction_expired",
      now: new Date("2026-08-13T00:00:02.000Z"),
      responseSummary: { kind: "selection", optionIds: ["alpha"] }
    });
    assert.equal(expired.outcome, "expired");
    assert.equal(expired.record.state, "expired");

    assert.equal(
      await store.cancelPending(scope, new Date("2026-08-13T00:00:03.000Z")),
      1
    );
    const records = await store.list(scope);
    assert.equal(records[1]?.state, "cancelled");
  });

  it("appends monotonic events and deduplicates provider event references", async () => {
    const store = new InMemoryAgentEventStore();
    const first = await store.append({
      ...scope,
      occurredAt: new Date("2026-08-13T00:00:00.000Z"),
      payload: { state: "running" },
      providerEventRef: "run-1:started",
      type: "run_started"
    });
    const duplicate = await store.append({
      ...scope,
      occurredAt: new Date("2026-08-13T00:00:00.500Z"),
      payload: { ignored: true },
      providerEventRef: "run-1:started",
      type: "run_started"
    });
    const second = await store.append({
      ...scope,
      interactionId: "interaction_001",
      occurredAt: new Date("2026-08-13T00:00:01.000Z"),
      payload: { interactionType: "approval" },
      providerEventRef: "approval-1:requested",
      type: "interaction_requested"
    });

    assert.equal(first.sequence, 1);
    assert.equal(duplicate.sequence, 1);
    assert.equal(second.sequence, 2);
    assert.deepEqual(
      (await store.list({ ...scope, afterSequence: 1, limit: 10 })).map(
        (event) => event.sequence
      ),
      [2]
    );
    assert.deepEqual(
      await store.list({
        ...scope,
        afterSequence: 0,
        appId: "app_other",
        limit: 10
      }),
      []
    );
  });

  it("uses an atomic session counter when Prisma creates an interaction", async () => {
    let createData: Record<string, unknown> | undefined;
    const prisma = {
      $transaction: async <T>(callback: (tx: unknown) => Promise<T>) =>
        callback(prisma),
      agentInteraction: {
        async create(args: { data: Record<string, unknown> }) {
          createData = args.data;
          return interactionRow({ sequence: Number(args.data.sequence) });
        }
      },
      agentSession: {
        async findFirst() {
          return { id: "agent_session_001" };
        },
        async update(args: { data: Record<string, unknown> }) {
          assert.deepEqual(args.data, {
            lastInteractionSeq: { increment: 1 }
          });
          return { lastInteractionSeq: 7 };
        }
      }
    } as unknown as AgentInteractionPrismaClient;
    const store = new PrismaAgentInteractionStore(prisma);

    const created = await store.create(interactionInput("interaction_007", "approval"));

    assert.equal(created.sequence, 7);
    assert.equal(createData?.sequence, 7);
    assert.equal(createData?.secretInput, false);
  });

  it("keeps Prisma Agent session lookups fully scoped", async () => {
    let findWhere: Record<string, unknown> | undefined;
    const row = {
      appId: scope.appId,
      backend: "openclaw_cli",
      capabilitySnapshot: capabilities,
      continuationMode: "same_session_new_turn",
      createdAt: new Date("2026-08-13T00:00:00.000Z"),
      executionId: scope.executionId,
      id: "agent_session_001",
      lastEventSeq: 0,
      protocolVersion: "2026.6.8",
      providerRunRef: null,
      providerSessionRef: "protected-session-ref",
      providerTurnRef: null,
      sessionId: scope.sessionId,
      state: "starting",
      transport: "openclaw_gateway",
      updatedAt: new Date("2026-08-13T00:00:00.000Z")
    };
    const prisma = {
      agentSession: {
        async findFirst(args: { where: Record<string, unknown> }) {
          findWhere = args.where;
          return row;
        },
        async updateMany() {
          return { count: 0 };
        },
        async upsert() {
          return row;
        }
      }
    } as unknown as AgentSessionPrismaClient;
    const store = new PrismaAgentSessionStore(prisma);

    const found = await store.getByExecution(scope);

    assert.equal(found?.agentSessionId, "agent_session_001");
    assert.deepEqual(findWhere, scope);
  });

  it("conditionally claims a Prisma interaction by scope, version, and expiry", async () => {
    let updateWhere: Record<string, unknown> | undefined;
    let row = interactionRow();
    const prisma = {
      $transaction: async <T>(callback: (tx: unknown) => Promise<T>) =>
        callback(prisma),
      agentInteraction: {
        async findFirst() {
          return row;
        },
        async updateMany(args: {
          data: Record<string, unknown>;
          where: Record<string, unknown>;
        }) {
          updateWhere = args.where;
          row = {
            ...row,
            ...args.data,
            state: "resolving",
            version: row.version + 1
          };
          return { count: 1 };
        }
      },
      agentSession: {}
    } as unknown as AgentInteractionPrismaClient;
    const store = new PrismaAgentInteractionStore(prisma);
    const now = new Date("2026-08-13T00:00:10.000Z");

    const result = await store.claim({
      ...scope,
      expectedVersion: 1,
      idempotencyKey: "response-key-001",
      interactionId: "interaction_001",
      now,
      responseSummary: { decision: "allow_once", kind: "approval" }
    });

    assert.equal(result.outcome, "claimed");
    assert.equal(updateWhere?.appId, scope.appId);
    assert.equal(updateWhere?.sessionId, scope.sessionId);
    assert.equal(updateWhere?.executionId, scope.executionId);
    assert.equal(updateWhere?.version, 1);
    assert.deepEqual(updateWhere?.expiresAt, { gt: now });
    assert.equal(updateWhere?.state, "pending");
  });

  it("does not resolve a Prisma interaction with another idempotency key", async () => {
    const row = interactionRow({
      idempotencyKey: "original-key",
      state: "resolving",
      version: 2
    });
    const prisma = {
      $transaction: async <T>(callback: (tx: unknown) => Promise<T>) =>
        callback(prisma),
      agentInteraction: {
        async findFirst() {
          return row;
        },
        async updateMany() {
          return { count: 0 };
        }
      },
      agentSession: {}
    } as unknown as AgentInteractionPrismaClient;
    const store = new PrismaAgentInteractionStore(prisma);

    const resolved = await store.resolve({
      ...scope,
      idempotencyKey: "wrong-key",
      interactionId: "interaction_001",
      now: new Date("2026-08-13T00:00:11.000Z"),
      responseSummary: { decision: "allow_once", kind: "approval" }
    });

    assert.equal(resolved, null);
  });

  it("uses an atomic session counter and provider ref dedupe for Prisma events", async () => {
    let createData: Record<string, unknown> | undefined;
    const prisma = {
      $transaction: async <T>(callback: (tx: unknown) => Promise<T>) =>
        callback(prisma),
      agentExecutionEvent: {
        async create(args: { data: Record<string, unknown> }) {
          createData = args.data;
          return eventRow({ sequence: Number(args.data.sequence) });
        },
        async findFirst() {
          return null;
        }
      },
      agentSession: {
        async findFirst() {
          return { id: "agent_session_001" };
        },
        async update(args: { data: Record<string, unknown> }) {
          assert.deepEqual(args.data, { lastEventSeq: { increment: 1 } });
          return { lastEventSeq: 4 };
        }
      }
    } as unknown as AgentEventPrismaClient;
    const store = new PrismaAgentEventStore(prisma);

    const event = await store.append({
      ...scope,
      occurredAt: new Date("2026-08-13T00:00:00.000Z"),
      payload: { state: "running" },
      providerEventRef: "run-1:started",
      type: "run_started"
    });

    assert.equal(event.sequence, 4);
    assert.equal(createData?.sequence, 4);
  });
});

function interactionInput(
  interactionId: string,
  type: "approval" | "selection",
  overrides: { expiresAt?: Date } = {}
) {
  return {
    ...scope,
    agentSessionId: "agent_session_001",
    allowsFreeText: false,
    expiresAt: overrides.expiresAt ?? new Date("2026-08-13T00:01:00.000Z"),
    interactionId,
    options:
      type === "selection"
        ? [{ id: "alpha", label: "Alpha" }]
        : [{ id: "allow_once", label: "Allow once" }],
    policyBindingHash: "binding-hash",
    prompt: "Choose a bounded response.",
    providerCorrelationRef: `provider-${interactionId}`,
    type
  } as const;
}

function interactionRow(overrides: Record<string, unknown> = {}) {
  return {
    agentSessionId: "agent_session_001",
    allowsFreeText: false,
    appId: scope.appId,
    createdAt: new Date("2026-08-13T00:00:00.000Z"),
    executionId: scope.executionId,
    expiresAt: new Date("2026-08-13T00:01:00.000Z"),
    id: "interaction_001",
    idempotencyKey: null,
    options: [{ id: "allow_once", label: "Allow once" }],
    policyBindingHash: "binding-hash",
    prompt: "Choose.",
    providerCorrelationRef: "provider-interaction-001",
    resolvedAt: null,
    responseSummary: null,
    secretInput: false,
    sequence: 1,
    sessionId: scope.sessionId,
    state: "pending",
    type: "approval",
    updatedAt: new Date("2026-08-13T00:00:00.000Z"),
    version: 1,
    ...overrides
  };
}

function eventRow(overrides: Record<string, unknown> = {}) {
  return {
    appId: scope.appId,
    executionId: scope.executionId,
    interactionId: null,
    occurredAt: new Date("2026-08-13T00:00:00.000Z"),
    payload: { state: "running" },
    providerEventRef: "run-1:started",
    sequence: 1,
    sessionId: scope.sessionId,
    type: "run_started",
    ...overrides
  };
}
