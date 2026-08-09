import type {
  AgentSkillBackend,
  AgentSkillGovernanceProjection,
  ProjectedAgentSkillGovernance,
  ProjectionReceipt,
  ProjectionRevisionSummary
} from "./agent-skill-types.js";

export interface AgentSkillProjectionStore {
  publish(snapshot: AgentSkillGovernanceProjection): Promise<ProjectionReceipt>;
  getActiveRevision(): Promise<ProjectionRevisionSummary | null>;
  listForApp(
    appId: string,
    backend: AgentSkillBackend
  ): Promise<ProjectedAgentSkillGovernance[]>;
  getForApp(
    appId: string,
    agentSkillId: string
  ): Promise<ProjectedAgentSkillGovernance | null>;
}

export type AgentSkillProjectionErrorCode =
  | "BUILDER_INSTANCE_CONFLICT"
  | "DUPLICATE_PROJECTION_ITEM"
  | "REVISION_CONFLICT"
  | "REVISION_OUT_OF_RANGE"
  | "REVISION_ROLLBACK";

export class AgentSkillProjectionError extends Error {
  constructor(readonly code: AgentSkillProjectionErrorCode) {
    super(code);
    this.name = "AgentSkillProjectionError";
  }
}

interface ActiveProjection {
  items: ProjectedAgentSkillGovernance[];
  summary: ProjectionRevisionSummary;
}

function cloneItem(
  item: ProjectedAgentSkillGovernance
): ProjectedAgentSkillGovernance {
  return { ...item };
}

export class InMemoryAgentSkillProjectionStore
  implements AgentSkillProjectionStore
{
  private active: ActiveProjection | null = null;

  async publish(
    snapshot: AgentSkillGovernanceProjection
  ): Promise<ProjectionReceipt> {
    if (this.active) {
      if (
        snapshot.builder_instance_id !== this.active.summary.builder_instance_id
      ) {
        throw new AgentSkillProjectionError("BUILDER_INSTANCE_CONFLICT");
      }
      if (snapshot.revision < this.active.summary.revision) {
        throw new AgentSkillProjectionError("REVISION_ROLLBACK");
      }
      if (snapshot.revision === this.active.summary.revision) {
        if (snapshot.digest !== this.active.summary.digest) {
          throw new AgentSkillProjectionError("REVISION_CONFLICT");
        }
        return { ...this.active.summary, idempotent: true };
      }
    }

    const seen = new Set<string>();
    const items = snapshot.items.map((item) => {
      const key = `${item.app_id}\u0000${item.agent_skill_id}`;
      if (seen.has(key)) {
        throw new AgentSkillProjectionError("DUPLICATE_PROJECTION_ITEM");
      }
      seen.add(key);
      return cloneItem(item);
    });
    const summary: ProjectionRevisionSummary = {
      builder_instance_id: snapshot.builder_instance_id,
      digest: snapshot.digest,
      generated_at: snapshot.generated_at,
      item_count: items.length,
      received_at: new Date().toISOString(),
      revision: snapshot.revision
    };
    this.active = { items, summary };
    return { ...summary, idempotent: false };
  }

  async getActiveRevision(): Promise<ProjectionRevisionSummary | null> {
    return this.active ? { ...this.active.summary } : null;
  }

  async listForApp(
    appId: string,
    backend: AgentSkillBackend
  ): Promise<ProjectedAgentSkillGovernance[]> {
    return (this.active?.items ?? [])
      .filter((item) => item.app_id === appId && item.backend === backend)
      .map(cloneItem);
  }

  async getForApp(
    appId: string,
    agentSkillId: string
  ): Promise<ProjectedAgentSkillGovernance | null> {
    const item = this.active?.items.find(
      (candidate) =>
        candidate.app_id === appId &&
        candidate.agent_skill_id === agentSkillId
    );
    return item ? cloneItem(item) : null;
  }
}
