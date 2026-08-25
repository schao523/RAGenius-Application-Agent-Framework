import { z } from "zod";

import type { CodexManagedAuthenticationTarget } from "./codex-managed-auth-targets.js";
import { isSecretInteractionText } from "./codex-mcp-elicitation.js";
import type { AgentInteractionPresentation, AgentInteractionType } from "./interactive-agent-types.js";

const toolCallSchema = z.object({
  question: z.string().trim().min(1).max(2000),
  options: z.array(z.string().trim().min(1).max(200)).max(20).optional(),
  allows_free_text: z.boolean().optional().default(false)
}).strict();

const SECRET_REQUEST_PATTERN =
  /\b(password|passcode|otp|one[- ]time code|api[- ]?key|token|auth(?:entication)? code|cookie|credential|private key|secret)\b/i;

const authenticationHandoffCallSchema = z.object({
  authentication_target_id: z.string().trim().min(1).max(100),
  instruction: z.string().trim().min(1).max(2000),
  completion_label: z.string().trim().min(1).max(100).optional()
}).strict();

const userActionCallSchema = z.object({
  instruction: z.string().trim().min(1).max(2000),
  completion_label: z.string().trim().min(1).max(100).optional()
}).strict();

const EXTERNAL_AUTHORIZATION_PATTERN =
  /\b(?:approve|authorize|confirm)\b.{0,80}\b(?:publish(?:ing)?|send(?:ing)?|delet(?:e|ing)|post(?:ing)?|external write)\b|\b(?:publish(?:ing)?|send(?:ing)?|delet(?:e|ing)|post(?:ing)?|external write)\b.{0,80}\b(?:approve|authorize|confirm)\b/i;

export const rageniusInteractionToolSpec = {
  type: "function" as const,
  name: "ragenius_request_input",
  description:
    "Ask the user one bounded non-secret clarification or selection question. This tool cannot request authorization, credentials, passwords, tokens, or OTPs.",
  inputSchema: {
    type: "object",
    additionalProperties: false,
    required: ["question"],
    properties: {
      question: { type: "string", maxLength: 2000 },
      options: {
        type: "array",
        maxItems: 20,
        items: { type: "string", maxLength: 200 }
      },
      allows_free_text: { type: "boolean" }
    }
  }
};

export const rageniusAuthenticationHandoffToolSpec = {
  type: "function" as const,
  name: "ragenius_request_authentication_handoff",
  description:
    "Pause for sign-in or account consent at an administrator-approved authentication target. Never request credentials in RAGenius.",
  inputSchema: {
    type: "object",
    additionalProperties: false,
    required: ["authentication_target_id", "instruction"],
    properties: {
      authentication_target_id: { type: "string", minLength: 1, maxLength: 100 },
      instruction: { type: "string", maxLength: 2000 },
      completion_label: { type: "string", maxLength: 100 }
    }
  }
};

export const rageniusUserActionToolSpec = {
  type: "function" as const,
  name: "ragenius_request_user_action",
  description:
    "Pause for one bounded non-secret action in an already approved browser or application. This tool does not authorize an external write.",
  inputSchema: {
    type: "object",
    additionalProperties: false,
    required: ["instruction"],
    properties: {
      instruction: { type: "string", maxLength: 2000 },
      completion_label: { type: "string", maxLength: 100 }
    }
  }
};

export type ManagedInteractionResponseBinding =
  | { kind: "managed_authentication"; targetId: string; verifierId: string }
  | { kind: "managed_user_action" };

export type ManagedInteractionToolRequest = {
  allowsFreeText: false;
  options: [];
  presentation: AgentInteractionPresentation;
  prompt: string;
  protectedLaunchTarget?: CodexManagedAuthenticationTarget["launch"];
  responseBinding: ManagedInteractionResponseBinding;
  type: Extract<AgentInteractionType, "authentication_handoff" | "user_action_required">;
};

type ManagedToolOptions = {
  authHandoffEnabled: boolean;
  eligibleTargets: readonly CodexManagedAuthenticationTarget[];
  userActionEnabled: boolean;
};

export function buildRageniusDynamicToolSpecs(
  options: ManagedToolOptions & { inputEnabled: boolean }
): Array<
  | typeof rageniusInteractionToolSpec
  | typeof rageniusAuthenticationHandoffToolSpec
  | typeof rageniusUserActionToolSpec
> {
  return [
    ...(options.inputEnabled ? [rageniusInteractionToolSpec] : []),
    ...(options.authHandoffEnabled && options.eligibleTargets.length > 0
      ? [rageniusAuthenticationHandoffToolSpec]
      : []),
    ...(options.userActionEnabled ? [rageniusUserActionToolSpec] : [])
  ];
}

export function buildRageniusManagedInteractionGuidance(options: ManagedToolOptions): string {
  const sections: string[] = [];
  if (options.authHandoffEnabled && options.eligibleTargets.length > 0) {
    sections.push([
      "RAGenius managed authentication targets:",
      ...options.eligibleTargets.map((target) => `- ${target.id}: ${target.label}`),
      "Use only the listed target id with `ragenius_request_authentication_handoff`.",
      "Never ask the user to enter credentials, passwords, tokens, or one-time codes in RAGenius."
    ].join("\n"));
  }
  if (options.userActionEnabled) {
    sections.push([
      "RAGenius managed user action:",
      "Use `ragenius_request_user_action` only for a bounded non-secret action in an already approved browser or application.",
      "This tool cannot authorize sending, publishing, deleting, or another external write."
    ].join("\n"));
  }
  return sections.join("\n\n");
}

export function parseRageniusAuthenticationHandoffToolCall(
  value: unknown,
  eligibleTargets: readonly CodexManagedAuthenticationTarget[]
): ManagedInteractionToolRequest {
  const parsed = authenticationHandoffCallSchema.parse(value);
  rejectSecretManagedRequest(parsed.instruction, parsed.completion_label);
  const target = eligibleTargets.find((candidate) => candidate.id === parsed.authentication_target_id);
  if (!target) {
    throw new Error("AUTHENTICATION_TARGET_NOT_APPROVED: The requested authentication target is unavailable.");
  }
  const presentation: AgentInteractionPresentation = {
    completionLabel: parsed.completion_label ?? "Authentication completed",
    launchAvailable: true,
    targetLabel: target.label,
    ...(target.launch.kind === "https_url"
      ? { targetHost: new URL(target.launch.url).hostname }
      : {})
  };
  return {
    allowsFreeText: false,
    options: [],
    presentation,
    prompt: parsed.instruction,
    protectedLaunchTarget: target.launch,
    responseBinding: {
      kind: "managed_authentication",
      targetId: target.id,
      verifierId: target.verifierId
    },
    type: "authentication_handoff"
  };
}

export function parseRageniusUserActionToolCall(value: unknown): ManagedInteractionToolRequest {
  const parsed = userActionCallSchema.parse(value);
  rejectSecretManagedRequest(parsed.instruction, parsed.completion_label);
  if (EXTERNAL_AUTHORIZATION_PATTERN.test(parsed.instruction)) {
    throw new Error("A user action cannot authorize an external write.");
  }
  return {
    allowsFreeText: false,
    options: [],
    presentation: {
      completionLabel: parsed.completion_label ?? "I completed this step"
    },
    prompt: parsed.instruction,
    responseBinding: { kind: "managed_user_action" },
    type: "user_action_required"
  };
}

export function parseRageniusInteractionToolCall(value: unknown): {
  allowsFreeText: boolean;
  options: Array<{ id: string; label: string }>;
  prompt: string;
  type: "clarification" | "selection";
} {
  const parsed = toolCallSchema.parse(value);
  const requestedText = [parsed.question, ...(parsed.options ?? [])].join(" ");
  if (SECRET_REQUEST_PATTERN.test(requestedText)) {
    throw new Error("RAGenius interactions cannot request secret input.");
  }
  const options = (parsed.options ?? []).map((label, index) => ({
    id: `option-${index + 1}`,
    label
  }));
  return {
    allowsFreeText: parsed.allows_free_text,
    options,
    prompt: parsed.question,
    type: options.length > 0 ? "selection" : "clarification"
  };
}

function rejectSecretManagedRequest(instruction: string, completionLabel?: string): void {
  if (isSecretInteractionText(`${instruction} ${completionLabel ?? ""}`)) {
    throw new Error("RAGenius managed interactions cannot request secret input.");
  }
}
