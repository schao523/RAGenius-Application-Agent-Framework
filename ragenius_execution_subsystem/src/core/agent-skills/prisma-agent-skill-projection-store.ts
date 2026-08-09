import { randomUUID } from "node:crypto";

import type {
  AgentSkillBackend,
  AgentSkillGovernanceProjection,
  ProjectedAgentSkillGovernance,
  ProjectionReceipt,
  ProjectionRevisionSummary
} from "./agent-skill-types.js";
import {
  AgentSkillProjectionError,
  type AgentSkillProjectionStore
} from "./agent-skill-projection-store.js";

interface RevisionRow {
  id: string;
  builderInstanceId: string;
  digest: string;
  generatedAt: Date;
  receivedAt: Date;
  revision: bigint;
  status: string;
}

interface GovernanceRow {
  agentSkillId: string;
  appId: string;
  approvalState: string;
  approvedFingerprint: string;
  backend: string;
  bindingEnabled: boolean;
  currentFingerprint: string;
  description: string;
  directToolDispatch: boolean;
  displayName: string;
  modelVisible: boolean;
  protectedLocatorRef: string;
  providerSkillName: string;
  providerSkillReference: string;
  runtimeTargetId: string;
  sourceEnabled: boolean;
  sourceId: string;
  userInvocable: boolean;
}

export interface AgentSkillProjectionTransactionClient {
  agentSkillProjectionHead: {
    findUnique(args: { where: { id: string } }): Promise<{
      activeRevisionId: string;
      id: string;
    } | null>;
    upsert(args: {
      create: { activeRevisionId: string; id: string };
      update: { activeRevisionId: string };
      where: { id: string };
    }): Promise<unknown>;
  };
  agentSkillProjectionRevision: {
    create(args: { data: Record<string, unknown> }): Promise<RevisionRow>;
    findUnique(args: { where: { id: string } }): Promise<RevisionRow | null>;
    updateMany(args: {
      data: { status: string };
      where: { status: string };
    }): Promise<{ count: number }>;
  };
  projectedAgentSkillGovernance: {
    createMany(args: {
      data: Array<Record<string, unknown>>;
    }): Promise<{ count: number }>;
    findFirst(args: {
      where: Record<string, unknown>;
    }): Promise<GovernanceRow | null>;
    findMany(args: {
      where: Record<string, unknown>;
    }): Promise<GovernanceRow[]>;
  };
}

export interface PrismaAgentSkillProjectionClient
  extends AgentSkillProjectionTransactionClient {
  $transaction<T>(
    operation: (transaction: AgentSkillProjectionTransactionClient) => Promise<T>,
    options?: { isolationLevel: "Serializable" }
  ): Promise<T>;
}

function revisionId(builderInstanceId: string, revision: number): string {
  return `${builderInstanceId}:${revision}`;
}

function revisionNumber(revision: bigint): number {
  const value = Number(revision);
  if (!Number.isSafeInteger(value)) {
    throw new AgentSkillProjectionError("REVISION_OUT_OF_RANGE");
  }
  return value;
}

function toSummary(row: RevisionRow, itemCount: number): ProjectionRevisionSummary {
  return {
    builder_instance_id: row.builderInstanceId,
    digest: row.digest,
    generated_at: row.generatedAt.toISOString(),
    item_count: itemCount,
    received_at: row.receivedAt.toISOString(),
    revision: revisionNumber(row.revision)
  };
}

function toGovernance(row: GovernanceRow): ProjectedAgentSkillGovernance {
  return {
    agent_skill_id: row.agentSkillId,
    app_id: row.appId,
    approval_state: row.approvalState as ProjectedAgentSkillGovernance["approval_state"],
    approved_fingerprint: row.approvedFingerprint,
    backend: row.backend as AgentSkillBackend,
    binding_enabled: row.bindingEnabled,
    current_fingerprint: row.currentFingerprint,
    description: row.description,
    direct_tool_dispatch: row.directToolDispatch,
    display_name: row.displayName,
    model_visible: row.modelVisible,
    protected_locator_ref: row.protectedLocatorRef,
    provider_skill_name: row.providerSkillName,
    provider_skill_reference: row.providerSkillReference,
    runtime_target_id: row.runtimeTargetId,
    source_enabled: row.sourceEnabled,
    source_id: row.sourceId,
    user_invocable: row.userInvocable
  };
}

function itemData(
  projectionRevisionId: string,
  item: ProjectedAgentSkillGovernance
): Record<string, unknown> {
  return {
    id: randomUUID(),
    projectionRevisionId,
    agentSkillId: item.agent_skill_id,
    appId: item.app_id,
    approvalState: item.approval_state,
    approvedFingerprint: item.approved_fingerprint,
    backend: item.backend,
    bindingEnabled: item.binding_enabled,
    currentFingerprint: item.current_fingerprint,
    description: item.description,
    directToolDispatch: item.direct_tool_dispatch,
    displayName: item.display_name,
    modelVisible: item.model_visible,
    protectedLocatorRef: item.protected_locator_ref,
    providerSkillName: item.provider_skill_name,
    providerSkillReference: item.provider_skill_reference,
    runtimeTargetId: item.runtime_target_id,
    sourceEnabled: item.source_enabled,
    sourceId: item.source_id,
    userInvocable: item.user_invocable
  };
}

export class PrismaAgentSkillProjectionStore
  implements AgentSkillProjectionStore
{
  constructor(private readonly prisma: PrismaAgentSkillProjectionClient) {}

  async publish(
    snapshot: AgentSkillGovernanceProjection
  ): Promise<ProjectionReceipt> {
    return this.prisma.$transaction(async (transaction) => {
      const current = await this.activeRevision(transaction);
      const snapshotRevision = BigInt(snapshot.revision);
      if (current) {
        if (snapshot.builder_instance_id !== current.builderInstanceId) {
          throw new AgentSkillProjectionError("BUILDER_INSTANCE_CONFLICT");
        }
        if (snapshotRevision < current.revision) {
          throw new AgentSkillProjectionError("REVISION_ROLLBACK");
        }
        if (snapshotRevision === current.revision) {
          if (snapshot.digest !== current.digest) {
            throw new AgentSkillProjectionError("REVISION_CONFLICT");
          }
          return {
            ...toSummary(current, snapshot.items.length),
            idempotent: true
          };
        }
      }

      const id = revisionId(snapshot.builder_instance_id, snapshot.revision);
      await transaction.agentSkillProjectionRevision.updateMany({
        data: { status: "superseded" },
        where: { status: "active" }
      });
      const created = await transaction.agentSkillProjectionRevision.create({
        data: {
          id,
          builderInstanceId: snapshot.builder_instance_id,
          digest: snapshot.digest,
          generatedAt: new Date(snapshot.generated_at),
          revision: snapshotRevision,
          status: "active"
        }
      });
      if (snapshot.items.length > 0) {
        await transaction.projectedAgentSkillGovernance.createMany({
          data: snapshot.items.map((item) => itemData(id, item))
        });
      }
      await transaction.agentSkillProjectionHead.upsert({
        create: { activeRevisionId: id, id: "active" },
        update: { activeRevisionId: id },
        where: { id: "active" }
      });
      return {
        ...toSummary(created, snapshot.items.length),
        idempotent: false
      };
    }, { isolationLevel: "Serializable" });
  }

  async getActiveRevision(): Promise<ProjectionRevisionSummary | null> {
    const row = await this.activeRevision(this.prisma);
    if (!row) return null;
    const items = await this.prisma.projectedAgentSkillGovernance.findMany({
      where: { projectionRevisionId: row.id }
    });
    return toSummary(row, items.length);
  }

  async listForApp(
    appId: string,
    backend: AgentSkillBackend
  ): Promise<ProjectedAgentSkillGovernance[]> {
    const row = await this.activeRevision(this.prisma);
    if (!row) return [];
    const items = await this.prisma.projectedAgentSkillGovernance.findMany({
      where: { appId, backend, projectionRevisionId: row.id }
    });
    return items.map(toGovernance);
  }

  async getForApp(
    appId: string,
    agentSkillId: string
  ): Promise<ProjectedAgentSkillGovernance | null> {
    const row = await this.activeRevision(this.prisma);
    if (!row) return null;
    const item = await this.prisma.projectedAgentSkillGovernance.findFirst({
      where: { agentSkillId, appId, projectionRevisionId: row.id }
    });
    return item ? toGovernance(item) : null;
  }

  private async activeRevision(
    client: AgentSkillProjectionTransactionClient
  ): Promise<RevisionRow | null> {
    const head = await client.agentSkillProjectionHead.findUnique({
      where: { id: "active" }
    });
    if (!head) return null;
    return client.agentSkillProjectionRevision.findUnique({
      where: { id: head.activeRevisionId }
    });
  }
}
