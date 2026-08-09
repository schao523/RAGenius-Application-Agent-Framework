import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";

import type { FastifyInstance } from "fastify";

import { buildApp } from "../../src/app.js";
import { computeAgentSkillProjectionDigest } from "../../src/api/schemas/agent-skill.schema.js";
import { getEnv } from "../../src/config/env.js";
import { buildRuntimeConfig } from "../../src/config/runtime-config.js";
import { InMemoryAgentSkillProjectionStore } from "../../src/core/agent-skills/agent-skill-projection-store.js";
import type { ProjectedAgentSkillGovernance } from "../../src/core/agent-skills/agent-skill-types.js";

function item(
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
    description: "A selectable skill",
    direct_tool_dispatch: false,
    display_name: "Selectable Skill",
    model_visible: true,
    protected_locator_ref: "secret-source-ref",
    provider_skill_name: "selectable-skill",
    provider_skill_reference: "selectable-skill",
    runtime_target_id: "codex-local-default",
    source_enabled: true,
    source_id: "source-1",
    user_invocable: true,
    ...overrides
  };
}

function projection(items: ProjectedAgentSkillGovernance[], revision = 42) {
  const unsigned = {
    builder_instance_id: "builder-primary",
    generated_at: "2026-08-04T00:00:00.000Z",
    items,
    revision
  };
  return {
    ...unsigned,
    digest: computeAgentSkillProjectionDigest(unsigned)
  };
}

function runtimeConfig(maxItems = "10000") {
  return buildRuntimeConfig(getEnv({
    AGENT_SKILL_PROJECTION_MAX_BYTES: "8388608",
    AGENT_SKILL_PROJECTION_MAX_ITEMS: maxItems,
    AGENT_SKILL_TRUSTED_BUILDER_INSTANCE_ID: "builder-primary",
    DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
    MCP_SERVERS_JSON: "[]",
    RAGENIUS_EXECUTION_SERVICE_AUTH_REQUIRED: "true",
    RAGENIUS_EXECUTION_SERVICE_CREDENTIALS_JSON: JSON.stringify([
      {
        service_id: "ragenius_app",
        token: "app-token",
        scopes: ["execution", "agent_skills:read"]
      },
      {
        service_id: "ragenius_builder",
        token: "builder-token",
        scopes: ["agent_skills:admin"]
      }
    ])
  }));
}

describe("agent skill projection routes", () => {
  let app: FastifyInstance | undefined;

  afterEach(async () => {
    await app?.close();
    app = undefined;
  });

  it("returns an unavailable empty inventory before first publication", async () => {
    app = buildApp(
      { agentSkillProjectionStore: new InMemoryAgentSkillProjectionStore() },
      runtimeConfig()
    );

    const response = await app.inject({
      method: "GET",
      url: "/v1/agent-skills/inventory?app_id=app-1&backend=codex_cli",
      headers: { authorization: "Bearer app-token" }
    });

    assert.equal(response.statusCode, 200);
    assert.deepEqual(response.json(), {
      inventory_revision: null,
      items: [],
      projection_status: "unavailable"
    });
  });

  it("returns opaque Codex source options without configured paths", async () => {
    const config = runtimeConfig();
    config.agentSkills.codex.sourceOptions = [{
      display_name: "Administrator Codex Skills",
      discovery_mode: "directory",
      path: "C:\\Users\\Administrator\\.codex\\skills",
      precedence: 100,
      protected_locator_ref: "codex-source-ref-1",
      runtime_target_id: "codex-local-default"
    }];
    app = buildApp(
      { agentSkillProjectionStore: new InMemoryAgentSkillProjectionStore() },
      config
    );

    const response = await app.inject({
      method: "GET",
      url: "/v1/admin/agent-skills/source-options",
      headers: { authorization: "Bearer builder-token" }
    });

    assert.equal(response.statusCode, 200);
    assert.deepEqual(response.json().items, [{
      backend: "codex_cli",
      display_name: "Administrator Codex Skills",
      precedence: 100,
      protected_locator_ref: "codex-source-ref-1",
      runtime_target_id: "codex-local-default",
      source_kind: "codex_directory"
    }]);
    assert.equal(JSON.stringify(response.json()).includes("C:\\\\Users"), false);
  });

  it("returns opaque OpenClaw targets without WSL details or skill roots", async () => {
    const config = runtimeConfig();
    config.agentSkills.openClaw.targets = [{
      agent_id: "main",
      display_name: "OpenClaw Main",
      protected_locator_ref: "openclaw-main-ref",
      runtime_target_id: "openclaw-main",
      skill_roots: ["/home/openclaw/.openclaw/skills"],
      wsl_distro: "OpenClawGateway"
    }];
    app = buildApp(
      { agentSkillProjectionStore: new InMemoryAgentSkillProjectionStore() },
      config
    );

    const response = await app.inject({
      method: "GET",
      url: "/v1/admin/agent-skills/source-options",
      headers: { authorization: "Bearer builder-token" }
    });

    assert.equal(response.statusCode, 200);
    assert.deepEqual(response.json().items, [{
      backend: "openclaw_cli",
      display_name: "OpenClaw Main",
      precedence: 100,
      protected_locator_ref: "openclaw-main-ref",
      runtime_target_id: "openclaw-main",
      source_kind: "openclaw_agent_inventory"
    }]);
    assert.equal(JSON.stringify(response.json()).includes("OpenClawGateway"), false);
    assert.equal(JSON.stringify(response.json()).includes("/home/openclaw"), false);
  });

  it("publishes idempotently and returns only redacted scoped inventory", async () => {
    app = buildApp(
      { agentSkillProjectionStore: new InMemoryAgentSkillProjectionStore() },
      runtimeConfig()
    );
    const payload = projection([
      item(),
      item({ agent_skill_id: "other-app", app_id: "app-2" }),
      item({
        agent_skill_id: "disabled",
        binding_enabled: false,
        provider_skill_name: "disabled"
      })
    ]);

    const publish = await app.inject({
      method: "PUT",
      url: "/v1/admin/agent-skills/governance-projection",
      headers: { authorization: "Bearer builder-token" },
      payload
    });
    const repeated = await app.inject({
      method: "PUT",
      url: "/v1/admin/agent-skills/governance-projection",
      headers: { authorization: "Bearer builder-token" },
      payload
    });
    const inventory = await app.inject({
      method: "GET",
      url: "/v1/agent-skills/inventory?app_id=app-1&backend=codex_cli",
      headers: { authorization: "Bearer app-token" }
    });

    assert.equal(publish.statusCode, 200);
    assert.equal(publish.json().idempotent, false);
    assert.equal(repeated.statusCode, 200);
    assert.equal(repeated.json().idempotent, true);
    assert.equal(inventory.statusCode, 200);
    assert.equal(inventory.json().projection_status, "active");
    assert.equal(inventory.json().items.length, 1);
    assert.deepEqual(inventory.json().items[0], {
      agent_skill_id: "agent-skill-1",
      approved_fingerprint: "sha256:v1:abc",
      availability: "available",
      backend: "codex_cli",
      description: "A selectable skill",
      display_name: "Selectable Skill",
      provider_skill_name: "selectable-skill"
    });
    assert.equal("protected_locator_ref" in inventory.json().items[0], false);
  });

  it("enforces caller scope and trusted Builder identity", async () => {
    app = buildApp(
      { agentSkillProjectionStore: new InMemoryAgentSkillProjectionStore() },
      runtimeConfig()
    );

    const appPublish = await app.inject({
      method: "PUT",
      url: "/v1/admin/agent-skills/governance-projection",
      headers: { authorization: "Bearer app-token" },
      payload: projection([])
    });
    const wrongBuilder = projection([]);
    wrongBuilder.builder_instance_id = "builder-secondary";
    wrongBuilder.digest = computeAgentSkillProjectionDigest(wrongBuilder);
    const wrongBuilderPublish = await app.inject({
      method: "PUT",
      url: "/v1/admin/agent-skills/governance-projection",
      headers: { authorization: "Bearer builder-token" },
      payload: wrongBuilder
    });
    const builderInventory = await app.inject({
      method: "GET",
      url: "/v1/agent-skills/inventory?app_id=app-1&backend=codex_cli",
      headers: { authorization: "Bearer builder-token" }
    });

    assert.equal(appPublish.statusCode, 403);
    assert.equal(appPublish.json().error.code, "SERVICE_SCOPE_REQUIRED");
    assert.equal(wrongBuilderPublish.statusCode, 403);
    assert.equal(wrongBuilderPublish.json().error.code, "UNTRUSTED_BUILDER_INSTANCE");
    assert.equal(builderInventory.statusCode, 403);
  });

  it("rejects digest mismatch and item-limit overflow", async () => {
    app = buildApp(
      { agentSkillProjectionStore: new InMemoryAgentSkillProjectionStore() },
      runtimeConfig("1")
    );
    const invalidDigest = projection([]);
    invalidDigest.digest = `sha256:${"0".repeat(64)}`;

    const digestResponse = await app.inject({
      method: "PUT",
      url: "/v1/admin/agent-skills/governance-projection",
      headers: { authorization: "Bearer builder-token" },
      payload: invalidDigest
    });
    const limitResponse = await app.inject({
      method: "PUT",
      url: "/v1/admin/agent-skills/governance-projection",
      headers: { authorization: "Bearer builder-token" },
      payload: projection([item(), item({ agent_skill_id: "agent-skill-2" })])
    });

    assert.equal(digestResponse.statusCode, 400);
    assert.equal(
      digestResponse.json().error.code,
      "AGENT_SKILL_PROJECTION_DIGEST_MISMATCH"
    );
    assert.equal(limitResponse.statusCode, 413);
    assert.equal(limitResponse.json().error.code, "AGENT_SKILL_PROJECTION_TOO_LARGE");
  });
});
