import type { ExecuteAgentRequest } from "../../api/schemas/execution-request.schema.js";
import { AppError } from "../errors/app-error.js";
import type { AgentSkillDiscoveryService } from "./agent-skill-discovery-service.js";
import type { AgentSkillProjectionStore } from "./agent-skill-projection-store.js";
import type {
  ProjectedAgentSkillGovernance,
  ResolvedAgentSkillSelection
} from "./agent-skill-types.js";

export class AgentSkillSelectionError extends AppError {
  constructor(code: string, message: string) {
    super({
      code,
      message: `${code}: ${message}`,
      errorClass: "validation",
      httpStatus: code === "AGENT_SKILL_BACKEND_MISMATCH" ? 400 : 409,
      recoverable: true,
      suggestedAction: "Refresh Agent skills and select a currently approved skill."
    });
    this.name = "AgentSkillSelectionError";
  }
}

function isSelectable(record: ProjectedAgentSkillGovernance): boolean {
  return record.approval_state === "approved" &&
    record.approved_fingerprint === record.current_fingerprint &&
    record.binding_enabled &&
    record.source_enabled &&
    record.model_visible &&
    !record.direct_tool_dispatch;
}

export class AgentSkillSelectionService {
  constructor(private readonly dependencies: {
    discoveryService: Pick<AgentSkillDiscoveryService, "inspect">;
    projectionStore: AgentSkillProjectionStore;
  }) {}

  async resolve(
    request: ExecuteAgentRequest
  ): Promise<ResolvedAgentSkillSelection | null> {
    if (!request.agent_skill_ref && !request.agent_skill_hint) {
      return null;
    }
    const active = await this.dependencies.projectionStore.getActiveRevision();
    if (!active) {
      throw new AgentSkillSelectionError(
        "AGENT_SKILL_PROJECTION_UNAVAILABLE",
        "Agent skill governance projection is unavailable."
      );
    }

    let selected: ProjectedAgentSkillGovernance | null = null;
    if (request.agent_skill_ref) {
      selected = await this.dependencies.projectionStore.getForApp(
        request.app_id,
        request.agent_skill_ref.agent_skill_id
      );
      if (!selected) {
        throw new AgentSkillSelectionError(
          "AGENT_SKILL_NOT_BOUND",
          "Selected Agent skill is not bound to this app."
        );
      }
      if (selected.backend !== request.agent_backend) {
        throw new AgentSkillSelectionError(
          "AGENT_SKILL_BACKEND_MISMATCH",
          "Selected Agent skill belongs to another backend."
        );
      }
      if (
        request.agent_skill_ref.approved_fingerprint !== selected.approved_fingerprint ||
        selected.approved_fingerprint !== selected.current_fingerprint
      ) {
        throw new AgentSkillSelectionError(
          "AGENT_SKILL_FINGERPRINT_CHANGED",
          "Selected Agent skill approval is stale."
        );
      }
    }

    if (request.agent_skill_hint) {
      const normalizedHint = request.agent_skill_hint.trim().toLowerCase();
      const candidates = (
        await this.dependencies.projectionStore.listForApp(
          request.app_id,
          request.agent_backend
        )
      ).filter((record) =>
        record.provider_skill_name.trim().toLowerCase() === normalizedHint
      );
      if (candidates.length > 1) {
        throw new AgentSkillSelectionError(
          "AGENT_SKILL_HINT_AMBIGUOUS",
          "Legacy Agent skill hint matches multiple governed skills."
        );
      }
      const hinted = candidates[0] ?? null;
      if (selected && hinted?.agent_skill_id !== selected.agent_skill_id) {
        throw new AgentSkillSelectionError(
          "AGENT_SKILL_SELECTION_CONFLICT",
          "Structured Agent skill selection conflicts with the legacy hint."
        );
      }
      if (!selected) selected = hinted;
    }

    if (!selected || !isSelectable(selected)) {
      throw new AgentSkillSelectionError(
        "AGENT_SKILL_NOT_BOUND",
        "Agent skill is not currently selectable for this app."
      );
    }

    const observed = await this.dependencies.discoveryService.inspect(
      selected.backend,
      {
        protected_locator_ref: selected.protected_locator_ref,
        provider_skill_name: selected.provider_skill_name,
        runtime_target_id: selected.runtime_target_id,
        source_id: selected.source_id
      }
    );
    if (
      observed.backend !== selected.backend ||
      observed.provider_skill_name !== selected.provider_skill_name ||
      observed.runtime_target_id !== selected.runtime_target_id ||
      observed.source_id !== selected.source_id
    ) {
      throw new AgentSkillSelectionError(
        "AGENT_SKILL_PROVIDER_IDENTITY_MISMATCH",
        "Provider inspection returned a different Agent skill identity."
      );
    }
    if (
      observed.discovery_status !== "available" ||
      observed.content_fingerprint !== selected.approved_fingerprint
    ) {
      throw new AgentSkillSelectionError(
        "AGENT_SKILL_FINGERPRINT_CHANGED",
        "Agent skill content changed after approval."
      );
    }

    return {
      activation_method: selected.backend === "openclaw_cli"
        ? "openclaw_prompt_guidance"
        : "codex_explicit_reference",
      agent_skill_id: selected.agent_skill_id,
      approved_fingerprint: selected.approved_fingerprint,
      backend: selected.backend,
      display_name: selected.display_name,
      observed_fingerprint: observed.content_fingerprint,
      protected_locator_ref: selected.protected_locator_ref,
      provider_skill_name: selected.provider_skill_name,
      resolved_at: new Date().toISOString(),
      runtime_target_id: selected.runtime_target_id,
      source_id: selected.source_id
    };
  }
}
