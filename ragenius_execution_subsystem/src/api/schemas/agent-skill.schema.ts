import { createHash } from "node:crypto";

import { z } from "zod";

const backendSchema = z.enum(["codex_cli", "openclaw_cli"]);
const fingerprintSchema = z.string().trim().min(1);

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
    provider_skill_reference: z.string().trim().min(1)
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
    provider_skill_reference:
      item.provider_skill_reference ?? item.provider_skill_name
  });
}
