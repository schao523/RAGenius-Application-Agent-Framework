import { z } from "zod";

const toolCallSchema = z.object({
  question: z.string().trim().min(1).max(2000),
  options: z.array(z.string().trim().min(1).max(200)).max(20).optional(),
  allows_free_text: z.boolean().optional().default(false)
}).strict();

const SECRET_REQUEST_PATTERN =
  /\b(password|passcode|otp|one[- ]time code|api[- ]?key|token|auth(?:entication)? code|cookie|credential|private key|secret)\b/i;

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
