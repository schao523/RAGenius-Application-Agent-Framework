import type {
  AgentSessionScope,
  AgentSessionStore,
  CreateAgentSessionInput,
  UpdateAgentSessionInput
} from "./agent-session-store.js";
import type {
  AgentInteractionCapabilities,
  AgentSessionRecord,
  ExecutionScope
} from "./interactive-agent-types.js";

export interface AgentSessionRow {
  appId: string;
  backend: string;
  capabilitySnapshot: unknown;
  continuationMode: string;
  createdAt: Date;
  executionId: string;
  id: string;
  lastEventSeq: number;
  protocolVersion: string;
  providerRunRef: string | null;
  providerSessionRef: string;
  providerTurnRef: string | null;
  sessionId: string;
  state: string;
  transport: string;
  updatedAt: Date;
}

export interface AgentSessionPrismaClient {
  agentSession: {
    findFirst(args: { where: Record<string, unknown> }): Promise<AgentSessionRow | null>;
    updateMany(args: {
      data: Record<string, unknown>;
      where: Record<string, unknown>;
    }): Promise<{ count: number }>;
    upsert(args: {
      create: Record<string, unknown>;
      update: Record<string, unknown>;
      where: { executionId: string };
    }): Promise<AgentSessionRow>;
  };
}

export class PrismaAgentSessionStore implements AgentSessionStore {
  constructor(private readonly prisma: AgentSessionPrismaClient) {}

  async create(input: CreateAgentSessionInput): Promise<AgentSessionRecord> {
    const row = await this.prisma.agentSession.upsert({
      where: { executionId: input.executionId },
      create: {
        id: input.agentSessionId,
        executionId: input.executionId,
        appId: input.appId,
        sessionId: input.sessionId,
        backend: input.backend,
        transport: input.transport,
        state: input.state,
        providerSessionRef: input.providerSessionRef,
        providerRunRef: input.providerRunRef,
        providerTurnRef: input.providerTurnRef,
        continuationMode: input.continuationMode,
        protocolVersion: input.protocolVersion,
        capabilitySnapshot: input.capabilitySnapshot
      },
      update: {}
    });
    if (!matchesScope(row, input)) {
      throw new Error("Existing Agent session does not match execution scope.");
    }
    return toRecord(row);
  }

  async get(scope: AgentSessionScope): Promise<AgentSessionRecord | null> {
    const row = await this.prisma.agentSession.findFirst({
      where: scopeWhere(scope, { id: scope.agentSessionId })
    });
    return row ? toRecord(row) : null;
  }

  async getByExecution(scope: ExecutionScope): Promise<AgentSessionRecord | null> {
    const row = await this.prisma.agentSession.findFirst({
      where: scopeWhere(scope)
    });
    return row ? toRecord(row) : null;
  }

  async update(
    scope: AgentSessionScope,
    input: UpdateAgentSessionInput
  ): Promise<AgentSessionRecord | null> {
    await this.prisma.agentSession.updateMany({
      where: scopeWhere(scope, { id: scope.agentSessionId }),
      data: input
    });
    return this.get(scope);
  }
}

function scopeWhere(
  scope: ExecutionScope,
  extra: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    appId: scope.appId,
    executionId: scope.executionId,
    sessionId: scope.sessionId,
    ...extra
  };
}

function matchesScope(row: AgentSessionRow, scope: ExecutionScope): boolean {
  return (
    row.appId === scope.appId &&
    row.executionId === scope.executionId &&
    row.sessionId === scope.sessionId
  );
}

function asCapabilities(value: unknown): AgentInteractionCapabilities {
  return value as AgentInteractionCapabilities;
}

function toRecord(row: AgentSessionRow): AgentSessionRecord {
  return {
    agentSessionId: row.id,
    appId: row.appId,
    backend: row.backend as AgentSessionRecord["backend"],
    capabilitySnapshot: asCapabilities(row.capabilitySnapshot),
    continuationMode: row.continuationMode as AgentSessionRecord["continuationMode"],
    createdAt: row.createdAt,
    executionId: row.executionId,
    lastEventSeq: row.lastEventSeq,
    protocolVersion: row.protocolVersion,
    providerRunRef: row.providerRunRef,
    providerSessionRef: row.providerSessionRef,
    providerTurnRef: row.providerTurnRef,
    sessionId: row.sessionId,
    state: row.state as AgentSessionRecord["state"],
    transport: row.transport as AgentSessionRecord["transport"],
    updatedAt: row.updatedAt
  };
}
