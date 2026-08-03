import { randomUUID } from "node:crypto";

import type {
  ConfirmationClaimResult,
  ConfirmationRecord,
  ConfirmationScope,
  ConfirmationStore
} from "./confirmation-store.js";

export interface ConfirmationMetadata {
  confirmation_expires_at: string;
  confirmation_id: string;
  confirmation_state: ConfirmationRecord["status"];
}

export interface ApprovedConfirmation {
  confirmationId: string;
  confirmedAt?: string;
  policySnapshot: Record<string, unknown>;
}

export class ConfirmationService {
  constructor(
    private readonly store: ConfirmationStore,
    private readonly options: {
      clock?: () => Date;
      createId?: () => string;
      ttlMs: number;
    }
  ) {}

  async issue(input: {
    appId: string;
    executionId: string;
    policySnapshot: Record<string, unknown>;
    sessionId: string;
  }): Promise<ConfirmationMetadata> {
    const now = this.now();
    const record = await this.store.create({
      appId: input.appId,
      confirmationId:
        this.options.createId?.() ??
        `confirmation_${randomUUID().replace(/-/g, "").slice(0, 16)}`,
      executionId: input.executionId,
      expiresAt: new Date(now.getTime() + this.options.ttlMs),
      policySnapshot: input.policySnapshot,
      sessionId: input.sessionId
    });
    return this.metadata(record);
  }

  claim(scope: ConfirmationScope): Promise<ConfirmationClaimResult> {
    return this.store.claim(scope, this.now());
  }

  finish(
    scope: ConfirmationScope,
    status: "completed" | "failed"
  ): Promise<ConfirmationRecord | null> {
    return this.store.finish(scope, status, this.now());
  }

  metadata(record: ConfirmationRecord): ConfirmationMetadata {
    return {
      confirmation_expires_at: record.expiresAt.toISOString(),
      confirmation_id: record.confirmationId,
      confirmation_state: record.status
    };
  }

  private now(): Date {
    return this.options.clock?.() ?? new Date();
  }
}
