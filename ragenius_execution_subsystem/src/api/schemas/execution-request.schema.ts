import { z } from "zod";

export const executionOptionsSchema = z
  .object({
    dry_run: z.boolean().optional().default(false),
    mode: z.enum(["sync", "async"]).optional()
  })
  .strict()
  .default({});

const executionRequestBaseSchema = z.object({
  app_id: z.string().trim().min(1),
  session_id: z.string().trim().min(1),
  execution_options: executionOptionsSchema.optional()
});

export const executeSkillRequestSchema = executionRequestBaseSchema.extend({
  request_type: z.literal("execute_skill"),
  skill_id: z.string().trim().min(1),
  input: z.record(z.string(), z.unknown())
});

export const agentBackendSchema = z.enum(["codex_cli", "openclaw_cli"]);

export const agentSkillRefSchema = z.object({
  agent_skill_id: z.string().trim().min(1),
  approved_fingerprint: z.string().trim().min(1)
}).strict();

const conversationalInteractionTypesSchema = z
  .array(z.enum(["clarification", "selection"]))
  .max(2)
  .refine((values) => new Set(values).size === values.length, {
    message: "Interaction types must be unique."
  });

export const agentRequestInteractionRequirementsSchema = z
  .object({
    transport: z.literal("interactive").optional(),
    style: z.enum(["structured", "chat"]).optional(),
    allowed_types: conversationalInteractionTypesSchema.optional(),
    required_types: conversationalInteractionTypesSchema.optional()
  })
  .strict()
  .superRefine((value, context) => {
    const allowed = value.allowed_types ?? [];
    const required = value.required_types ?? [];
    if (value.style === "chat" && (allowed.length > 0 || required.length > 0)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Chat-level interaction cannot advertise typed interactions."
      });
    } else if (value.style !== "chat" && allowed.length === 0 && required.length === 0) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: "At least one allowed or required interaction type is needed."
      });
    }
  });

export const agentArtifactRefSchema = z
  .object({
    artifact_id: z.string().trim().min(1),
    artifact_version_id: z.string().trim().min(1).optional(),
    role: z.enum(["source", "context", "template", "attachment"]),
    reuse_mode: z.enum([
      "inline_text",
      "file_backed",
      "binary_payload",
      "metadata_only"
    ]),
    display_name: z.string().trim().min(1).optional(),
    mime_type: z.string().trim().min(1).optional()
  })
  .strict();

export const agentExpectedOutputSchema = z
  .object({
    output_id: z.string().trim().regex(/^[A-Za-z0-9][A-Za-z0-9_-]*$/),
    display_name: z.string().trim().min(1).optional(),
    media_type: z.string().trim().min(1).optional(),
    required: z.boolean().optional(),
    persist_as_artifact: z.boolean().optional(),
    artifact_type: z.literal("agent_output").optional(),
    min_size_bytes: z.number().int().nonnegative().optional(),
    expected_sha256: z.string().trim().regex(/^[a-fA-F0-9]{64}$/).optional()
  })
  .strict();

export const executeAgentRequestSchema = executionRequestBaseSchema.extend({
  request_type: z.literal("execute_agent"),
  agent_backend: agentBackendSchema,
  agent_query: z.string().trim().min(1),
  agent_skill_ref: agentSkillRefSchema.optional(),
  agent_skill_hint: z.string().trim().min(1).optional(),
  approved_content_id: z.string().trim().min(1).optional(),
  approved_revision_id: z.string().trim().min(1).optional(),
  interaction_requirements: agentRequestInteractionRequirementsSchema.optional(),
  artifact_refs: z.array(agentArtifactRefSchema).optional(),
  expected_outputs: z.array(agentExpectedOutputSchema).optional(),
  context: z.record(z.string(), z.unknown()).optional()
});

export const executionRequestSchema = z.discriminatedUnion("request_type", [
  executeSkillRequestSchema,
  executeAgentRequestSchema
]);

export type ExecutionOptions = z.infer<typeof executionOptionsSchema>;
export type AgentArtifactRef = z.infer<typeof agentArtifactRefSchema>;
export type AgentSkillRef = z.infer<typeof agentSkillRefSchema>;
export type AgentRequestInteractionRequirements = z.infer<
  typeof agentRequestInteractionRequirementsSchema
>;
export type AgentExpectedOutput = z.infer<typeof agentExpectedOutputSchema>;
export type ExecuteSkillRequest = z.infer<typeof executeSkillRequestSchema>;
export type ExecuteAgentRequest = z.infer<typeof executeAgentRequestSchema>;
export type ExecutionRequest = z.infer<typeof executionRequestSchema>;
