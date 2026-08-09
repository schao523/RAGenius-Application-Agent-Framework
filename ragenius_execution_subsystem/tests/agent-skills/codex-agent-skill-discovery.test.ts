import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, it } from "node:test";

import { CodexAgentSkillDiscoveryAdapter } from "../../src/core/agent-skills/codex-agent-skill-discovery.js";

const roots: string[] = [];

async function temporaryRoot(): Promise<string> {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "ragenius-codex-skills-"));
  roots.push(root);
  return root;
}

async function writeSkill(
  root: string,
  directory: string,
  name: string,
  description = "Test skill"
): Promise<string> {
  const skillRoot = path.join(root, directory);
  await fs.mkdir(skillRoot, { recursive: true });
  await fs.writeFile(
    path.join(skillRoot, "SKILL.md"),
    `---\nname: ${name}\ndescription: ${description}\n---\n\n# ${name}\n`,
    "utf8"
  );
  return skillRoot;
}

function adapter(root: string, limits: Partial<{
  maxDepth: number;
  maxFiles: number;
  maxFileBytes: number;
  maxTotalBytes: number;
}> = {}) {
  return new CodexAgentSkillDiscoveryAdapter({
    limits: {
      maxDepth: 6,
      maxFileBytes: 1024,
      maxFiles: 20,
      maxTotalBytes: 4096,
      ...limits
    },
    sourceOptions: [{
      display_name: "Test Codex Skills",
      path: root,
      protected_locator_ref: "codex-source-ref-1",
      runtime_target_id: "codex-local-default"
    }]
  });
}

const discoveryInput = {
  protected_locator_ref: "codex-source-ref-1",
  runtime_target_id: "codex-local-default",
  source_id: "source-1"
};

describe("Codex agent skill discovery", () => {
  afterEach(async () => {
    await Promise.all(roots.splice(0).map((root) =>
      fs.rm(root, { force: true, recursive: true })
    ));
  });

  it("fingerprints the complete skill package deterministically", async () => {
    const root = await temporaryRoot();
    const skillRoot = await writeSkill(root, "sample", "sample-skill");
    await fs.writeFile(path.join(skillRoot, "reference.md"), "version one", "utf8");
    const discovery = adapter(root);

    const first = await discovery.inspect({
      ...discoveryInput,
      provider_skill_name: "sample-skill"
    });
    const repeated = await discovery.inspect({
      ...discoveryInput,
      provider_skill_name: "sample-skill"
    });
    await fs.writeFile(path.join(skillRoot, "reference.md"), "version two", "utf8");
    const afterReferenceEdit = await discovery.inspect({
      ...discoveryInput,
      provider_skill_name: "sample-skill"
    });

    assert.match(first.content_fingerprint, /^sha256:v1:[a-f0-9]{64}$/);
    assert.equal(repeated.content_fingerprint, first.content_fingerprint);
    assert.notEqual(
      afterReferenceEdit.content_fingerprint,
      first.content_fingerprint
    );
    assert.equal("path" in first, false);
  });

  it("reports malformed manifests and duplicate names without hiding valid entries", async () => {
    const root = await temporaryRoot();
    await writeSkill(root, "valid", "valid-skill");
    await writeSkill(root, "duplicate-a", "duplicate-skill");
    await writeSkill(root, "duplicate-b", "duplicate-skill");
    const malformedRoot = path.join(root, "malformed");
    await fs.mkdir(malformedRoot);
    await fs.writeFile(path.join(malformedRoot, "SKILL.md"), "# no frontmatter", "utf8");

    const result = await adapter(root).discover(discoveryInput);

    assert.equal(result.complete, true);
    assert.equal(
      result.items.find((entry) => entry.provider_skill_name === "valid-skill")?.discovery_status,
      "available"
    );
    assert.equal(
      result.items.filter((entry) => entry.provider_skill_name === "duplicate-skill").length,
      2
    );
    assert.ok(
      result.items
        .filter((entry) => entry.provider_skill_name === "duplicate-skill")
        .every((entry) => entry.discovery_status === "invalid")
    );
    assert.ok(result.errors.some((error) => error.code === "AGENT_SKILL_MANIFEST_INVALID"));
  });

  it("fails closed at configured depth, file, and byte limits", async () => {
    const root = await temporaryRoot();
    const deepRoot = await writeSkill(root, "one/two/three", "deep-skill");
    await fs.writeFile(path.join(deepRoot, "large.txt"), "x".repeat(2048), "utf8");

    const depthResult = await adapter(root, { maxDepth: 1 }).discover(discoveryInput);
    assert.equal(depthResult.complete, false);
    assert.ok(depthResult.errors.some((error) => error.code === "AGENT_SKILL_DEPTH_LIMIT"));

    await assert.rejects(
      () => adapter(root, { maxFileBytes: 128 }).inspect({
        ...discoveryInput,
        provider_skill_name: "deep-skill"
      }),
      /AGENT_SKILL_FILE_BYTES_LIMIT/
    );
    await assert.rejects(
      () => adapter(root, { maxFileBytes: 4096, maxFiles: 1 }).inspect({
        ...discoveryInput,
        provider_skill_name: "deep-skill"
      }),
      /AGENT_SKILL_FILE_COUNT_LIMIT/
    );
    await assert.rejects(
      () => adapter(root, { maxFileBytes: 4096, maxTotalBytes: 100 }).inspect({
        ...discoveryInput,
        provider_skill_name: "deep-skill"
      }),
      /AGENT_SKILL_TOTAL_BYTES_LIMIT/
    );
  });

  it("rejects a linked package that escapes the configured source", async (context) => {
    const root = await temporaryRoot();
    const outside = await temporaryRoot();
    await writeSkill(outside, "escaped", "escaped-skill");
    const link = path.join(root, "escaped-link");
    try {
      await fs.symlink(path.join(outside, "escaped"), link, "junction");
    } catch (error) {
      context.skip(`Junction creation is unavailable: ${String(error)}`);
      return;
    }

    await assert.rejects(
      () => adapter(root).inspect({
        ...discoveryInput,
        provider_skill_name: "escaped-skill"
      }),
      /AGENT_SKILL_SOURCE_NOT_ALLOWED/
    );
  });

  it("discovers same-name skills under distinct contained plugin namespaces", async () => {
    const root = await temporaryRoot();
    const firstPlugin = path.join(root, "plugins", "plugin-a");
    const secondPlugin = path.join(root, "plugins", "plugin-b");
    await writeSkill(firstPlugin, "skills/shared", "shared-skill");
    await writeSkill(secondPlugin, "skills/shared", "shared-skill");
    const discovery = new CodexAgentSkillDiscoveryAdapter({
      limits: {
        maxDepth: 6,
        maxFileBytes: 1024,
        maxFiles: 20,
        maxTotalBytes: 4096
      },
      sourceOptions: [{
        display_name: "Approved plugins",
        discovery_mode: "plugin_inventory",
        path: root,
        precedence: 10,
        protected_locator_ref: "plugin-root",
        runtime_target_id: "codex-local-default"
      }]
    }, {
      pluginInventory: {
        list: async () => [{
          name: "plugin-a",
          plugin_id: "plugin-a@local",
          source_path: firstPlugin,
          version: "1.0.0"
        }, {
          name: "plugin-b",
          plugin_id: "plugin-b@local",
          source_path: secondPlugin,
          version: "2.0.0"
        }]
      }
    });

    const result = await discovery.discover({
      protected_locator_ref: "plugin-root",
      runtime_target_id: "codex-local-default",
      source_id: "source-plugins"
    });

    assert.equal(result.complete, true);
    assert.deepEqual(
      result.items.map((item) => item.provider_skill_reference).sort(),
      ["plugin-a:shared-skill", "plugin-b:shared-skill"]
    );
    assert.ok(result.items.every((item) => item.discovery_status === "available"));
    assert.equal(result.items[0]?.source_kind, "codex_plugin_inventory");
    assert.equal(result.items[0]?.provider_metadata.plugin_id, "plugin-a@local");
    assert.equal(JSON.stringify(result).includes(root), false);
  });

  it("ignores CLI plugin paths outside approved roots and fails closed on tied roots", async () => {
    const root = await temporaryRoot();
    const nested = path.join(root, "nested");
    const outside = await temporaryRoot();
    const outsidePlugin = path.join(outside, "plugin-outside");
    await writeSkill(outsidePlugin, "skills/test", "outside-skill");
    const pluginInventory = {
      list: async () => [{
        name: "outside-plugin",
        plugin_id: "outside-plugin@local",
        source_path: outsidePlugin
      }]
    };
    const contained = new CodexAgentSkillDiscoveryAdapter({
      limits: { maxDepth: 6, maxFileBytes: 1024, maxFiles: 20, maxTotalBytes: 4096 },
      sourceOptions: [{
        display_name: "Approved root",
        discovery_mode: "plugin_inventory",
        path: root,
        precedence: 10,
        protected_locator_ref: "root-ref",
        runtime_target_id: "codex-local-default"
      }]
    }, { pluginInventory });
    const outsideResult = await contained.discover({
      protected_locator_ref: "root-ref",
      runtime_target_id: "codex-local-default",
      source_id: "source-root"
    });
    assert.equal(outsideResult.items.length, 0);
    assert.ok(outsideResult.errors.some((error) =>
      error.code === "AGENT_SKILL_SOURCE_NOT_ALLOWED"
    ));

    await fs.mkdir(nested, { recursive: true });
    const tied = new CodexAgentSkillDiscoveryAdapter({
      limits: { maxDepth: 6, maxFileBytes: 1024, maxFiles: 20, maxTotalBytes: 4096 },
      sourceOptions: [{
        display_name: "Root A",
        discovery_mode: "plugin_inventory",
        path: root,
        precedence: 10,
        protected_locator_ref: "root-a",
        runtime_target_id: "codex-local-default"
      }, {
        display_name: "Root B",
        discovery_mode: "plugin_inventory",
        path: nested,
        precedence: 10,
        protected_locator_ref: "root-b",
        runtime_target_id: "codex-local-default"
      }]
    }, {
      pluginInventory: {
        list: async () => [{
          name: "tied-plugin",
          plugin_id: "tied-plugin@local",
          source_path: nested
        }]
      }
    });
    const tiedResult = await tied.discover({
      protected_locator_ref: "root-a",
      runtime_target_id: "codex-local-default",
      source_id: "source-a"
    });
    assert.equal(tiedResult.items.length, 0);
    assert.ok(tiedResult.errors.some((error) =>
      error.code === "AGENT_SKILL_SOURCE_AMBIGUOUS"
    ));
  });

  it("marks discovery incomplete when a reported plugin source becomes unavailable", async () => {
    const root = await temporaryRoot();
    const discovery = new CodexAgentSkillDiscoveryAdapter({
      limits: { maxDepth: 6, maxFileBytes: 1024, maxFiles: 20, maxTotalBytes: 4096 },
      sourceOptions: [{
        display_name: "Approved plugins",
        discovery_mode: "plugin_inventory",
        path: root,
        precedence: 10,
        protected_locator_ref: "plugin-root",
        runtime_target_id: "codex-local-default"
      }]
    }, {
      pluginInventory: {
        list: async () => [{
          name: "missing-plugin",
          plugin_id: "missing-plugin@local",
          source_path: path.join(root, "missing-plugin")
        }]
      }
    });

    const result = await discovery.discover({
      protected_locator_ref: "plugin-root",
      runtime_target_id: "codex-local-default",
      source_id: "source-plugins"
    });

    assert.equal(result.complete, false);
    assert.ok(result.errors.some((error) =>
      error.code === "AGENT_SKILL_SOURCE_UNAVAILABLE"
    ));
  });
});
