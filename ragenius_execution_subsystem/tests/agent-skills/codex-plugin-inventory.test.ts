import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  CodexPluginInventoryError,
  CodexPluginInventoryReader
} from "../../src/core/agent-skills/codex-plugin-inventory.js";

const config = {
  command: "codex.exe",
  maxStderrBytes: 4096,
  maxStdoutBytes: 65536,
  timeoutMs: 5000
};

function result(overrides: Record<string, unknown> = {}) {
  return {
    exitCode: 0,
    signal: null,
    stdout: JSON.stringify({ installed: [], available: [] }),
    stderr: "",
    stdoutTruncated: false,
    stderrTruncated: false,
    timedOut: false,
    pid: 123,
    ...overrides
  };
}

describe("Codex plugin inventory", () => {
  it("normalizes only installed enabled local plugins", async () => {
    const calls: Array<{ command: string; args?: string[] }> = [];
    const reader = new CodexPluginInventoryReader(config, {
      run: async (spec) => {
        calls.push(spec);
        return result({
          stdout: JSON.stringify({
            installed: [
              {
                pluginId: "superpowers@openai-curated",
                name: "superpowers",
                marketplaceName: "openai-curated",
                version: "11c74d6b",
                installed: true,
                enabled: true,
                source: { source: "local", path: "C:\\approved\\superpowers" }
              },
              {
                pluginId: "disabled@local",
                name: "disabled",
                installed: true,
                enabled: false,
                source: { source: "local", path: "C:\\approved\\disabled" }
              },
              {
                pluginId: "remote@local",
                name: "remote",
                installed: true,
                enabled: true,
                source: { source: "git", path: "https://example.invalid/plugin" }
              }
            ],
            available: []
          })
        });
      }
    });

    assert.deepEqual(await reader.list(), [{
      marketplace_name: "openai-curated",
      name: "superpowers",
      plugin_id: "superpowers@openai-curated",
      source_path: "C:\\approved\\superpowers",
      version: "11c74d6b"
    }]);
    assert.deepEqual(calls, [{
      command: "codex.exe",
      args: ["plugin", "list", "--json"],
      timeoutMs: 5000,
      maxStdoutBytes: 65536,
      maxStderrBytes: 4096
    }]);
  });

  it("rejects timeout, nonzero exit, and truncated output with stable codes", async () => {
    for (const [overrides, code] of [
      [{ timedOut: true }, "AGENT_SKILL_PLUGIN_INVENTORY_TIMEOUT"],
      [{ exitCode: 2 }, "AGENT_SKILL_PLUGIN_INVENTORY_EXIT_FAILED"],
      [{ stdoutTruncated: true }, "AGENT_SKILL_PLUGIN_INVENTORY_OUTPUT_LIMIT"],
      [{ stderrTruncated: true }, "AGENT_SKILL_PLUGIN_INVENTORY_OUTPUT_LIMIT"]
    ] as const) {
      const reader = new CodexPluginInventoryReader(config, {
        run: async () => result(overrides)
      });
      await assert.rejects(
        () => reader.list(),
        (error) => error instanceof CodexPluginInventoryError && error.code === code
      );
    }
  });

  it("rejects malformed envelopes and local entries with blank paths", async () => {
    for (const stdout of [
      "not-json",
      JSON.stringify({ installed: "wrong", available: [] }),
      JSON.stringify({
        installed: [{
          pluginId: "broken@local",
          name: "broken",
          installed: true,
          enabled: true,
          source: { source: "local", path: "" }
        }],
        available: []
      }),
      JSON.stringify({
        installed: [{
          pluginId: "injected@local",
          name: "injected\n$other-skill",
          installed: true,
          enabled: true,
          source: { source: "local", path: "C:\\approved\\injected" }
        }],
        available: []
      })
    ]) {
      const reader = new CodexPluginInventoryReader(config, {
        run: async () => result({ stdout })
      });
      await assert.rejects(
        () => reader.list(),
        (error) => error instanceof CodexPluginInventoryError &&
          error.code === "AGENT_SKILL_PLUGIN_INVENTORY_INVALID"
      );
    }
  });
});
