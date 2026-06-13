import { redactSensitiveValue } from "../../utils/redact.js";

export interface LogEvent {
  level: "debug" | "info" | "warn" | "error" | "audit";
  eventType: string;
  message: string;
  summary?: Record<string, unknown>;
}

export class ExecutionLogger {
  createEvent(event: LogEvent): LogEvent {
    const normalizedEvent: LogEvent = {
      level: event.level,
      eventType: event.eventType,
      message: event.message
    };

    if (event.summary) {
      normalizedEvent.summary = redactSensitiveValue(event.summary);
    }

    return normalizedEvent;
  }

  summarizeExecution(options: {
    executionId: string | null;
    skillId: string;
    stepCount: number;
    toolCallCount: number;
    status: string;
  }): string {
    return `Execution ${options.executionId ?? "pending"} for ${options.skillId} ${options.status} after ${options.stepCount} steps and ${options.toolCallCount} tool calls.`;
  }
}
