export type OpenClawGatewayEventFrame = {
  event: string;
  payload: unknown;
  seq?: number;
  type: "event";
};

export type OpenClawGatewayEventAcceptance =
  | { accepted: false; duplicate: true }
  | { accepted: true; gap?: { actual: number; expected: number } };

const APPROVAL_EVENTS = new Set([
  "exec.approval.requested",
  "exec.approval.resolved"
]);

export class OpenClawGatewayEventTracker {
  private lastSequence: number | null = null;
  private readonly approvalEvents = new Set<string>();

  accept(frame: OpenClawGatewayEventFrame): OpenClawGatewayEventAcceptance {
    if (typeof frame.seq === "number") {
      if (this.lastSequence !== null && frame.seq <= this.lastSequence) {
        return { accepted: false, duplicate: true };
      }
      const gap = this.lastSequence !== null && frame.seq > this.lastSequence + 1
        ? { expected: this.lastSequence + 1, actual: frame.seq }
        : undefined;
      this.lastSequence = frame.seq;
      return gap ? { accepted: true, gap } : { accepted: true };
    }

    if (APPROVAL_EVENTS.has(frame.event)) {
      const approvalId = stringField(frame.payload, "id");
      if (approvalId) {
        const key = `${approvalId}:${frame.event}`;
        if (this.approvalEvents.has(key)) return { accepted: false, duplicate: true };
        this.approvalEvents.add(key);
        if (this.approvalEvents.size > 4096) {
          const oldest = this.approvalEvents.values().next().value as string | undefined;
          if (oldest) this.approvalEvents.delete(oldest);
        }
      }
    }
    return { accepted: true };
  }

  resetSequence(): void {
    this.lastSequence = null;
  }
}

export function buildOpenClawInteractiveSessionKey(input: {
  agentSessionId: string;
  appId: string;
  sessionId: string;
}): string {
  const parts = [input.appId, input.sessionId, input.agentSessionId].map((value) => {
    const normalized = value.trim();
    if (!/^[A-Za-z0-9_-]+$/.test(normalized)) {
      throw new Error(`Unsafe OpenClaw interactive session key component: ${value}`);
    }
    return normalized;
  });
  return `ragenius:${parts.join(":")}`;
}

export function isGatewayEventFrame(value: unknown): value is OpenClawGatewayEventFrame {
  if (!isRecord(value)) return false;
  return value.type === "event" && typeof value.event === "string" && "payload" in value;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function recordField(value: unknown, key: string): Record<string, unknown> {
  if (!isRecord(value)) return {};
  const field = value[key];
  return isRecord(field) ? field : {};
}

export function stringField(value: unknown, key: string): string {
  if (!isRecord(value)) return "";
  return typeof value[key] === "string" ? value[key] : "";
}

export function numberField(value: unknown, key: string): number | undefined {
  if (!isRecord(value)) return undefined;
  return typeof value[key] === "number" && Number.isFinite(value[key])
    ? value[key]
    : undefined;
}
