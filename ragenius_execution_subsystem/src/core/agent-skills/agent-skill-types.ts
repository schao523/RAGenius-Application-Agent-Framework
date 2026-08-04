export type AgentSkillBackend = "codex_cli" | "openclaw_cli";

export type AgentSkillApprovalState = "approved" | "revoked" | "superseded";

export interface ProjectedAgentSkillGovernance {
  agent_skill_id: string;
  app_id: string;
  approval_state: AgentSkillApprovalState;
  approved_fingerprint: string;
  backend: AgentSkillBackend;
  binding_enabled: boolean;
  current_fingerprint: string;
  description: string;
  direct_tool_dispatch: boolean;
  display_name: string;
  model_visible: boolean;
  protected_locator_ref: string;
  provider_skill_name: string;
  runtime_target_id: string;
  source_enabled: boolean;
  source_id: string;
  user_invocable: boolean;
}

export interface AgentSkillGovernanceProjection {
  builder_instance_id: string;
  digest: string;
  generated_at: string;
  items: ProjectedAgentSkillGovernance[];
  revision: number;
}

export interface ProjectionRevisionSummary {
  builder_instance_id: string;
  digest: string;
  generated_at: string;
  item_count: number;
  received_at: string;
  revision: number;
}

export interface ProjectionReceipt extends ProjectionRevisionSummary {
  idempotent: boolean;
}
