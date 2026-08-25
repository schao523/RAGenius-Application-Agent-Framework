import type { AgentInteractionPresentation } from "./interactive-agent-types.js";

export type McpElicitationErrorCode =
  | "MCP_ELICITATION_UNSUPPORTED"
  | "MCP_ELICITATION_SECRET_INPUT_BLOCKED"
  | "MCP_ELICITATION_SCOPE_MISMATCH"
  | "MCP_ELICITATION_TARGET_BLOCKED";

export class McpElicitationDecodeError extends Error {
  constructor(readonly code: McpElicitationErrorCode, message: string) {
    super(message);
    this.name = "McpElicitationDecodeError";
  }
}

export type NormalizedMcpElicitation = {
  interactionType: "approval" | "clarification" | "selection" | "authentication_handoff";
  prompt: string;
  options: Array<{ id: string; label: string; description?: string }>;
  allowsFreeText: boolean;
  serverName: string;
  threadId: string;
  turnId: string | null;
  providerRequestId: string | number;
  responseBinding:
    | { kind: "approval" }
    | { kind: "field"; propertyName: string }
    | { kind: "authentication_url"; elicitationId: string };
  presentation?: AgentInteractionPresentation;
  protectedLaunchTarget?: { kind: "https_url"; url: string };
};

export type McpElicitationDecodeContext = {
  activeThreadId: string;
  activeTurnId: string | null;
  allowedAuthenticationHosts: readonly string[];
  authorizationBound: boolean;
  providerRequestId: string | number;
};

const SECRET_REQUEST_PATTERN =
  /\b(password|passcode|otp|one[- ]time code|api[- ]?key|token|auth(?:entication)? code|cookie|credential|private key|recovery code|secret)\b/i;
const OBJECT_SCHEMA_KEYS = new Set(["type", "properties", "required", "title", "description"]);
const FIELD_SCHEMA_KEYS = new Set(["type", "enum", "maxLength", "title", "description"]);

export function isSecretInteractionText(value: string): boolean {
  return SECRET_REQUEST_PATTERN.test(value);
}

export function decodeCodexMcpElicitation(
  value: unknown,
  context: McpElicitationDecodeContext
): NormalizedMcpElicitation {
  const params = asRecord(value);
  const threadId = boundedString(params.threadId, 200, "threadId");
  const turnId = params.turnId === null ? null : boundedString(params.turnId, 200, "turnId");
  if (threadId !== context.activeThreadId || turnId !== context.activeTurnId) {
    throw new McpElicitationDecodeError(
      "MCP_ELICITATION_SCOPE_MISMATCH",
      "The elicitation does not belong to the active Codex turn."
    );
  }
  const serverName = boundedString(params.serverName, 200, "serverName");
  const prompt = boundedUtf8String(params.message, 2000, "message");
  const mode = boundedString(params.mode, 30, "mode");
  if (mode === "url") {
    return decodeUrlMode(params, context, { prompt, serverName, threadId, turnId });
  }
  if (mode !== "form" && mode !== "openai/form") {
    throw unsupported("Unsupported MCP elicitation mode.");
  }
  const schema = asRecord(params.requestedSchema);
  rejectUnknownKeys(schema, OBJECT_SCHEMA_KEYS);
  if (schema.type !== "object") throw unsupported("MCP form must use an object schema.");
  const properties = asRecord(schema.properties);
  const entries = Object.entries(properties);
  if (entries.length > 1) throw unsupported("MCP form contains too many fields.");
  validateRequiredProperties(schema.required, entries.map(([name]) => name));
  if (entries.length === 0) {
    requireBoundAuthorization(context);
    rejectSecrets(prompt);
    return normalizedBase({ prompt, serverName, threadId, turnId, context }, {
      interactionType: "approval",
      responseBinding: { kind: "approval" }
    });
  }

  const [propertyName, rawField] = entries[0]!;
  if (!propertyName || propertyName.length > 200) throw unsupported("Invalid MCP form field name.");
  const field = asRecord(rawField);
  rejectUnknownKeys(field, FIELD_SCHEMA_KEYS);
  rejectSecrets([prompt, propertyName, optionalString(field.title), optionalString(field.description)].join(" "));
  if (field.type === "boolean") {
    requireBoundAuthorization(context);
    return normalizedBase({ prompt, serverName, threadId, turnId, context }, {
      interactionType: "approval",
      responseBinding: { kind: "approval" }
    });
  }
  if (field.type !== "string") throw unsupported("Unsupported MCP form field type.");
  if (Array.isArray(field.enum)) {
    if (field.enum.length === 0 || field.enum.length > 20) {
      throw unsupported("MCP selection has an unsupported option count.");
    }
    const labels = field.enum.map((item) => boundedString(item, 200, "enum option"));
    if (new Set(labels).size !== labels.length) throw unsupported("MCP selection options must be unique.");
    rejectSecrets(labels.join(" "));
    return normalizedBase({ prompt, serverName, threadId, turnId, context }, {
      interactionType: "selection",
      options: labels.map((label) => ({ id: label, label })),
      responseBinding: { kind: "field", propertyName }
    });
  }
  if (!Number.isInteger(field.maxLength) || Number(field.maxLength) < 1 || Number(field.maxLength) > 8000) {
    throw unsupported("MCP clarification must have a bounded string length.");
  }
  return normalizedBase({ prompt, serverName, threadId, turnId, context }, {
    interactionType: "clarification",
    allowsFreeText: true,
    responseBinding: { kind: "field", propertyName }
  });
}

export function translateMcpElicitationResponse(
  request: NormalizedMcpElicitation,
  response: Record<string, unknown>
): { action: "accept" | "decline" | "cancel"; content: Record<string, unknown> | null; _meta: null } {
  if (response.kind === "approval" && response.decision === "deny") {
    return { action: "decline", content: null, _meta: null };
  }
  if (
    (response.kind === "approval" && response.decision === "cancel_execution") ||
    (response.kind === "user_action" && response.outcome === "cancelled")
  ) {
    return { action: "cancel", content: null, _meta: null };
  }
  if (request.responseBinding.kind === "approval") {
    if (response.kind !== "approval" || response.decision !== "allow_once") {
      throw unsupported("Approval response does not match elicitation.");
    }
    return { action: "accept", content: {}, _meta: null };
  }
  if (request.responseBinding.kind === "authentication_url") {
    if (response.kind !== "user_action" || response.outcome !== "completed") {
      throw unsupported("Authentication response does not match elicitation.");
    }
    return { action: "accept", content: null, _meta: null };
  }
  if (request.interactionType === "clarification") {
    const text = boundedUtf8String(response.text, 8000, "clarification response");
    return {
      action: "accept",
      content: { [request.responseBinding.propertyName]: text },
      _meta: null
    };
  }
  const ids = Array.isArray(response.option_ids)
    ? response.option_ids.filter((item): item is string => typeof item === "string")
    : [];
  if (ids.length !== 1 || !request.options.some((option) => option.id === ids[0])) {
    throw unsupported("Selection response does not match elicitation options.");
  }
  return {
    action: "accept",
    content: { [request.responseBinding.propertyName]: ids[0] },
    _meta: null
  };
}

function decodeUrlMode(
  params: Record<string, unknown>,
  context: McpElicitationDecodeContext,
  base: { prompt: string; serverName: string; threadId: string; turnId: string | null }
): NormalizedMcpElicitation {
  rejectSecrets(base.prompt);
  const elicitationId = boundedString(params.elicitationId, 200, "elicitationId");
  const rawUrl = boundedUtf8String(params.url, 8192, "url");
  let url: URL;
  try {
    url = new URL(rawUrl);
  } catch {
    throw targetBlocked();
  }
  if (
    url.protocol !== "https:" ||
    url.username ||
    url.password ||
    !context.allowedAuthenticationHosts.includes(url.hostname)
  ) {
    throw targetBlocked();
  }
  return {
    ...normalizedBase({ ...base, context }, {
      interactionType: "authentication_handoff",
      responseBinding: { kind: "authentication_url", elicitationId }
    }),
    presentation: {
      launchAvailable: true,
      targetHost: url.hostname,
      targetLabel: base.serverName
    },
    protectedLaunchTarget: { kind: "https_url", url: rawUrl }
  };
}

function normalizedBase(
  base: {
    context: McpElicitationDecodeContext;
    prompt: string;
    serverName: string;
    threadId: string;
    turnId: string | null;
  },
  values: Pick<NormalizedMcpElicitation, "interactionType" | "responseBinding"> &
    Partial<Pick<NormalizedMcpElicitation, "allowsFreeText" | "options">>
): NormalizedMcpElicitation {
  return {
    interactionType: values.interactionType,
    prompt: base.prompt,
    options: values.options ?? [],
    allowsFreeText: values.allowsFreeText ?? false,
    serverName: base.serverName,
    threadId: base.threadId,
    turnId: base.turnId,
    providerRequestId: base.context.providerRequestId,
    responseBinding: values.responseBinding
  };
}

function requireBoundAuthorization(context: McpElicitationDecodeContext): void {
  if (!context.authorizationBound) {
    throw unsupported("MCP confirmation is not bound to an authorized operation.");
  }
}

function rejectSecrets(value: string): void {
  if (isSecretInteractionText(value)) {
    throw new McpElicitationDecodeError(
      "MCP_ELICITATION_SECRET_INPUT_BLOCKED",
      "MCP elicitation cannot collect secret input."
    );
  }
}

function rejectUnknownKeys(value: Record<string, unknown>, allowed: Set<string>): void {
  if (Object.keys(value).some((key) => !allowed.has(key))) {
    throw unsupported("MCP elicitation contains unsupported schema fields.");
  }
}

function validateRequiredProperties(value: unknown, propertyNames: string[]): void {
  if (value === undefined) return;
  if (
    !Array.isArray(value) ||
    value.some((item) => typeof item !== "string") ||
    new Set(value).size !== value.length ||
    value.some((item) => !propertyNames.includes(item))
  ) {
    throw unsupported("MCP form required fields do not match its properties.");
  }
}

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw unsupported("Expected an object.");
  return value as Record<string, unknown>;
}

function boundedString(value: unknown, maxLength: number, label: string): string {
  if (typeof value !== "string" || !value.trim() || value.length > maxLength) {
    throw unsupported(`Invalid ${label}.`);
  }
  return value.trim();
}

function boundedUtf8String(value: unknown, maxBytes: number, label: string): string {
  const text = boundedString(value, maxBytes, label);
  if (Buffer.byteLength(text, "utf8") > maxBytes) throw unsupported(`Invalid ${label}.`);
  return text;
}

function optionalString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function unsupported(message: string): McpElicitationDecodeError {
  return new McpElicitationDecodeError("MCP_ELICITATION_UNSUPPORTED", message);
}

function targetBlocked(): McpElicitationDecodeError {
  return new McpElicitationDecodeError(
    "MCP_ELICITATION_TARGET_BLOCKED",
    "The authentication target is not approved."
  );
}
