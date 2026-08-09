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
});
