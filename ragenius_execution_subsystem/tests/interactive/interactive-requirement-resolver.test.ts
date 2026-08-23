import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { ExecuteAgentRequest } from "../../src/api/schemas/execution-request.schema.js";
import type { ResolvedAgentSkillSelection } from "../../src/core/agent-skills/agent-skill-types.js";
import { resolveInteractiveRequirements } from "../../src/core/interactive/interactive-requirement-resolver.js";

const request: ExecuteAgentRequest = {
  request_type: "execute_agent",
  app_id: "app_001",
  session_id: "session_001",
  agent_backend: "codex_cli",
  agent_query: "Ask before answering.",
  interaction_requirements: { required_types: ["selection"] }
};

function selection(requirement: "conditional" | "required"): ResolvedAgentSkillSelection {
  return {
    activation_method: "codex_explicit_reference",
    agent_skill_id: "skill_001",
    approved_fingerprint: "sha256:v1:approved",
    backend: "codex_cli",
    display_name: "Interactive skill",
    interaction_policy: {
      interaction_requirement: requirement,
      supported_interaction_types: ["clarification"],
      required_transport: "interactive",
      recovery_class: "turn_resumable"
    },
    observed_fingerprint: "sha256:v1:approved",
    protected_locator_ref: "protected",
    provider_skill_name: "interactive-skill",
    provider_skill_reference: "interactive-skill",
    resolved_at: "2026-08-21T00:00:00.000Z",
    runtime_target_id: "codex-local",
    source_id: "source_001"
  };
}

describe("interactive requirement resolver", () => {
  it("routes an Auto request with an explicit selection requirement", () => {
    assert.deepEqual(resolveInteractiveRequirements({ request, selection: null }), {
      requiredInteractionTypes: ["selection"],
      requiredOccurrenceTypes: ["selection"]
    });
  });

  it("routes an interactive transport without requiring an interaction to occur", () => {
    assert.deepEqual(resolveInteractiveRequirements({
      request: {
        ...request,
        interaction_requirements: {
          transport: "interactive",
          allowed_types: ["clarification", "selection"],
          required_types: []
        }
      },
      selection: null
    }), {
      requiredInteractionTypes: ["clarification", "selection"],
      requiredOccurrenceTypes: []
    });
  });

  it("infers a required selection from an explicit Interactive Agent imperative", () => {
    assert.deepEqual(resolveInteractiveRequirements({
      request: {
        ...request,
        agent_query:
          "Before answering the questions, ask me to select Markdown or plain text. After I select, answer.",
        interaction_requirements: {
          transport: "interactive",
          style: "structured",
          allowed_types: ["clarification", "selection"],
          required_types: []
        }
      },
      selection: null
    }), {
      inferredInteractionTypes: ["selection"],
      requiredInteractionTypes: ["clarification", "selection"],
      requiredOccurrenceTypes: ["selection"]
    });
  });

  it("does not infer required interaction from negated or non-interactive wording", () => {
    assert.deepEqual(resolveInteractiveRequirements({
      request: {
        ...request,
        agent_query: "Do not ask me to select a format. Use Markdown.",
        interaction_requirements: {
          transport: "interactive",
          style: "structured",
          allowed_types: ["clarification", "selection"],
          required_types: []
        }
      },
      selection: null
    }), {
      requiredInteractionTypes: ["clarification", "selection"],
      requiredOccurrenceTypes: []
    });
    assert.equal(resolveInteractiveRequirements({
      request: {
        ...request,
        agent_query: "Before answering, ask me to select Markdown or plain text.",
        interaction_requirements: undefined
      },
      selection: null
    }), null);
  });

  it("routes chat-level interaction without advertising typed interactions", () => {
    assert.deepEqual(resolveInteractiveRequirements({
      request: {
        ...request,
        agent_backend: "openclaw_cli",
        interaction_requirements: { transport: "interactive", style: "chat" }
      },
      selection: null
    }), {
      requiredChatLevelInteraction: true,
      requiredInteractionTypes: [],
      requiredOccurrenceTypes: []
    });
  });

  it("unions request and governed skill requirements without weakening either", () => {
    assert.deepEqual(resolveInteractiveRequirements({ request, selection: selection("required") }), {
      requiredInteractionTypes: ["selection", "clarification"],
      requiredOccurrenceTypes: ["selection", "clarification"],
      requiredRecoveryClass: "turn_resumable"
    });
  });

  it("does not require a conditional skill interaction to occur", () => {
    assert.deepEqual(resolveInteractiveRequirements({ request, selection: selection("conditional") }), {
      requiredInteractionTypes: ["selection", "clarification"],
      requiredOccurrenceTypes: ["selection"],
      requiredRecoveryClass: "turn_resumable"
    });
  });
});
