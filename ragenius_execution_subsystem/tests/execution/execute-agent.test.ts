import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  executionRequestSchema
} from "../../src/api/schemas/execution-request.schema.js";
import type { AgentProvider } from "../../src/core/agents/agent-provider.js";
import { ExecutionEngine } from "../../src/core/execution/execution-engine.js";
import { persistedSkillIdForRequest } from "../../src/core/execution/execution-store.js";

describe("execute_agent requests", () => {
  it("accepts openclaw_cli as an execute_agent backend", () => {
    const parsed = executionRequestSchema.parse({
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Inspect the approved content."
    });

    assert.equal(parsed.request_type, "execute_agent");
    assert.equal(parsed.agent_backend, "openclaw_cli");
  });

  it("rejects unknown execute_agent backends", () => {
    assert.throws(() =>
      executionRequestSchema.parse({
        request_type: "execute_agent",
        app_id: "app_001",
        session_id: "sess_001",
        agent_backend: "unknown_agent",
        agent_query: "Inspect the approved content."
      })
    );
  });

  it("accepts session-scoped artifact refs and provider-neutral expected outputs", () => {
    const parsed = executionRequestSchema.parse({
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Summarize the selected artifact into markdown.",
      artifact_refs: [
        {
          artifact_id: "artifact_123",
          role: "source",
          reuse_mode: "file_backed",
          display_name: "Bible notes.md",
          mime_type: "text/markdown"
        }
      ],
      expected_outputs: [
        {
          output_id: "agent_answer",
          display_name: "agent-answer.md",
          media_type: "text/markdown",
          required: true,
          persist_as_artifact: true,
          artifact_type: "agent_output",
          min_size_bytes: 1
        }
      ]
    });

    assert.equal(parsed.request_type, "execute_agent");
    assert.equal(parsed.artifact_refs?.[0]?.artifact_id, "artifact_123");
    assert.equal(parsed.artifact_refs?.[0]?.reuse_mode, "file_backed");
    assert.equal(parsed.expected_outputs?.[0]?.output_id, "agent_answer");
    assert.equal(parsed.expected_outputs?.[0]?.persist_as_artifact, true);
  });

  it("rejects invalid artifact refs and expected outputs", () => {
    assert.throws(() =>
      executionRequestSchema.parse({
        request_type: "execute_agent",
        app_id: "app_001",
        session_id: "sess_001",
        agent_backend: "openclaw_cli",
        agent_query: "Use this artifact.",
        artifact_refs: [
          {
            artifact_id: "artifact_123",
            role: "source",
            reuse_mode: "raw_path"
          }
        ]
      })
    );

    assert.throws(() =>
      executionRequestSchema.parse({
        request_type: "execute_agent",
        app_id: "app_001",
        session_id: "sess_001",
        agent_backend: "openclaw_cli",
        agent_query: "Create output.",
        expected_outputs: [
          {
            output_id: "bad/output",
            persist_as_artifact: true
          }
        ]
      })
    );
  });

  it("dispatches openclaw_cli agent requests to the OpenClaw provider", async () => {
    const openclawProvider: AgentProvider = {
      backend: "openclaw_cli",
      async execute() {
        return {
          status: "completed",
          summary: "OpenClaw completed.",
          output_text: "OpenClaw response.",
          artifacts: [],
          provider_metadata: {
            backend: "openclaw_cli",
            provider_name: "OpenClaw",
            invocation_mode: "wsl_cli",
            wsl_distro: "OpenClawGateway",
            openclaw_command: "openclaw",
            openclaw_agent_id: "main",
            openclaw_session_key: "ragenius:app_001:sess_001:execution_test",
            execution_mode: "read_only",
            expected_output_count: 0,
            required_output_count: 0,
            verified_output_count: 0,
            json_parse_status: "parsed",
            raw_exit_code: 0,
            timed_out: false,
            stdout_truncated: false,
            stderr_truncated: false
          },
          verification_results: [],
          diagnostics: {
            stdout_truncated: false,
            stderr_truncated: false,
            redactions_applied: true
          },
          raw: { exit_code: 0 }
        };
      }
    };

    const engine = new ExecutionEngine({
      agentProviders: new Map([["openclaw_cli", openclawProvider]])
    });

    const result = await engine.execute({
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Reply with OK."
    });

    assert.equal(result.status, "completed");
    assert.equal((result.result as Record<string, unknown>).backend, "openclaw_cli");
    assert.deepEqual(result.execution_metadata?.provider_ids, ["openclaw_cli"]);
  });

  it("persists backend-aware agent skill ids", () => {
    assert.equal(
      persistedSkillIdForRequest({
        request_type: "execute_agent",
        app_id: "app_001",
        session_id: "sess_001",
        agent_backend: "openclaw_cli",
        agent_query: "Inspect content."
      }),
      "openclaw_cli"
    );

    assert.equal(
      persistedSkillIdForRequest({
        request_type: "execute_agent",
        app_id: "app_001",
        session_id: "sess_001",
        agent_backend: "codex_cli",
        agent_query: "Use NotebookLM.",
        agent_skill_hint: "notebooklm"
      }),
      "codex_cli:notebooklm"
    );
  });
});
