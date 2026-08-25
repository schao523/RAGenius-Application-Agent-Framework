import { z } from "zod";

export const providerInteractionRequestSchema = z.object({
  allowsFreeText: z.boolean(),
  expiresAt: z.date(),
  interactionId: z.string().trim().min(1).max(200),
  options: z.array(z.object({
    description: z.string().trim().min(1).max(200).optional(),
    id: z.string().trim().min(1).max(200),
    label: z.string().trim().min(1).max(200)
  }).strict()).max(20),
  presentation: z.object({
    completionLabel: z.string().trim().min(1).max(100).optional(),
    launchAvailable: z.boolean().optional(),
    targetHost: z.string().trim().min(1).max(253)
      .regex(/^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$/).optional(),
    targetLabel: z.string().trim().min(1).max(200).optional()
  }).strict().nullable().optional(),
  policyBindingHash: z.string().trim().min(1).max(512),
  prompt: z.string().trim().min(1).max(2000),
  providerCorrelationRef: z.string().trim().min(1).max(512),
  type: z.enum([
    "approval",
    "clarification",
    "selection",
    "authentication_handoff",
    "user_action_required"
  ])
}).strict();

export const interactiveExecutionScopeQuerySchema = z.object({
  app_id: z.string().trim().min(1),
  session_id: z.string().trim().min(1)
}).passthrough();

const approvalResponseSchema = z.object({
  kind: z.literal("approval"),
  decision: z.enum(["allow_once", "deny", "cancel_execution"])
}).strict();

const selectionResponseSchema = z.object({
  kind: z.literal("selection"),
  option_ids: z.array(z.string().trim().min(1).max(200)).max(20)
}).strict();

const clarificationResponseSchema = z.object({
  kind: z.literal("clarification"),
  text: z.string().trim().min(1).max(8000)
}).strict();

const userActionResponseSchema = z.object({
  kind: z.literal("user_action"),
  outcome: z.enum(["completed", "cancelled"])
}).strict();

export const agentInteractionResponseBodySchema = z.object({
  expected_version: z.number().int().positive(),
  idempotency_key: z.string().trim().min(1).max(128),
  response: z.discriminatedUnion("kind", [
    approvalResponseSchema,
    selectionResponseSchema,
    clarificationResponseSchema,
    userActionResponseSchema
  ])
}).strict();

export const agentEventQuerySchema = interactiveExecutionScopeQuerySchema.extend({
  after_sequence: z.coerce.number().int().nonnegative().default(0),
  limit: z.coerce.number().int().positive().max(200).default(100)
});

export const agentChatFollowUpBodySchema = z.object({
  expected_session_version: z.number().int().positive(),
  idempotency_key: z.string().trim().min(1).max(128),
  kind: z.enum(["reply", "continue", "revise", "graceful_cancel"]),
  text: z.string().trim().min(1).max(8000).optional()
}).strict().superRefine((value, context) => {
  if ((value.kind === "reply" || value.kind === "revise") && !value.text) {
    context.addIssue({ code: "custom", message: `${value.kind} requires text.`, path: ["text"] });
  }
});

export const endAgentChatSessionBodySchema = z.object({
  expected_session_version: z.number().int().positive()
}).strict();

export const agentInteractionLaunchBodySchema = z.object({
  expected_version: z.number().int().positive()
}).strict();

export type AgentInteractionResponseBody = z.infer<
  typeof agentInteractionResponseBodySchema
>;
