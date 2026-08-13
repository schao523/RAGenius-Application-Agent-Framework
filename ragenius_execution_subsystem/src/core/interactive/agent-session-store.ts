import type {
  AgentSessionRecord,
  ExecutionScope
} from "./interactive-agent-types.js";

export type CreateAgentSessionInput = Omit<
  AgentSessionRecord,
  "createdAt" | "lastEventSeq" | "updatedAt"
>;

export interface AgentSessionScope extends ExecutionScope {
  agentSessionId: string;
}

export type UpdateAgentSessionInput = Partial<
  Pick<
    AgentSessionRecord,
    | "capabilitySnapshot"
    | "lastEventSeq"
    | "providerRunRef"
    | "providerSessionRef"
    | "providerTurnRef"
    | "state"
  >
>;

export interface AgentSessionStore {
  create(input: CreateAgentSessionInput): Promise<AgentSessionRecord>;
  get(scope: AgentSessionScope): Promise<AgentSessionRecord | null>;
  getByExecution(scope: ExecutionScope): Promise<AgentSessionRecord | null>;
  update(
    scope: AgentSessionScope,
    input: UpdateAgentSessionInput
  ): Promise<AgentSessionRecord | null>;
}

export class InMemoryAgentSessionStore implements AgentSessionStore {
  private readonly records = new Map<string, AgentSessionRecord>();
  private readonly executionIndex = new Map<string, string>();

  async create(input: CreateAgentSessionInput): Promise<AgentSessionRecord> {
    const existingId = this.executionIndex.get(input.executionId);
    const existing = existingId ? this.records.get(existingId) : undefined;
    if (existing) {
      if (!matchesScope(existing, input)) {
        throw new Error("Existing Agent session does not match execution scope.");
      }
      return cloneSession(existing);
    }
    const now = new Date();
    const record: AgentSessionRecord = {
      ...input,
      capabilitySnapshot: cloneCapabilities(input.capabilitySnapshot),
      createdAt: now,
      lastEventSeq: 0,
      updatedAt: now
    };
    this.records.set(record.agentSessionId, record);
    this.executionIndex.set(record.executionId, record.agentSessionId);
    return cloneSession(record);
  }

  async get(scope: AgentSessionScope): Promise<AgentSessionRecord | null> {
    const record = this.records.get(scope.agentSessionId);
    return record && matchesScope(record, scope) ? cloneSession(record) : null;
  }

  async getByExecution(scope: ExecutionScope): Promise<AgentSessionRecord | null> {
    const id = this.executionIndex.get(scope.executionId);
    const record = id ? this.records.get(id) : undefined;
    return record && matchesScope(record, scope) ? cloneSession(record) : null;
  }

  async update(
    scope: AgentSessionScope,
    input: UpdateAgentSessionInput
  ): Promise<AgentSessionRecord | null> {
    const current = this.records.get(scope.agentSessionId);
    if (!current || !matchesScope(current, scope)) {
      return null;
    }
    const updated: AgentSessionRecord = {
      ...current,
      ...input,
      capabilitySnapshot: input.capabilitySnapshot
        ? cloneCapabilities(input.capabilitySnapshot)
        : current.capabilitySnapshot,
      updatedAt: new Date()
    };
    this.records.set(updated.agentSessionId, updated);
    return cloneSession(updated);
  }
}

function matchesScope(record: ExecutionScope, scope: ExecutionScope): boolean {
  return (
    record.appId === scope.appId &&
    record.executionId === scope.executionId &&
    record.sessionId === scope.sessionId
  );
}

function cloneCapabilities(
  value: AgentSessionRecord["capabilitySnapshot"]
): AgentSessionRecord["capabilitySnapshot"] {
  return { ...value, interactionTypes: [...value.interactionTypes] };
}

function cloneSession(record: AgentSessionRecord): AgentSessionRecord {
  return {
    ...record,
    capabilitySnapshot: cloneCapabilities(record.capabilitySnapshot)
  };
}
