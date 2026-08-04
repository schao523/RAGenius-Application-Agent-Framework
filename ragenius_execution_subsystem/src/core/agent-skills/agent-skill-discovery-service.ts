import type {
  AgentSkillBackend,
  AgentSkillDiscoveryAdapter,
  AgentSkillDiscoveryInput,
  AgentSkillDiscoveryResult,
  AgentSkillInspectionInput,
  AgentSkillCatalogCandidate,
  AgentSkillSourceOption
} from "./agent-skill-types.js";

export class AgentSkillDiscoveryService {
  private readonly adapters: Map<AgentSkillBackend, AgentSkillDiscoveryAdapter>;

  constructor(adapters: AgentSkillDiscoveryAdapter[]) {
    this.adapters = new Map(adapters.map((adapter) => [adapter.backend, adapter]));
  }

  sourceOptions(): AgentSkillSourceOption[] {
    return [...this.adapters.values()].flatMap((adapter) => adapter.sourceOptions());
  }

  discover(
    backend: AgentSkillBackend,
    input: AgentSkillDiscoveryInput
  ): Promise<AgentSkillDiscoveryResult> {
    return this.adapter(backend).discover(input);
  }

  inspect(
    backend: AgentSkillBackend,
    input: AgentSkillInspectionInput
  ): Promise<AgentSkillCatalogCandidate> {
    return this.adapter(backend).inspect(input);
  }

  private adapter(backend: AgentSkillBackend): AgentSkillDiscoveryAdapter {
    const adapter = this.adapters.get(backend);
    if (!adapter) {
      throw new Error(`AGENT_SKILL_BACKEND_UNAVAILABLE: ${backend}`);
    }
    return adapter;
  }
}
