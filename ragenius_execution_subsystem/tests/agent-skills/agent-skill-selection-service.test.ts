import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  executeAgentRequestSchema,
  type ExecuteAgentRequest
} from "../../src/api/schemas/execution-request.schema.js";
import { InMemoryAgentSkillProjectionStore } from "../../src/core/agent-skills/agent-skill-projection-store.js";
import { AgentSkillSelectionService } from "../../src/core/agent-skills/agent-skill-selection-service.js";
import type {
  AgentSkillCatalogCandidate,
  ProjectedAgentSkillGovernance
} from "../../src/core/agent-skills/agent-skill-types.js";

function projected(
  overrides: Partial<ProjectedAgentSkillGovernance> = {}
): ProjectedAgentSkillGovernance {
  return {
    agent_skill_id: "agent-skill-1",
    app_id: "app-1",
    approval_state: "approved",
    approved_fingerprint: "sha256:v1:approved",
    backend: "codex_cli",
    binding_enabled: true,
    current_fingerprint: "sha256:v1:approved",
    description: "Approved skill",
    direct_tool_dispatch: false,
    display_name: "Approved Skill",
    model_visible: true,
    protected_locator_ref: "codex-source-ref-1",
    provider_skill_name: "approved-skill",
    runtime_target_id: "codex-local-default",
    source_enabled: true,
    source_id: "source-1",
    user_invocable: true,
    ...overrides
  };
}

function observed(
  record: ProjectedAgentSkillGovernance,
  fingerprint = record.approved_fingerprint
): AgentSkillCatalogCandidate {
  const timestamp = "2026-08-04T00:00:00.000Z";
  return {
    agent_skill_id: record.agent_skill_id,
    backend: record.backend,
    content_fingerprint: fingerprint,
    description: record.description,
    direct_tool_dispatch: record.direct_tool_dispatch,
    discovered_at: timestamp,
    discovery_status: "available",
    display_name: record.display_name,
    last_seen_at: timestamp,
    missing_requirements: { bins: [], config: [], env: [], os: [] },
    model_visible: true,
    provider_metadata: {},
    provider_skill_name: record.provider_skill_name,
    runtime_target_id: record.runtime_target_id,
    source_id: record.source_id,
    source_kind: record.backend === "codex_cli"
      ? "codex_directory"
      : "openclaw_agent_inventory",
    source_label: "Approved source",
    user_invocable: true
  };
}

function request(overrides: Record<string, unknown> = {}): ExecuteAgentRequest {
  return executeAgentRequestSchema.parse({
    request_type: "execute_agent",
    agent_backend: "codex_cli",
    agent_query: "Use the selected skill.",
    app_id: "app-1",
    session_id: "session-1",
    ...overrides
  });
}

async function service(input: {
  records?: ProjectedAgentSkillGovernance[];
  observedFingerprint?: string;
  publish?: boolean;
} = {}) {
  const records = input.records ?? [projected()];
  const store = new InMemoryAgentSkillProjectionStore();
  if (input.publish !== false) {
    await store.publish({
      builder_instance_id: "builder-primary",
      digest: "sha256:projection",
      generated_at: "2026-08-04T00:00:00.000Z",
      items: records,
      revision: 1
    });
  }
  return new AgentSkillSelectionService({
    discoveryService: {
      inspect: async (_backend, inspection) => {
        const record = records.find((candidate) =>
          candidate.provider_skill_name === inspection.provider_skill_name
        );
        if (!record) throw new Error("not found");
        return observed(record, input.observedFingerprint);
      }
    },
    projectionStore: store
  });
}

describe("agent skill selection service", () => {
  it("keeps Auto available without a governance projection", async () => {
    const resolver = await service({ publish: false });
    assert.equal(await resolver.resolve(request()), null);
  });

  it("resolves an exact approved structured reference", async () => {
    const resolver = await service();
    const resolved = await resolver.resolve(request({
      agent_skill_ref: {
        agent_skill_id: "agent-skill-1",
        approved_fingerprint: "sha256:v1:approved"
      }
    }));

    assert.equal(resolved?.agent_skill_id, "agent-skill-1");
    assert.equal(resolved?.provider_skill_name, "approved-skill");
    assert.equal(resolved?.activation_method, "codex_explicit_reference");
    assert.equal(resolved?.observed_fingerprint, "sha256:v1:approved");
  });

  it("fails when an explicit selection has no active projection", async () => {
    const resolver = await service({ publish: false });
    await assert.rejects(
      () => resolver.resolve(request({
        agent_skill_ref: {
          agent_skill_id: "agent-skill-1",
          approved_fingerprint: "sha256:v1:approved"
        }
      })),
      /AGENT_SKILL_PROJECTION_UNAVAILABLE/
    );
  });

  it("rejects stale references and provider fingerprint drift", async () => {
    const resolver = await service();
    await assert.rejects(
      () => resolver.resolve(request({
        agent_skill_ref: {
          agent_skill_id: "agent-skill-1",
          approved_fingerprint: "sha256:v1:stale"
        }
      })),
      /AGENT_SKILL_FINGERPRINT_CHANGED/
    );

    const drifted = await service({ observedFingerprint: "sha256:v1:changed" });
    await assert.rejects(
      () => drifted.resolve(request({
        agent_skill_ref: {
          agent_skill_id: "agent-skill-1",
          approved_fingerprint: "sha256:v1:approved"
        }
      })),
      /AGENT_SKILL_FINGERPRINT_CHANGED/
    );
  });

  it("rejects backend mismatch and inactive governance", async () => {
    const resolver = await service();
    await assert.rejects(
      () => resolver.resolve(request({
        agent_backend: "openclaw_cli",
        agent_skill_ref: {
          agent_skill_id: "agent-skill-1",
          approved_fingerprint: "sha256:v1:approved"
        }
      })),
      /AGENT_SKILL_BACKEND_MISMATCH/
    );

    for (const record of [
      projected({ approval_state: "revoked" }),
      projected({ binding_enabled: false }),
      projected({ source_enabled: false }),
      projected({ model_visible: false }),
      projected({ direct_tool_dispatch: true })
    ]) {
      const inactive = await service({ records: [record] });
      await assert.rejects(
        () => inactive.resolve(request({
          agent_skill_ref: {
            agent_skill_id: "agent-skill-1",
            approved_fingerprint: "sha256:v1:approved"
          }
        })),
        /AGENT_SKILL_NOT_BOUND/
      );
    }
  });

  it("resolves unique legacy hints and rejects ambiguous or conflicting input", async () => {
    const unique = await service();
    assert.equal(
      (await unique.resolve(request({ agent_skill_hint: "approved-skill" })))
        ?.agent_skill_id,
      "agent-skill-1"
    );

    const ambiguous = await service({ records: [
      projected(),
      projected({ agent_skill_id: "agent-skill-2", source_id: "source-2" })
    ] });
    await assert.rejects(
      () => ambiguous.resolve(request({ agent_skill_hint: "approved-skill" })),
      /AGENT_SKILL_HINT_AMBIGUOUS/
    );

    await assert.rejects(
      () => unique.resolve(request({
        agent_skill_hint: "different-skill",
        agent_skill_ref: {
          agent_skill_id: "agent-skill-1",
          approved_fingerprint: "sha256:v1:approved"
        }
      })),
      /AGENT_SKILL_SELECTION_CONFLICT/
    );
  });
});
