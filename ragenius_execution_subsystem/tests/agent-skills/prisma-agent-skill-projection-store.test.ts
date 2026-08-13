import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  PrismaAgentSkillProjectionStore,
  type PrismaAgentSkillProjectionClient
} from "../../src/core/agent-skills/prisma-agent-skill-projection-store.js";
import type { ProjectedAgentSkillGovernance } from "../../src/core/agent-skills/agent-skill-types.js";

function binding(): ProjectedAgentSkillGovernance {
  return {
    agent_skill_id: "agent-skill-1",
    app_id: "app-1",
    approval_state: "approved",
    approved_fingerprint: "sha256:v1:abc",
    backend: "codex_cli",
    binding_enabled: true,
    current_fingerprint: "sha256:v1:abc",
    description: "A persisted skill",
    direct_tool_dispatch: false,
    display_name: "Persisted Skill",
    interaction_policy: {
      interaction_requirement: "autonomous",
      supported_interaction_types: [],
      required_transport: "one_shot",
      recovery_class: "not_resumable"
    },
    model_visible: true,
    protected_locator_ref: "codex-source-ref-1",
    provider_skill_name: "systematic-debugging",
    provider_skill_reference: "superpowers:systematic-debugging",
    runtime_target_id: "codex-local-default",
    source_enabled: true,
    source_id: "source-1",
    user_invocable: true
  };
}

type RevisionRow = {
  id: string;
  builderInstanceId: string;
  revision: bigint;
  digest: string;
  generatedAt: Date;
  receivedAt: Date;
  status: string;
};

type ItemRow = Record<string, unknown>;

function createFakePrisma() {
  const state: {
    activeRevisionId: string | null;
    failNextItemInsert: boolean;
    items: ItemRow[];
    revisions: RevisionRow[];
  } = {
    activeRevisionId: null,
    failNextItemInsert: false,
    items: [],
    revisions: []
  };

  function transactionClient(working: typeof state) {
    return {
      agentSkillProjectionHead: {
        async findUnique() {
          return working.activeRevisionId
            ? { id: "active", activeRevisionId: working.activeRevisionId }
            : null;
        },
        async upsert(args: { create: { activeRevisionId: string }; update: { activeRevisionId: string } }) {
          working.activeRevisionId = args.update.activeRevisionId ?? args.create.activeRevisionId;
          return { id: "active", activeRevisionId: working.activeRevisionId };
        }
      },
      agentSkillProjectionRevision: {
        async create(args: { data: Omit<RevisionRow, "id"> & { id: string } }) {
          const row = {
            ...args.data,
            receivedAt: args.data.receivedAt ?? new Date("2026-08-04T00:00:01.000Z")
          };
          working.revisions.push(row);
          return row;
        },
        async findUnique(args: { where: { id: string } }) {
          return working.revisions.find((row) => row.id === args.where.id) ?? null;
        },
        async updateMany(args: { data: { status: string }; where: { status: string } }) {
          let count = 0;
          working.revisions = working.revisions.map((row) => {
            if (row.status !== args.where.status) return row;
            count += 1;
            return { ...row, status: args.data.status };
          });
          return { count };
        }
      },
      projectedAgentSkillGovernance: {
        async createMany(args: { data: ItemRow[] }) {
          if (working.failNextItemInsert) {
            working.failNextItemInsert = false;
            throw new Error("simulated item insert failure");
          }
          working.items.push(...args.data.map((item) => ({ ...item })));
          return { count: args.data.length };
        },
        async findFirst(args: { where: Record<string, unknown> }) {
          return working.items.find((item) =>
            Object.entries(args.where).every(([key, value]) => item[key] === value)
          ) ?? null;
        },
        async findMany(args: { where: Record<string, unknown> }) {
          return working.items.filter((item) =>
            Object.entries(args.where).every(([key, value]) => item[key] === value)
          );
        }
      }
    };
  }

  const client = {
    ...transactionClient(state),
    async $transaction<T>(operation: (tx: ReturnType<typeof transactionClient>) => Promise<T>) {
      const working = {
        activeRevisionId: state.activeRevisionId,
        failNextItemInsert: state.failNextItemInsert,
        items: state.items.map((item) => ({ ...item })),
        revisions: state.revisions.map((revision) => ({ ...revision }))
      };
      try {
        const result = await operation(transactionClient(working));
        state.activeRevisionId = working.activeRevisionId;
        state.failNextItemInsert = working.failNextItemInsert;
        state.items = working.items;
        state.revisions = working.revisions;
        return result;
      } catch (error) {
        state.failNextItemInsert = working.failNextItemInsert;
        throw error;
      }
    }
  };

  return { client, state };
}

describe("prisma agent skill projection store", () => {
  it("persists millisecond-scale Builder revisions as bigint and returns JSON-safe numbers", async () => {
    const { client, state } = createFakePrisma();
    const store = new PrismaAgentSkillProjectionStore(
      client as unknown as PrismaAgentSkillProjectionClient
    );
    const revision = 1_785_832_908_957;

    const receipt = await store.publish({
      builder_instance_id: "builder-primary",
      digest: "sha256:large",
      generated_at: "2026-08-04T00:00:00.000Z",
      items: [binding()],
      revision
    });

    assert.equal(typeof state.revisions[0]?.revision, "bigint");
    assert.equal(receipt.revision, revision);
  });

  it("persists an active snapshot across store instances", async () => {
    const { client, state } = createFakePrisma();
    const firstStore = new PrismaAgentSkillProjectionStore(
      client as unknown as PrismaAgentSkillProjectionClient
    );
    await firstStore.publish({
      builder_instance_id: "builder-primary",
      digest: "sha256:a",
      generated_at: "2026-08-04T00:00:00.000Z",
      items: [binding()],
      revision: 42
    });

    const restartedStore = new PrismaAgentSkillProjectionStore(
      client as unknown as PrismaAgentSkillProjectionClient
    );
    assert.equal((await restartedStore.getActiveRevision())?.revision, 42);
    assert.equal(state.revisions.find((row) => row.revision === 42n)?.status, "active");
    assert.deepEqual(await restartedStore.listForApp("app-1", "codex_cli"), [binding()]);
  });

  it("keeps the prior active snapshot when publication fails", async () => {
    const { client, state } = createFakePrisma();
    const store = new PrismaAgentSkillProjectionStore(
      client as unknown as PrismaAgentSkillProjectionClient
    );
    await store.publish({
      builder_instance_id: "builder-primary",
      digest: "sha256:a",
      generated_at: "2026-08-04T00:00:00.000Z",
      items: [binding()],
      revision: 42
    });
    state.failNextItemInsert = true;

    await assert.rejects(
      () => store.publish({
        builder_instance_id: "builder-primary",
        digest: "sha256:b",
        generated_at: "2026-08-04T00:01:00.000Z",
        items: [binding()],
        revision: 43
      }),
      /simulated item insert failure/
    );

    assert.equal((await store.getActiveRevision())?.revision, 42);
    assert.deepEqual(await store.listForApp("app-1", "codex_cli"), [binding()]);
  });
});
