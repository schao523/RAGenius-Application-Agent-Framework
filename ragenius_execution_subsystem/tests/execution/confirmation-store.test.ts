import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { InMemoryConfirmationStore } from "../../src/core/execution/confirmation-store.js";

describe("in-memory confirmation store", () => {
  it("atomically claims a pending confirmation once", async () => {
    const store = new InMemoryConfirmationStore();
    const scope = {
      appId: "app_001",
      confirmationId: "confirmation_001",
      executionId: "execution_001",
      sessionId: "sess_001"
    };
    await store.create({
      ...scope,
      expiresAt: new Date("2026-07-24T00:01:00.000Z"),
      policySnapshot: { permission_scope: "agent.external_write" }
    });

    const [first, second] = await Promise.all([
      store.claim(scope, new Date("2026-07-24T00:00:00.000Z")),
      store.claim(scope, new Date("2026-07-24T00:00:00.000Z"))
    ]);

    assert.equal(first.outcome, "claimed");
    assert.equal(second.outcome, "running");
    const completed = await store.finish(
      scope,
      "completed",
      new Date("2026-07-24T00:00:01.000Z")
    );
    assert.equal(completed?.status, "completed");
    assert.equal(
      (
        await store.claim(scope, new Date("2026-07-24T00:00:02.000Z"))
      ).outcome,
      "terminal"
    );
  });

  it("expires pending confirmations and enforces complete scope", async () => {
    const store = new InMemoryConfirmationStore();
    const scope = {
      appId: "app_001",
      confirmationId: "confirmation_001",
      executionId: "execution_001",
      sessionId: "sess_001"
    };
    await store.create({
      ...scope,
      expiresAt: new Date("2026-07-24T00:00:01.000Z"),
      policySnapshot: {}
    });

    assert.equal(
      (
        await store.claim(
          { ...scope, appId: "app_002" },
          new Date("2026-07-24T00:00:02.000Z")
        )
      ).outcome,
      "not_found"
    );
    assert.equal(
      (
        await store.claim(scope, new Date("2026-07-24T00:00:02.000Z"))
      ).outcome,
      "expired"
    );
  });
});
