import { createHash } from "node:crypto";

import { z } from "zod";

const backendSchema = z.enum(["codex_cli", "openclaw_cli"]);
const fingerprintSchema = z.string().trim().min(1);
const interactionPolicySchema = z.object({
  interaction_requirement: z.enum(["autonomous", "conditional", "required"]),
  supported_interaction_types: z.array(z.enum([
    "approval",
    "clarification",
    "selection",
    "authentication_handoff",
    "user_action_required"
  ])),
  required_transport: z.enum(["one_shot", "interactive"]),
  recovery_class: z.enum(["not_resumable", "session_resumable", "turn_resumable"])
}).strict().superRefine((value, context) => {
  if (new Set(value.supported_interaction_types).size !== value.supported_interaction_types.length) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "Interaction types must be unique." });
  }
  if (value.required_transport === "one_shot" && (
    value.interaction_requirement !== "autonomous"
    || value.supported_interaction_types.length > 0
    || value.recovery_class !== "not_resumable"
  )) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "One-shot skills must be autonomous and not resumable." });
  }
  if (["conditional", "required"].includes(value.interaction_requirement)
    && value.supported_interaction_types.length === 0) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "Interactive requirements must declare supported interaction types." });
  }
  if (value.supported_interaction_types.length > 0
    && value.required_transport !== "interactive") {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "Interaction types require interactive transport." });
  }
  if (value.recovery_class !== "not_resumable"
    && value.required_transport !== "interactive") {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "Resumable recovery requires interactive transport." });
  }
});
const defaultInteractionPolicy = {
  interaction_requirement: "autonomous" as const,
  supported_interaction_types: [],
  required_transport: "one_shot" as const,
  recovery_class: "not_resumable" as const
};

export const projectedAgentSkillGovernanceWireSchema = z.object({
  agent_skill_id: z.string().trim().min(1),
  app_id: z.string().trim().min(1),
  approval_state: z.enum(["approved", "revoked", "superseded"]),
  approved_fingerprint: fingerprintSchema,
  backend: backendSchema,
  binding_enabled: z.boolean(),
  current_fingerprint: fingerprintSchema,
  description: z.string(),
  direct_tool_dispatch: z.boolean(),
  display_name: z.string().trim().min(1),
  model_visible: z.boolean(),
  interaction_policy: interactionPolicySchema.optional(),
  protected_locator_ref: z.string().trim().min(1),
  provider_skill_name: z.string().trim().min(1),
  provider_skill_reference: z.string().trim().min(1).optional(),
  runtime_target_id: z.string().trim().min(1),
  source_enabled: z.boolean(),
  source_id: z.string().trim().min(1),
  user_invocable: z.boolean()
}).strict();

export const projectedAgentSkillGovernanceSchema =
  projectedAgentSkillGovernanceWireSchema.extend({
    provider_skill_reference: z.string().trim().min(1),
    interaction_policy: interactionPolicySchema
  }).strict();

export const agentSkillGovernanceProjectionSchema = z.object({
  builder_instance_id: z.string().trim().min(1),
  digest: z.string().regex(/^sha256:[a-f0-9]{64}$/),
  generated_at: z.string().datetime({ offset: true }),
  items: z.array(projectedAgentSkillGovernanceWireSchema),
  revision: z.number().int().nonnegative()
}).strict();

export const agentSkillInventoryQuerySchema = z.object({
  app_id: z.string().trim().min(1),
  backend: backendSchema
}).strict();

function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(canonicalize);
  }
  if (typeof value !== "object" || value === null) {
    return value;
  }
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .filter(([key]) => key !== "digest")
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, child]) => [key, canonicalize(child)])
  );
}

export function computeAgentSkillProjectionDigest(
  input: Record<string, unknown>
): string {
  const unsigned = { ...input };
  delete unsigned.digest;
  if (Array.isArray(unsigned.items)) {
    unsigned.items = [...unsigned.items].sort((left, right) =>
      JSON.stringify(canonicalize(left)).localeCompare(
        JSON.stringify(canonicalize(right))
      )
    );
  }
  const bytes = JSON.stringify(canonicalize(unsigned));
  return `sha256:${createHash("sha256").update(bytes).digest("hex")}`;
}

export type AgentSkillGovernanceProjectionInput = z.infer<
  typeof agentSkillGovernanceProjectionSchema
>;

export function normalizeProjectedAgentSkillGovernance(
  item: z.infer<typeof projectedAgentSkillGovernanceWireSchema>
): z.infer<typeof projectedAgentSkillGovernanceSchema> {
  return projectedAgentSkillGovernanceSchema.parse({
    ...item,
    interaction_policy: item.interaction_policy ?? defaultInteractionPolicy,
    provider_skill_reference:
      item.provider_skill_reference ?? item.provider_skill_name
  });
}
