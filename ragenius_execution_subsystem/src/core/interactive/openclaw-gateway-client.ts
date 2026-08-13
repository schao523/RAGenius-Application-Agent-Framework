import { randomUUID } from "node:crypto";
import WebSocket from "ws";

import {
  isGatewayEventFrame,
  isRecord,
  OpenClawGatewayEventTracker,
  recordField,
  stringField
} from "./openclaw-gateway-events.js";

export interface OpenClawGatewayHello {
  protocolVersion: number;
  scopes: string[];
  serverVersion: string;
}

export interface OpenClawGatewayClientConfig {
  credential: string;
  gatewayUrl: string;
  maxMessageBytes: number;
  reconnectBaseDelayMs: number;
  reconnectMaxAttempts: number;
  rpcTimeoutMs: number;
  scopes: string[];
}

export type OpenClawGatewayRequestFrame = {
  id: string;
  method: string;
  params?: unknown;
  type: "req";
};

type GatewaySocket = {
  addEventListener(
    type: "open" | "close" | "error" | "message",
    listener: (event: { data?: unknown }) => void
  ): void;
  close(): void;
  send(data: string): void;
};

type GatewaySocketConstructor = new (url: string) => GatewaySocket;

type PendingRequest = {
  reject(error: Error): void;
  resolve(value: unknown): void;
  timeout: NodeJS.Timeout;
};

export function createOpenClawGatewayRequest(
  method: string,
  params?: unknown
): OpenClawGatewayRequestFrame {
  return {
    type: "req",
    id: randomUUID(),
    method,
    ...(params === undefined ? {} : { params })
  };
}

export function buildOpenClawConnectParams(input: {
  credential: string;
  scopes: string[];
}): Record<string, unknown> {
  return {
    minProtocol: 4,
    maxProtocol: 4,
    client: {
      id: "ragenius-execution-subsystem",
      displayName: "RAGenius Execution Subsystem",
      version: "0.1.0",
      platform: "windows",
      mode: "operator"
    },
    caps: [],
    auth: { token: input.credential },
    role: "operator",
    scopes: [...input.scopes]
  };
}

export function redactOpenClawGatewayDiagnostic(
  value: unknown,
  credential: string
): unknown {
  if (typeof value === "string") {
    return credential ? value.replaceAll(credential, "[REDACTED]") : value;
  }
  if (Array.isArray(value)) {
    return value.map((item) => redactOpenClawGatewayDiagnostic(item, credential));
  }
  if (isRecord(value)) {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        key,
        /token|credential|secret/i.test(key)
          ? "[REDACTED]"
          : redactOpenClawGatewayDiagnostic(item, credential)
      ])
    );
  }
  return value;
}

export class OpenClawGatewayClient {
  private socket: GatewaySocket | null = null;
  private helloValue: OpenClawGatewayHello | null = null;
  private readonly pending = new Map<string, PendingRequest>();
  private readonly tracker = new OpenClawGatewayEventTracker();
  private readonly eventHandlers = new Set<(event: Record<string, unknown>) => Promise<void>>();
  private readonly gapHandlers = new Set<(gap: { actual: number; expected: number }) => Promise<void>>();
  private readonly closeHandlers = new Set<(error?: Error) => Promise<void>>();
  private messageQueue: Promise<void> = Promise.resolve();

  constructor(
    private readonly config: OpenClawGatewayClientConfig,
    private readonly Socket: GatewaySocketConstructor = WebSocket as unknown as GatewaySocketConstructor
  ) {
    assertSafeGatewayUrl(config.gatewayUrl);
    if (!config.credential.trim()) throw new Error("OpenClaw Gateway credential is required.");
    if (!Socket) throw new Error("The Node.js WebSocket runtime is unavailable.");
  }

  get hello(): OpenClawGatewayHello {
    if (!this.helloValue) throw new Error("OpenClaw Gateway is not connected.");
    return this.helloValue;
  }

  async connect(): Promise<this> {
    await this.openSocket();
    return this;
  }

  async request(method: string, params?: unknown): Promise<unknown> {
    const socket = this.socket;
    if (!socket) throw new Error("OpenClaw Gateway is not connected.");
    const frame = createOpenClawGatewayRequest(method, params);
    const result = new Promise<unknown>((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(frame.id);
        reject(new Error(`OpenClaw Gateway request timed out: ${method}`));
      }, this.config.rpcTimeoutMs);
      this.pending.set(frame.id, { reject, resolve, timeout });
    });
    socket.send(JSON.stringify(frame));
    return result;
  }

  onEvent(handler: (event: Record<string, unknown>) => Promise<void>): void {
    this.eventHandlers.add(handler);
  }

  onGap(handler: (gap: { actual: number; expected: number }) => Promise<void>): void {
    this.gapHandlers.add(handler);
  }

  onClose(handler: (error?: Error) => Promise<void>): void {
    this.closeHandlers.add(handler);
  }

  async reconnect(): Promise<OpenClawGatewayHello> {
    this.socket?.close();
    this.socket = null;
    this.helloValue = null;
    this.tracker.resetSequence();
    let lastError: Error | undefined;
    for (let attempt = 0; attempt < this.config.reconnectMaxAttempts; attempt += 1) {
      if (attempt > 0) {
        await delay(this.config.reconnectBaseDelayMs * 2 ** (attempt - 1));
      }
      try {
        await this.openSocket();
        return this.hello;
      } catch (error) {
        lastError = asError(error);
      }
    }
    throw lastError ?? new Error("OpenClaw Gateway reconnect failed.");
  }

  async close(): Promise<void> {
    this.socket?.close();
    this.socket = null;
    this.rejectPending(new Error("OpenClaw Gateway connection closed."));
  }

  private async openSocket(): Promise<void> {
    const socket = new this.Socket(this.config.gatewayUrl);
    this.socket = socket;
    await new Promise<void>((resolve, reject) => {
      let settled = false;
      const timeout = setTimeout(() => {
        if (!settled) reject(new Error("OpenClaw Gateway connection timed out."));
      }, this.config.rpcTimeoutMs);
      socket.addEventListener("open", () => undefined);
      socket.addEventListener("error", () => {
        if (!settled) {
          settled = true;
          clearTimeout(timeout);
          reject(new Error("OpenClaw Gateway WebSocket connection failed."));
        }
      });
      socket.addEventListener("close", () => {
        this.socket = null;
        this.rejectPending(new Error("OpenClaw Gateway disconnected."));
        if (!settled) {
          settled = true;
          clearTimeout(timeout);
          reject(new Error("OpenClaw Gateway closed before authentication."));
        } else {
          void this.notifyClose();
        }
      });
      socket.addEventListener("message", (event) => {
        const text = typeof event.data === "string" ? event.data : String(event.data ?? "");
        if (Buffer.byteLength(text, "utf8") > this.config.maxMessageBytes) {
          socket.close();
          if (!settled) reject(new Error("OpenClaw Gateway message exceeded the configured bound."));
          return;
        }
        this.messageQueue = this.messageQueue.then(async () => {
          const frame = parseGatewayFrame(text);
          if (!settled && isGatewayEventFrame(frame) && frame.event === "connect.challenge") {
            void this.sendConnect(socket).then((response) => {
              this.helloValue = normalizeHello(response);
              settled = true;
              clearTimeout(timeout);
              resolve();
            }).catch((error) => {
              settled = true;
              clearTimeout(timeout);
              reject(asError(error));
            });
            return;
          }
          await this.consumeFrame(frame);
        }).catch((error) => {
          if (!settled) {
            settled = true;
            clearTimeout(timeout);
            reject(asError(error));
          }
        });
      });
    });
  }

  private async sendConnect(socket: GatewaySocket): Promise<unknown> {
    const frame = createOpenClawGatewayRequest(
      "connect",
      buildOpenClawConnectParams({
        credential: this.config.credential,
        scopes: this.config.scopes
      })
    );
    const result = new Promise<unknown>((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(frame.id);
        reject(new Error("OpenClaw Gateway authentication timed out."));
      }, this.config.rpcTimeoutMs);
      this.pending.set(frame.id, { reject, resolve, timeout });
    });
    socket.send(JSON.stringify(frame));
    return result;
  }

  private async consumeFrame(frame: Record<string, unknown>): Promise<void> {
    if (frame.type === "res") {
      const id = stringField(frame, "id");
      const pending = this.pending.get(id);
      if (!pending) return;
      clearTimeout(pending.timeout);
      this.pending.delete(id);
      if (frame.ok === false) {
        pending.reject(new Error(
          gatewayErrorMessage(frame).replaceAll(this.config.credential, "[REDACTED]")
        ));
      } else {
        pending.resolve(frame.payload);
      }
      return;
    }
    if (!isGatewayEventFrame(frame)) return;
    const acceptance = this.tracker.accept(frame);
    if (!acceptance.accepted) return;
    if (acceptance.gap) {
      for (const handler of this.gapHandlers) await handler(acceptance.gap);
    }
    for (const handler of this.eventHandlers) await handler(frame);
  }

  private rejectPending(error: Error): void {
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timeout);
      pending.reject(error);
    }
    this.pending.clear();
  }

  private async notifyClose(): Promise<void> {
    for (const handler of this.closeHandlers) await handler();
  }
}

function parseGatewayFrame(text: string): Record<string, unknown> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error("OpenClaw Gateway returned malformed JSON.");
  }
  if (!isRecord(parsed)) throw new Error("OpenClaw Gateway frame must be an object.");
  return parsed;
}

function normalizeHello(value: unknown): OpenClawGatewayHello {
  const payload = isRecord(value) ? value : {};
  const server = recordField(payload, "server");
  const auth = recordField(payload, "auth");
  const protocolVersion = typeof payload.protocol === "number"
    ? payload.protocol
    : typeof payload.protocolVersion === "number" ? payload.protocolVersion : 4;
  const serverVersion = stringField(server, "version") || stringField(payload, "version");
  const scopes = Array.isArray(auth.scopes)
    ? auth.scopes.filter((scope): scope is string => typeof scope === "string")
    : Array.isArray(payload.scopes)
      ? payload.scopes.filter((scope): scope is string => typeof scope === "string")
      : [];
  if (!serverVersion) throw new Error("OpenClaw Gateway connect response omitted server version.");
  return { protocolVersion, scopes, serverVersion };
}

function gatewayErrorMessage(frame: Record<string, unknown>): string {
  const error = recordField(frame, "error");
  return stringField(error, "message") || stringField(frame, "error") || "OpenClaw Gateway request failed.";
}

function assertSafeGatewayUrl(value: string): void {
  const url = new URL(value);
  if (url.protocol !== "ws:" && url.protocol !== "wss:") {
    throw new Error("OpenClaw Gateway URL must use ws or wss.");
  }
  if (url.protocol === "ws:" && !["127.0.0.1", "localhost", "::1"].includes(url.hostname)) {
    throw new Error("Unencrypted OpenClaw Gateway connections must be loopback-only.");
  }
}

function asError(value: unknown): Error {
  return value instanceof Error ? value : new Error(String(value));
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
