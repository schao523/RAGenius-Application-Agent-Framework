import { z } from "zod";

export const executionOptionsSchema = z
  .object({
    dry_run: z.boolean().optional().default(false),
    require_confirmation: z.boolean().optional().default(false)
  })
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

export const executeAgentRequestSchema = executionRequestBaseSchema.extend({
  request_type: z.literal("execute_agent"),
  agent_backend: agentBackendSchema,
  agent_query: z.string().trim().min(1),
  agent_skill_hint: z.string().trim().min(1).optional(),
  approved_content_id: z.string().trim().min(1).optional(),
  approved_revision_id: z.string().trim().min(1).optional(),
  context: z.record(z.string(), z.unknown()).optional()
});

export const executionRequestSchema = z.discriminatedUnion("request_type", [
  executeSkillRequestSchema,
  executeAgentRequestSchema
]);

export type ExecutionOptions = z.infer<typeof executionOptionsSchema>;
export type ExecuteSkillRequest = z.infer<typeof executeSkillRequestSchema>;
export type ExecuteAgentRequest = z.infer<typeof executeAgentRequestSchema>;
export type ExecutionRequest = z.infer<typeof executionRequestSchema>;
