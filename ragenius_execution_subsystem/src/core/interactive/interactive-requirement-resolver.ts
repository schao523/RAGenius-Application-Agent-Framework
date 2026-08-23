import type { ExecuteAgentRequest } from "../../api/schemas/execution-request.schema.js";
import type {
  AgentSkillRecoveryClass,
  ResolvedAgentSkillSelection
} from "../agent-skills/agent-skill-types.js";

import type { AgentInteractionType } from "./interactive-agent-types.js";

export interface ResolvedInteractiveRequirements {
  inferredInteractionTypes?: AgentInteractionType[];
  requiredChatLevelInteraction?: boolean;
  requiredInteractionTypes: AgentInteractionType[];
  requiredOccurrenceTypes: AgentInteractionType[];
  requiredRecoveryClass?: AgentSkillRecoveryClass;
}

export function resolveInteractiveRequirements(input: {
  request: ExecuteAgentRequest;
  selection: ResolvedAgentSkillSelection | null;
}): ResolvedInteractiveRequirements | null {
  const requestRequirements = input.request.interaction_requirements;
  const requiredChatLevelInteraction = requestRequirements?.style === "chat";
  const requiredRequestTypes = requestRequirements?.required_types ?? [];
  const allowedRequestTypes = requestRequirements?.allowed_types ?? [];
  const inferredInteractionTypes = inferExplicitInteractionTypes(input.request);
  const requestTypes = stableUnique([
    ...allowedRequestTypes,
    ...requiredRequestTypes
  ]);
  const policy = input.selection?.interaction_policy;
  const policyTypes =
    policy?.required_transport === "interactive"
      ? policy.supported_interaction_types
      : [];
  const requiredInteractionTypes = stableUnique([...requestTypes, ...policyTypes]);
  if (requiredInteractionTypes.length === 0 && !requiredChatLevelInteraction) return null;

  const requiredOccurrenceTypes = stableUnique([
    ...requiredRequestTypes,
    ...inferredInteractionTypes,
    ...(policy?.interaction_requirement === "required" ? policyTypes : [])
  ]);
  return {
    ...(inferredInteractionTypes.length > 0
      ? { inferredInteractionTypes }
      : {}),
    ...(requiredChatLevelInteraction ? { requiredChatLevelInteraction: true } : {}),
    requiredInteractionTypes,
    requiredOccurrenceTypes,
    ...(policy?.recovery_class
      ? { requiredRecoveryClass: policy.recovery_class }
      : {})
  };
}

function inferExplicitInteractionTypes(
  request: ExecuteAgentRequest
): AgentInteractionType[] {
  const requirements = request.interaction_requirements;
  if (
    request.agent_backend !== "codex_cli" ||
    requirements?.transport !== "interactive" ||
    requirements.style === "chat"
  ) {
    return [];
  }
  const query = request.agent_query.trim();
  const inferred: AgentInteractionType[] = [];
  const commandPrefix = String.raw`(?:^|[.!?]\s+)(?:please\s+)?(?:before\b.{0,180}?[,:]\s*)?`;
  if (
    new RegExp(`${commandPrefix}ask me to (?:select|choose)\\b`, "i").test(query)
  ) {
    inferred.push("selection");
  }
  if (
    new RegExp(
      `${commandPrefix}ask me (?:for clarification|to clarify|a clarifying question)\\b`,
      "i"
    ).test(query)
  ) {
    inferred.push("clarification");
  }
  return inferred.filter((type) =>
    stableUnique([
      ...(requirements.allowed_types ?? []),
      ...(requirements.required_types ?? [])
    ]).includes(type)
  );
}

function stableUnique(values: AgentInteractionType[]): AgentInteractionType[] {
  return [...new Set(values)];
}
