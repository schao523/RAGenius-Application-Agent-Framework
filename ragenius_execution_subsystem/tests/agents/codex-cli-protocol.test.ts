import assert from "node:assert/strict";
import test from "node:test";

import {
  buildCodexArgs,
  parseCodexJsonl
} from "../../scripts/codex_cli_protocol.js";

test("builds explicit workspace sandbox arguments without the bypass flag", () => {
  const args = buildCodexArgs(["exec", "--json"], {
    workspaceAbsolutePath: "D:/runtime/codex-runs/execution_123",
    sandboxMode: "workspace-write",
    networkAccess: "allowlisted"
  });

  assert.deepEqual(args.slice(-6), [
    "--cd",
    "D:/runtime/codex-runs/execution_123",
    "--sandbox",
    "workspace-write",
    "-c",
    "sandbox_workspace_write.network_access=true"
  ]);
  assert.equal(args.includes("--dangerously-bypass-approvals-and-sandbox"), false);
});

test("replaces configured sandbox arguments with the trusted runtime policy", () => {
  const args = buildCodexArgs(
    ["exec", "--json", "--sandbox", "danger-full-access", "-s", "read-only"],
    {
      workspaceAbsolutePath: "D:/runtime/codex-runs/execution_123",
      sandboxMode: "workspace-write",
      networkAccess: "deny"
    }
  );

  assert.equal(args.filter((arg) => arg === "--sandbox").length, 1);
  assert.equal(args.includes("danger-full-access"), false);
  assert.equal(args.includes("read-only"), false);
  assert.deepEqual(args.slice(-4), [
    "--cd",
    "D:/runtime/codex-runs/execution_123",
    "--sandbox",
    "workspace-write"
  ]);
});

test("adds only trusted additional writable directories", () => {
  const args = buildCodexArgs(
    ["exec", "--json", "--add-dir", "C:/untrusted"],
    {
      workspaceAbsolutePath: "D:/runtime/codex-runs/execution_123",
      sandboxMode: "workspace-write",
      networkAccess: "allowlisted",
      additionalWritableDirs: [
        "C:/Users/User/.notebooklm/profiles/default",
        "C:/Users/User/.notebooklm/profiles/default"
      ]
    }
  );

  assert.equal(args.includes("C:/untrusted"), false);
  assert.deepEqual(
    args.flatMap((arg, index) => arg === "--add-dir" ? [args[index + 1]] : []),
    ["C:/Users/User/.notebooklm/profiles/default"]
  );
});

test("parses terminal state, command evidence, final message, and usage line by line", () => {
  const finalMessage = JSON.stringify({
    task_status: "completed",
    summary: "Source added.",
    activated_skills: ["notebooklm"],
    operations: [{
      operation_id: "notebooklm_source_add",
      operation: "add source",
      status: "completed",
      external_id: "source_123"
    }],
    artifacts: [],
    errors: []
  });
  const jsonl = [
    JSON.stringify({ type: "thread.started", thread_id: "thread_123" }),
    JSON.stringify({ type: "turn.started" }),
    JSON.stringify({
      type: "item.started",
      item: { id: "item_1", type: "command_execution", command: "python -m notebooklm source add" }
    }),
    JSON.stringify({
      type: "item.completed",
      item: {
        id: "item_1",
        type: "command_execution",
        command: "python -m notebooklm source add",
        aggregated_output: "created source_123",
        exit_code: 0,
        status: "completed"
      }
    }),
    JSON.stringify({
      type: "item.completed",
      item: { id: "item_2", type: "agent_message", text: finalMessage }
    }),
    JSON.stringify({ type: "turn.completed", usage: { input_tokens: 10, output_tokens: 20 } })
  ].join("\n");

  const parsed = parseCodexJsonl(jsonl, { maxOutputBytes: 16384, rawExitCode: 0 });

  assert.equal(parsed.thread_id, "thread_123");
  assert.equal(parsed.turn_status, "completed");
  assert.equal(parsed.command_events.length, 1);
  assert.equal(parsed.command_events[0]?.exit_code, 0);
  assert.equal(parsed.command_events[0]?.stdout_summary, "created source_123");
  assert.equal(parsed.final_message, finalMessage);
  assert.deepEqual(parsed.usage, { input_tokens: 10, output_tokens: 20 });
  assert.equal(parsed.raw_exit_code, 0);
});

test("turn.failed overrides an otherwise successful process", () => {
  const parsed = parseCodexJsonl(
    [
      "not-json",
      JSON.stringify({ type: "turn.failed", error: { message: "model failed" } })
    ].join("\n"),
    { maxOutputBytes: 16384, rawExitCode: 0 }
  );

  assert.equal(parsed.turn_status, "failed");
  assert.equal(parsed.errors[0]?.message, "model failed");
  assert.equal(parsed.malformed_line_count, 1);
});

test("bounds and redacts command output", () => {
  const parsed = parseCodexJsonl(
    JSON.stringify({
      type: "item.completed",
      item: {
        id: "item_1",
        type: "command_execution",
        command: "curl -H 'Authorization: Bearer secret-value' https://example.test",
        aggregated_output: `token=secret-value ${"x".repeat(200)}`,
        exit_code: 0
      }
    }),
    { maxOutputBytes: 64, rawExitCode: 0 }
  );

  assert.doesNotMatch(parsed.command_events[0]?.command ?? "", /secret-value/);
  assert.doesNotMatch(parsed.command_events[0]?.stdout_summary ?? "", /secret-value/);
  assert.equal(parsed.stdout_truncated, true);
  assert.ok(Buffer.byteLength(parsed.command_events[0]?.stdout_summary ?? "") <= 64);
});
