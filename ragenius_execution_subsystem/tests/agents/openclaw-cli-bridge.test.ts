import assert from "node:assert/strict";
import test from "node:test";

import {
  buildOpenClawSupervisedWslArgs,
  executeOpenClawCliBridge,
  extractOpenClawExecArgs
} from "../../src/core/agents/openclaw-cli-bridge.js";

test("builds a static WSL process-group wrapper with separate agent arguments", () => {
  const prompt = "do not run $(whoami)";
  const args = buildOpenClawSupervisedWslArgs({
    wslDistro: "OpenClawGateway",
    processGroupFile: "/tmp/ragenius-openclaw-test.pgid",
    agentArgs: ["openclaw", "agent", "--message", prompt]
  });

  assert.deepEqual(args.slice(0, 7), [
    "-d",
    "OpenClawGateway",
    "--exec",
    "setsid",
    "--wait",
    "sh",
    "-c"
  ]);
  assert.equal(args[7]?.includes(prompt), false);
  assert.equal(args.at(-1), prompt);
  assert.match(args[7] ?? "", /exec "\$@"/);
});

test("retains the OpenClaw executable when wrapping direct WSL arguments", () => {
  assert.deepEqual(
    extractOpenClawExecArgs([
      "-d",
      "OpenClawGateway",
      "--exec",
      "openclaw",
      "agent",
      "--json"
    ]),
    ["openclaw", "agent", "--json"]
  );
});

test("builds OpenClaw argv without shell interpolation", async () => {
  const calls: unknown[] = [];
  const result = await executeOpenClawCliBridge({
    config: {
      wslDistro: "OpenClawGateway",
      command: "openclaw",
      agentId: "main",
      timeoutMs: 120000,
      maxStdoutBytes: 262144,
      maxStderrBytes: 65536
    },
    sessionKey: "ragenius:app:sess:exec",
    prompt: "Reply with `Task outcome: succeeded`; do not run $(whoami).",
    spawnProcess: async (command, args) => {
      calls.push({ command, args });
      return {
        exitCode: 0,
        stdout: JSON.stringify({
          status: "ok",
          result: { finalAssistantVisibleText: "OK" }
        }),
        stderr: "",
        timedOut: false
      };
    }
  });

  assert.deepEqual(calls[0], {
    command: "wsl",
    args: [
      "-d",
      "OpenClawGateway",
      "--exec",
      "openclaw",
      "agent",
      "--agent",
      "main",
      "--session-key",
      "ragenius:app:sess:exec",
      "--message",
      "Reply with `Task outcome: succeeded`; do not run $(whoami).",
      "--json"
    ]
  });
  assert.equal(result.exitCode, 0);
  assert.equal(result.jsonParseStatus, "parsed");
});

test("truncates stdout and stderr tails", async () => {
  const result = await executeOpenClawCliBridge({
    config: {
      wslDistro: "OpenClawGateway",
      command: "openclaw",
      agentId: "main",
      timeoutMs: 120000,
      maxStdoutBytes: 4,
      maxStderrBytes: 3
    },
    sessionKey: "session",
    prompt: "prompt",
    spawnProcess: async () => ({
      exitCode: 0,
      stdout: "abcdef",
      stderr: "wxyz",
      timedOut: false
    })
  });

  assert.equal(result.stdout, "cdef");
  assert.equal(result.stderr, "xyz");
  assert.equal(result.stdoutTruncated, true);
  assert.equal(result.stderrTruncated, true);
  assert.equal(result.jsonParseStatus, "failed");
});

test("reports timeout from the spawned process", async () => {
  const result = await executeOpenClawCliBridge({
    config: {
      wslDistro: "OpenClawGateway",
      command: "openclaw",
      agentId: "main",
      timeoutMs: 10,
      maxStdoutBytes: 262144,
      maxStderrBytes: 65536
    },
    sessionKey: "session",
    prompt: "prompt",
    spawnProcess: async () => ({
      exitCode: null,
      stdout: "",
      stderr: "timed out",
      timedOut: true
    })
  });

  assert.equal(result.timedOut, true);
  assert.equal(result.exitCode, null);
});
