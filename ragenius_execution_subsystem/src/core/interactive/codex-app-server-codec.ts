import type { InteractiveProviderEvent } from "./interactive-agent-adapter.js";

export class CodexProtocolError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CodexProtocolError";
  }
}

export class CodexAppServerCodec {
  constructor(private readonly config: {
    maxLineBytes: number;
    maxDeltaBytes?: number;
  }) {}

  encodeRequest(
    id: string | number,
    method: string,
    params?: unknown
  ): string {
    return `${JSON.stringify({
      jsonrpc: "2.0",
      id,
      method,
      ...(params !== undefined ? { params } : {})
    })}\n`;
  }

  encodeNotification(method: string, params?: unknown): string {
    return `${JSON.stringify({
      jsonrpc: "2.0",
      method,
      ...(params !== undefined ? { params } : {})
    })}\n`;
  }

  encodeResponse(id: string | number, result: unknown): string {
    return `${JSON.stringify({ jsonrpc: "2.0", id, result })}\n`;
  }

  decode(line: string): Record<string, unknown> {
    if (Buffer.byteLength(line, "utf8") > this.config.maxLineBytes) {
      throw new CodexProtocolError("Codex protocol line exceeds the configured maximum.");
    }
    try {
      const parsed: unknown = JSON.parse(line.trim());
      if (!isRecord(parsed)) {
        throw new CodexProtocolError("Codex protocol message must be an object.");
      }
      return parsed;
    } catch (error) {
      if (error instanceof CodexProtocolError) throw error;
      throw new CodexProtocolError("Codex app-server emitted malformed JSON.");
    }
  }

  normalizeNotification(message: Record<string, unknown>): InteractiveProviderEvent | null {
    const method = stringValue(message.method);
    const params = recordValue(message.params);
    if (method.includes("reasoning")) return null;
    if (method === "turn/started") {
      return { type: "run_started", payload: publicTurnPayload(params) };
    }
    if (method === "turn/completed") {
      const turn = recordValue(params.turn);
      const status = stringValue(turn.status);
      return {
        type: status === "interrupted" ? "run_cancelled" : "run_completed",
        payload: {
          status: status === "failed" ? "failed" : "completed",
          ...(stringValue(turn.error) ? { error: stringValue(turn.error) } : {})
        }
      };
    }
    if (method === "item/agentMessage/delta") {
      const bounded = boundedTail(stringValue(params.delta), this.config.maxDeltaBytes ?? 16_384);
      return {
        type: "message_delta",
        payload: {
          delta: bounded.value,
          ...(bounded.truncated ? { truncated: true } : {})
        }
      };
    }
    if (method === "item/completed") {
      return { type: "message_completed", payload: publicItemPayload(params) };
    }
    if (method === "item/started") {
      return { type: "tool_started", payload: publicItemPayload(params) };
    }
    if (method === "error") {
      return { type: "error", payload: { message: publicMessage(params) } };
    }
    if (method === "warning") {
      return { type: "warning", payload: { message: publicMessage(params) } };
    }
    return {
      type: "warning",
      payload: { code: "CODEX_UNKNOWN_METHOD", method }
    };
  }
}

function boundedTail(value: string, maxBytes: number): { value: string; truncated: boolean } {
  const bytes = Buffer.from(value, "utf8");
  if (bytes.byteLength <= maxBytes) return { value, truncated: false };
  return {
    value: bytes.subarray(bytes.byteLength - maxBytes).toString("utf8"),
    truncated: true
  };
}

function publicTurnPayload(params: Record<string, unknown>): Record<string, unknown> {
  const turn = recordValue(params.turn);
  return {
    ...(stringValue(params.threadId) ? { thread_id: stringValue(params.threadId) } : {}),
    ...(stringValue(turn.id) ? { turn_id: stringValue(turn.id) } : {})
  };
}

function publicItemPayload(params: Record<string, unknown>): Record<string, unknown> {
  const item = recordValue(params.item);
  return {
    ...(stringValue(item.id) ? { item_id: stringValue(item.id) } : {}),
    ...(stringValue(item.type) ? { item_type: stringValue(item.type) } : {})
  };
}

function publicMessage(params: Record<string, unknown>): string {
  return stringValue(params.message) || "Codex app-server reported a provider event.";
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function recordValue(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

export function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}
