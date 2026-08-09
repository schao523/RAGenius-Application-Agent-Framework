import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { OpenClawAgentSkillDiscoveryAdapter } from "../../src/core/agent-skills/openclaw-agent-skill-discovery.js";

const target = {
  agent_id: "main",
  display_name: "OpenClaw Main",
  protected_locator_ref: "openclaw-main-ref",
  runtime_target_id: "openclaw-main",
  skill_roots: ["/home/openclaw/.openclaw/skills", "/opt/openclaw/skills"],
  wsl_distro: "OpenClawGateway"
};

const input = {
  protected_locator_ref: "openclaw-main-ref",
  runtime_target_id: "openclaw-main",
  source_id: "source-openclaw"
};

function inventory() {
  return {
    skills: [
      {
        name: "eligible-skill",
        description: "Eligible",
        eligible: true,
        disabled: false,
        modelVisible: true,
        userInvocable: true,
        commandVisible: true,
        source: "openclaw-extra",
        bundled: false,
        missing: { bins: [], env: [], config: [], os: [] }
      },
      {
        name: "disabled-skill",
        description: "Disabled",
        eligible: false,
        disabled: true,
        modelVisible: false,
        userInvocable: true,
        commandVisible: false,
        source: "openclaw-bundled",
        bundled: true,
        missing: { bins: ["missing-bin"], env: [], config: [], os: [] }
      },
      {
        name: "hidden-skill",
        description: "Hidden",
        eligible: true,
        disabled: false,
        modelVisible: false,
        userInvocable: true,
        commandVisible: true,
        source: "openclaw-extra",
        bundled: false,
        missing: { bins: [], env: [], config: [], os: [] }
      },
      {
        name: "tool-only",
        description: "Tool only",
        eligible: true,
        disabled: false,
        modelVisible: true,
        userInvocable: true,
        commandVisible: true,
        directToolDispatch: true,
        source: "openclaw-extra",
        bundled: false,
        missing: { bins: [], env: [], config: [], os: [] }
      }
    ]
  };
}

describe("OpenClaw agent skill discovery", () => {
  it("normalizes inventory and inspects packages with argument-array WSL commands", async () => {
    const calls: string[][] = [];
    const adapter = new OpenClawAgentSkillDiscoveryAdapter({
      command: "openclaw",
      limits: {
        maxDepth: 6,
        maxFileBytes: 1024,
        maxFiles: 20,
        maxTotalBytes: 4096
      },
      maxStderrBytes: 4096,
      maxStdoutBytes: 65536,
      targets: [target],
      timeoutMs: 5000
    }, {
      run: async ({ args }) => {
        calls.push(args);
        if (args.includes("list")) {
          return {
            exitCode: 0,
            stderr: "",
            stdout: JSON.stringify(inventory()),
            timedOut: false
          };
        }
        if (args.includes("info")) {
          const name = args[args.indexOf("info") + 1];
          return {
            exitCode: 0,
            stderr: "",
            stdout: JSON.stringify({
              name,
              baseDir: `/opt/openclaw/skills/${name}`,
              filePath: `/opt/openclaw/skills/${name}/SKILL.md`
            }),
            timedOut: false
          };
        }
        return {
          exitCode: 0,
          stderr: "",
          stdout: JSON.stringify({
            content_fingerprint: `sha256:v1:${"a".repeat(64)}`,
            file_count: 2,
            total_bytes: 100
          }),
          timedOut: false
        };
      }
    });

    const result = await adapter.discover(input);
    const eligible = result.items.find((item) => item.provider_skill_name === "eligible-skill");
    const disabled = result.items.find((item) => item.provider_skill_name === "disabled-skill");
    const hidden = result.items.find((item) => item.provider_skill_name === "hidden-skill");
    const toolOnly = result.items.find((item) => item.provider_skill_name === "tool-only");

    assert.equal(result.complete, true);
    assert.equal(eligible?.discovery_status, "available");
    assert.equal(eligible?.provider_skill_reference, "eligible-skill");
    assert.equal(disabled?.discovery_status, "disabled_at_provider");
    assert.equal(hidden?.discovery_status, "ineligible");
    assert.equal(toolOnly?.direct_tool_dispatch, true);
    assert.equal(toolOnly?.discovery_status, "ineligible");
    assert.match(eligible?.content_fingerprint ?? "", /^sha256:v1:[a-f0-9]{64}$/);
    assert.deepEqual(calls[0], [
      "-d", "OpenClawGateway", "--exec", "openclaw", "skills", "list",
      "--agent", "main", "--json"
    ]);
    assert.ok(calls.every((args) => !args.includes("sh") && !args.includes("bash")));
  });

  it("rejects malformed inventory and timeouts", async () => {
    const malformed = new OpenClawAgentSkillDiscoveryAdapter({
      command: "openclaw",
      limits: { maxDepth: 6, maxFileBytes: 1024, maxFiles: 20, maxTotalBytes: 4096 },
      maxStderrBytes: 4096,
      maxStdoutBytes: 65536,
      targets: [target],
      timeoutMs: 5000
    }, {
      run: async () => ({ exitCode: 0, stderr: "", stdout: "not-json", timedOut: false })
    });
    const timedOut = new OpenClawAgentSkillDiscoveryAdapter({
      command: "openclaw",
      limits: { maxDepth: 6, maxFileBytes: 1024, maxFiles: 20, maxTotalBytes: 4096 },
      maxStderrBytes: 4096,
      maxStdoutBytes: 65536,
      targets: [target],
      timeoutMs: 5000
    }, {
      run: async () => ({ exitCode: null, stderr: "", stdout: "", timedOut: true })
    });

    await assert.rejects(() => malformed.discover(input), /OPENCLAW_SKILL_INVENTORY_INVALID/);
    await assert.rejects(() => timedOut.discover(input), /OPENCLAW_SKILL_DISCOVERY_TIMEOUT/);
  });

  it("rejects provider package roots outside configured WSL roots", async () => {
    const adapter = new OpenClawAgentSkillDiscoveryAdapter({
      command: "openclaw",
      limits: { maxDepth: 6, maxFileBytes: 1024, maxFiles: 20, maxTotalBytes: 4096 },
      maxStderrBytes: 4096,
      maxStdoutBytes: 65536,
      targets: [target],
      timeoutMs: 5000
    }, {
      run: async ({ args }) => {
        if (args.includes("list")) {
          return { exitCode: 0, stderr: "", stdout: JSON.stringify({ skills: [inventory().skills[0]] }), timedOut: false };
        }
        if (args.includes("info")) {
          return {
            exitCode: 0,
            stderr: "",
            stdout: JSON.stringify({
              name: "eligible-skill",
              baseDir: "/home/openclaw/private/eligible-skill",
              filePath: "/home/openclaw/private/eligible-skill/SKILL.md"
            }),
            timedOut: false
          };
        }
        return { exitCode: 73, stderr: "AGENT_SKILL_SOURCE_NOT_ALLOWED", stdout: "", timedOut: false };
      }
    });

    await assert.rejects(
      () => adapter.inspect({ ...input, provider_skill_name: "eligible-skill" }),
      /AGENT_SKILL_SOURCE_NOT_ALLOWED/
    );
  });

  it("inspects inventory with bounded concurrency", async () => {
    let activeInfoCalls = 0;
    let peakInfoCalls = 0;
    const skills = Array.from({ length: 8 }, (_, index) => ({
      ...inventory().skills[0],
      name: `eligible-${index}`
    }));
    const adapter = new OpenClawAgentSkillDiscoveryAdapter({
      command: "openclaw",
      limits: { maxDepth: 6, maxFileBytes: 1024, maxFiles: 20, maxTotalBytes: 4096 },
      maxStderrBytes: 4096,
      maxStdoutBytes: 65536,
      targets: [target],
      timeoutMs: 5000
    }, {
      run: async ({ args }) => {
        if (args.includes("list")) {
          return { exitCode: 0, stderr: "", stdout: JSON.stringify({ skills }), timedOut: false };
        }
        if (args.includes("info")) {
          activeInfoCalls += 1;
          peakInfoCalls = Math.max(peakInfoCalls, activeInfoCalls);
          await new Promise((resolve) => setTimeout(resolve, 10));
          activeInfoCalls -= 1;
          const name = args[args.indexOf("info") + 1];
          return {
            exitCode: 0,
            stderr: "",
            stdout: JSON.stringify({
              name,
              baseDir: `/opt/openclaw/skills/${name}`,
              filePath: `/opt/openclaw/skills/${name}/SKILL.md`
            }),
            timedOut: false
          };
        }
        return {
          exitCode: 0,
          stderr: "",
          stdout: JSON.stringify({
            content_fingerprint: `sha256:v1:${"b".repeat(64)}`,
            file_count: 1,
            total_bytes: 10
          }),
          timedOut: false
        };
      }
    });

    const result = await adapter.discover(input);

    assert.equal(result.items.length, skills.length);
    assert.ok(peakInfoCalls > 1, "inventory inspection should make parallel progress");
    assert.ok(peakInfoCalls <= 4, "inventory inspection must remain bounded");
  });
});
