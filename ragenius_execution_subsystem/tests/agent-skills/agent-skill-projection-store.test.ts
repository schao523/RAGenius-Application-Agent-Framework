import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { InMemoryAgentSkillProjectionStore } from "../../src/core/agent-skills/agent-skill-projection-store.js";
import type {
  AgentSkillGovernanceProjection,
  ProjectedAgentSkillGovernance
} from "../../src/core/agent-skills/agent-skill-types.js";

function binding(
  overrides: Partial<ProjectedAgentSkillGovernance> = {}
): ProjectedAgentSkillGovernance {
  return {
    agent_skill_id: "agent-skill-1",
    app_id: "app-1",
    approval_state: "approved",
    approved_fingerprint: "sha256:v1:abc",
    backend: "codex_cli",
    binding_enabled: true,
    current_fingerprint: "sha256:v1:abc",
    description: "A test skill",
    direct_tool_dispatch: false,
    display_name: "Test Skill",
    model_visible: true,
    protected_locator_ref: "codex-source-ref-1",
    provider_skill_name: "test-skill",
    runtime_target_id: "codex-local-default",
    source_enabled: true,
    source_id: "source-1",
    user_invocable: true,
    ...overrides
  };
}

function snapshot(
  revision: number,
  digest: string,
  items: ProjectedAgentSkillGovernance[]
): AgentSkillGovernanceProjection {
  return {
    builder_instance_id: "builder-primary",
    digest,
    generated_at: "2026-08-04T00:00:00.000Z",
    items,
    revision
  };
}

describe("agent skill projection store", () => {
  it("atomically replaces the active complete snapshot", async () => {
    const store = new InMemoryAgentSkillProjectionStore();
    const codex = binding();
    const openclaw = binding({
      agent_skill_id: "agent-skill-2",
      backend: "openclaw_cli",
      provider_skill_name: "openclaw-test",
      runtime_target_id: "openclaw-main",
      source_id: "source-2"
    });

    await store.publish(snapshot(41, "sha256:a", [codex, openclaw]));
    await store.publish(snapshot(42, "sha256:b", [codex]));

    assert.deepEqual(await store.listForApp("app-1", "codex_cli"), [codex]);
    assert.deepEqual(await store.listForApp("app-1", "openclaw_cli"), []);
    const active = await store.getActiveRevision();
    assert.ok(active);
    assert.match(active.received_at, /^2026-/);
    assert.deepEqual({ ...active, received_at: undefined }, {
      builder_instance_id: "builder-primary",
      digest: "sha256:b",
      generated_at: "2026-08-04T00:00:00.000Z",
      item_count: 1,
      received_at: undefined,
      revision: 42
    });
  });

  it("accepts an exact repeat idempotently", async () => {
    const store = new InMemoryAgentSkillProjectionStore();
    const projection = snapshot(42, "sha256:a", [binding()]);

    const first = await store.publish(projection);
    const repeated = await store.publish(projection);

    assert.equal(first.idempotent, false);
    assert.equal(repeated.idempotent, true);
    assert.equal(repeated.received_at, first.received_at);
  });

  it("rejects revision rollback and same-revision digest conflict", async () => {
    const store = new InMemoryAgentSkillProjectionStore();
    await store.publish(snapshot(42, "sha256:a", [binding()]));

    await assert.rejects(
      () => store.publish(snapshot(41, "sha256:b", [])),
      /REVISION_ROLLBACK/
    );
    await assert.rejects(
      () => store.publish(snapshot(42, "sha256:c", [])),
      /REVISION_CONFLICT/
    );
  });

  it("isolates lookups by app and backend", async () => {
    const store = new InMemoryAgentSkillProjectionStore();
    const appOne = binding();
    const appTwo = binding({ app_id: "app-2" });
    await store.publish(snapshot(42, "sha256:a", [appOne, appTwo]));

    assert.deepEqual(await store.listForApp("app-1", "codex_cli"), [appOne]);
    assert.deepEqual(await store.listForApp("app-1", "openclaw_cli"), []);
    assert.deepEqual(await store.getForApp("app-1", "agent-skill-1"), appOne);
    assert.deepEqual(await store.getForApp("app-3", "agent-skill-1"), null);
  });
});
