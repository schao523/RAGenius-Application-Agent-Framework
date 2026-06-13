import type { LogEvent } from "./logger.js";

export interface AuditRecord extends LogEvent {
  executionId: string | null;
  appId: string;
  sessionId: string;
  skillId: string;
}

export function createAuditRecord(record: AuditRecord): AuditRecord {
  return record;
}
