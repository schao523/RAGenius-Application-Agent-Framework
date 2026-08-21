import type {
  InteractiveAgentAdapter,
  InteractivePreflightInput,
  InteractivePreflightResult
} from "./interactive-agent-adapter.js";
import type { AgentBackend } from "./interactive-agent-types.js";

export type InteractiveCapabilityDecision =
  | {
      available: true;
      adapter: InteractiveAgentAdapter;
      preflight: InteractivePreflightResult;
    }
  | {
      available: false;
      failureCode: "INTERACTIVE_ADAPTER_UNAVAILABLE" | "INTERACTIVE_CAPABILITY_UNAVAILABLE";
      reason: string;
    };

export class InteractiveCapabilityService {
  private readonly adapters: Map<AgentBackend, InteractiveAgentAdapter>;

  constructor(adapters: Iterable<InteractiveAgentAdapter>) {
    this.adapters = new Map(
      [...adapters].map((adapter) => [adapter.backend, adapter])
    );
  }

  adapterFor(backend: AgentBackend): InteractiveAgentAdapter | undefined {
    return this.adapters.get(backend);
  }

  async preflight(input: InteractivePreflightInput): Promise<InteractiveCapabilityDecision> {
    const adapter = this.adapters.get(input.request.agent_backend);
    if (!adapter) {
      return {
        available: false,
        failureCode: "INTERACTIVE_ADAPTER_UNAVAILABLE",
        reason: `No interactive adapter is configured for ${input.request.agent_backend}.`
      };
    }
    const preflight = await adapter.preflight(input);
    if (!preflight.available || !preflight.capabilities.protocolTransport) {
      return {
        available: false,
        failureCode: "INTERACTIVE_CAPABILITY_UNAVAILABLE",
        reason: preflight.reason ?? "The interactive transport is unavailable."
      };
    }
    const missing = input.requiredInteractionTypes.filter(
      (type) => !preflight.capabilities.interactionTypes.includes(type)
    );
    if (missing.length > 0) {
      return {
        available: false,
        failureCode: "INTERACTIVE_CAPABILITY_UNAVAILABLE",
        reason: `The adapter does not support required interaction types: ${missing.join(", ")}.`
      };
    }
    const recoveryClass = input.requiredRecoveryClass ?? "not_resumable";
    if (
      recoveryClass === "session_resumable"
      && !preflight.capabilities.sameSessionContinuation
    ) {
      return {
        available: false,
        failureCode: "INTERACTIVE_CAPABILITY_UNAVAILABLE",
        reason: "The adapter does not support required same-session recovery."
      };
    }
    if (recoveryClass === "turn_resumable" && !preflight.capabilities.sameTurnResume) {
      return {
        available: false,
        failureCode: "INTERACTIVE_CAPABILITY_UNAVAILABLE",
        reason: "The adapter does not support required same-turn recovery."
      };
    }
    return { adapter, available: true, preflight };
  }
}
