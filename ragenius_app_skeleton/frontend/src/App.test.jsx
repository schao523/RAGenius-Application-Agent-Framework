import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const uploadArtifactMock = vi.hoisted(() => vi.fn());
vi.mock("./artifactUploadClient", async (importOriginal) => ({
  ...(await importOriginal()),
  uploadArtifact: uploadArtifactMock,
}));

import {
  default as App,
  applyApprovedContentSelectionToExecQuery,
  buildExecutionResultPreview,
  buildExecutionSubmitErrorTurn,
  buildExecutionRequestForComposer,
  buildExecCommand,
  classifyAssistantTurn,
  createSessionId,
  mergeTaskModelDiagnostics,
  resolveActiveAppDisplay,
  resolveInstructionUnderstandingState,
} from "./App";

describe("createSessionId", () => {
  it("creates UUID session identifiers", () => {
    const sessionId = createSessionId();

    expect(sessionId).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    );
  });

  it("uses the supplied UUID source", () => {
    expect(
      createSessionId(() => "123e4567-e89b-42d3-a456-426614174000"),
    ).toBe("123e4567-e89b-42d3-a456-426614174000");
  });
});

describe("mergeTaskModelDiagnostics", () => {
  it("uses top-level diagnostics when the retrieval summary omits them", () => {
    const diagnostics = {
      context_optimization: { mode: "diagnostic" },
      turn_token_accounting: { call_count: 3 },
    };

    expect(mergeTaskModelDiagnostics({ answer_source: "llm" }, diagnostics)).toEqual({
      answer_source: "llm",
      task_model_diagnostics: diagnostics,
    });
  });

  it("does not replace diagnostics already stored with the turn summary", () => {
    const stored = { turn_token_accounting: { call_count: 2 } };

    expect(
      mergeTaskModelDiagnostics(
        { task_model_diagnostics: stored },
        { turn_token_accounting: { call_count: 9 } },
      ).task_model_diagnostics,
    ).toBe(stored);
  });
});

function mockJsonResponse(payload, ok = true) {
  return Promise.resolve({
    ok,
    text: async () => JSON.stringify(payload),
  });
}

function createDeferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function buildAppFetchMock({
  artifactResponse,
  agentSkillResponse,
  executionInputResponse,
  prepareUploadResponse,
  sessionLaneState = {},
  agentInteractionsResponse,
  agentEventsResponse,
  agentInteractionSubmitResponse,
  agentCancelResponse,
  instructionPreview = { compiled_id: "compiled-test" },
  messages = [],
  sessionUploads = [],
  sessions = [],
  onRequest,
} = {}) {
  return vi.fn(async (url, options = {}) => {
    onRequest?.(url, options);
    const normalizedUrl = String(url || "");
    if (normalizedUrl === "http://127.0.0.1:5000") {
      return { ok: true, text: async () => "" };
    }
    if (normalizedUrl.endsWith("/apps")) {
      return mockJsonResponse({
        applications: [
          {
            id: "app-1",
            name: "Bible Tutor",
            starter_questions: [],
          },
        ],
      });
    }
    if (normalizedUrl.includes("/exec/tools")) {
      return mockJsonResponse({ items: [] });
    }
    if (normalizedUrl.includes("/exec/skills?")) {
      return mockJsonResponse({ items: [] });
    }
    if (normalizedUrl.includes("/exec/agent-skills?")) {
      if (typeof agentSkillResponse === "function") {
        return agentSkillResponse(normalizedUrl);
      }
      return mockJsonResponse({ items: [], inventory_revision: null, projection_status: "unavailable" });
    }
    if (normalizedUrl.includes("/apps/app-1/sessions?")) {
      return mockJsonResponse({ sessions });
    }
    if (normalizedUrl.includes("/apps/app-1/documents")) {
      return mockJsonResponse({ documents: [] });
    }
    if (normalizedUrl.includes("/apps/app-1/instructions")) {
      return mockJsonResponse({
        instructions: null,
        instruction_understanding_status: {},
        instruction_understanding_preview: instructionPreview,
      });
    }
    if (
      normalizedUrl.includes("/apps/app-1")
      && !normalizedUrl.includes("/documents")
      && !normalizedUrl.includes("/instructions")
    ) {
      return mockJsonResponse({
        id: "app-1",
        name: "Bible Tutor",
        starter_questions: [],
        instruction_understanding_status: {},
        instruction_understanding_preview: instructionPreview,
      });
    }
    if (normalizedUrl.includes("/sessions/") && normalizedUrl.includes("/messages?")) {
      return mockJsonResponse({
        session_id: "session-1",
        messages,
        session_lane_state: sessionLaneState,
        workflow_status: null,
        diagnostics: {},
        session_uploads: sessionUploads,
        approved_content: [],
      });
    }
    if (normalizedUrl.includes("/executions/") && normalizedUrl.includes("/interactions?") && options.method !== "POST") {
      return typeof agentInteractionsResponse === "function"
        ? agentInteractionsResponse(normalizedUrl, options)
        : mockJsonResponse(agentInteractionsResponse || { items: [], session_lane_state: sessionLaneState });
    }
    if (normalizedUrl.includes("/executions/") && normalizedUrl.includes("/events?")) {
      return typeof agentEventsResponse === "function"
        ? agentEventsResponse(normalizedUrl, options)
        : mockJsonResponse(agentEventsResponse || { items: [], next_after_sequence: 0, session_lane_state: sessionLaneState });
    }
    if (normalizedUrl.includes("/interactions/") && normalizedUrl.endsWith("/responses") && options.method === "POST") {
      return typeof agentInteractionSubmitResponse === "function"
        ? agentInteractionSubmitResponse(normalizedUrl, options)
        : mockJsonResponse(agentInteractionSubmitResponse || { outcome: "applied", session_lane_state: sessionLaneState });
    }
    if (normalizedUrl.includes("/executions/") && normalizedUrl.endsWith("/cancel") && options.method === "POST") {
      return typeof agentCancelResponse === "function"
        ? agentCancelResponse(normalizedUrl, options)
        : mockJsonResponse(agentCancelResponse || { cancelled: true, status: "cancelled", session_lane_state: sessionLaneState });
    }
    if (normalizedUrl.includes("/sessions/") && normalizedUrl.includes("/artifacts?")) {
      if (typeof artifactResponse === "function") {
        return artifactResponse(normalizedUrl);
      }
      return mockJsonResponse({ items: [] });
    }
    if (normalizedUrl.endsWith("/execution-inputs") && options.method === "POST") {
      return typeof executionInputResponse === "function"
        ? executionInputResponse(normalizedUrl, options)
        : mockJsonResponse({});
    }
    if (normalizedUrl.includes("/prepare-for-execution") && options.method === "POST") {
      return typeof prepareUploadResponse === "function"
        ? prepareUploadResponse(normalizedUrl, options)
        : mockJsonResponse({});
    }
    return mockJsonResponse({});
  });
}

describe("interactive Agent execution", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads a pending interaction and submits an idempotent typed response", async () => {
    const requests = [];
    const lane = {
      execution_lane: {
        latest_execution_id: "execution_1",
        latest_execution_request_skill_id: "openclaw_cli",
        latest_status_result: { status: "running" },
        last_event_sequence: 3,
      },
    };
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "response-key-1") });
    vi.stubGlobal("fetch", buildAppFetchMock({
      sessions: [{ id: "session-1", title: "Interactive run" }],
      messages: [{ id: "msg_1", role: "assistant", content: "Agent is running.", retrieval_summary: {} }],
      sessionLaneState: lane,
      agentInteractionsResponse: {
        execution_id: "execution_1",
        items: [{
          interaction_id: "interaction_1",
          type: "approval",
          state: "pending",
          version: 2,
          sequence: 4,
          prompt: "Allow this external action?",
          options: [],
          expires_at: "2099-08-13T12:00:00Z",
        }],
        session_lane_state: lane,
      },
      agentEventsResponse: { items: [], next_after_sequence: 3, session_lane_state: lane },
      onRequest: (url, options) => requests.push([String(url), options]),
    }));

    render(<App />);

    expect(await screen.findByText(/allow this external action/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /allow once/i }));

    await waitFor(() => {
      const submitted = requests.find(([url, options]) => url.endsWith("/interactions/interaction_1/responses") && options.method === "POST");
      expect(submitted).toBeTruthy();
      expect(JSON.parse(submitted[1].body)).toMatchObject({
        app_id: "app-1",
        user_id: "user1",
        expected_version: 2,
        idempotency_key: "response-key-1",
        response: { kind: "approval", decision: "allow_once" },
      });
    });
  });
});

describe("resolveActiveAppDisplay", () => {
  it("prefers detailed app info only when it matches the selected app", () => {
    const selectedApp = {
      id: "app-b",
      name: "App B",
      starter_questions: ["B1", "B2"],
    };
    const staleAppInfo = {
      id: "app-a",
      name: "App A",
      starter_questions: ["A1", "A2"],
    };

    const display = resolveActiveAppDisplay(selectedApp, staleAppInfo, "app-b");

    expect(display.appName).toBe("App B");
    expect(display.starterQuestions).toEqual(["B1", "B2"]);
  });

  it("uses detailed app info when it matches the selected app", () => {
    const selectedApp = {
      id: "app-b",
      name: "App B",
      starter_questions: ["B1"],
    };
    const appInfo = {
      id: "app-b",
      name: "App B Detailed",
      starter_questions: ["BD1", "BD2"],
    };

    const display = resolveActiveAppDisplay(selectedApp, appInfo, "app-b");

    expect(display.appName).toBe("App B Detailed");
    expect(display.starterQuestions).toEqual(["BD1", "BD2"]);
  });
});

describe("resolveInstructionUnderstandingState", () => {
  it("marks compile required when preview is missing", () => {
    const state = resolveInstructionUnderstandingState({});

    expect(state.compileRequired).toBe(true);
    expect(state.message).toContain("run Recompile");
  });

  it("marks compile available when preview has a compiled id", () => {
    const state = resolveInstructionUnderstandingState({
      instruction_understanding_preview: {
        compiled_id: "compiled-1",
        compile_required: false,
      },
    });

    expect(state.compileRequired).toBe(false);
    expect(state.message).toBe("");
  });

  it("keeps compile required for hybrid apps when semantic validity is false", () => {
    const state = resolveInstructionUnderstandingState({
      instruction_understanding_preview: {
        compiled_id: "compiled-1",
        compile_required: false,
        semantic_compile_attached: true,
        semantic_compile_valid: false,
        primary_service_mode: "intent_routed_multi_workflow",
      },
    });

    expect(state.compileRequired).toBe(true);
    expect(state.message).toContain("run Recompile");
  });

  it("keeps compile available for interaction-logic apps when semantic model is valid", () => {
    const state = resolveInstructionUnderstandingState({
      instruction_understanding_preview: {
        compiled_id: "compiled-1",
        compile_required: false,
        semantic_compile_attached: true,
        semantic_compile_valid: true,
        primary_service_mode: "intent_routed_interaction_logic",
      },
    });

    expect(state.compileRequired).toBe(false);
    expect(state.message).toBe("");
  });
});

describe("applyApprovedContentSelectionToExecQuery", () => {
  it("injects the selected approved content id into @exec skill queries", () => {
    const nextQuery = applyApprovedContentSelectionToExecQuery(
      '@exec skill notebooklm_generate_video notebookTitle="GPT Application Designer"',
      "ac_123",
    );

    expect(nextQuery).toContain('approvedContentId="ac_123"');
  });

  it("injects the selected approved content id into @exec tool queries", () => {
    const nextQuery = applyApprovedContentSelectionToExecQuery(
      '@exec tool adapter.notebooklm.generate_video notebookTitle="GPT Application Designer"',
      "ac_123",
    );

    expect(nextQuery).toContain('approvedContentId="ac_123"');
  });

  it("does not change normal chat turns", () => {
    const nextQuery = applyApprovedContentSelectionToExecQuery(
      "Revise the last answer to be friendlier.",
      "ac_123",
    );

    expect(nextQuery).toBe("Revise the last answer to be friendlier.");
  });

  it("does not override an explicit approved content id", () => {
    const nextQuery = applyApprovedContentSelectionToExecQuery(
      '@exec skill notebooklm_generate_video approvedContentId="ac_explicit"',
      "ac_123",
    );

    expect(nextQuery).toBe('@exec skill notebooklm_generate_video approvedContentId="ac_explicit"');
  });
});

describe("buildExecCommand", () => {
  it("builds an async exec tool command with serialized arguments", () => {
    const command = buildExecCommand({
      commandKind: "tool",
      targetId: "adapter.notebooklm.generate_video",
      args: {
        notebookTitle: "GPT Application Designer",
        instructions: "Create a short intro video.",
      },
      executionMode: "async",
      approvedContentId: "ac_123",
    });

    expect(command).toContain("@exec async tool adapter.notebooklm.generate_video");
    expect(command).toContain('notebookTitle="GPT Application Designer"');
    expect(command).toContain('instructions="Create a short intro video."');
    expect(command).toContain('approvedContentId="ac_123"');
  });

  it("builds an agent exec command with an optional skill hint", () => {
    const command = buildExecCommand({
      commandKind: "agent",
      targetId: "codex_cli",
      args: {
        request: "Use NotebookLM to generate a Traditional Chinese study guide.",
        skillHint: "notebooklm",
      },
      executionMode: "sync",
    });

    expect(command).toBe('@exec codex use notebooklm "Use NotebookLM to generate a Traditional Chinese study guide."');
  });

  it("builds an async agent exec command without a skill hint", () => {
    const command = buildExecCommand({
      commandKind: "agent",
      targetId: "codex_cli",
      args: {
        request: "Summarize the approved content for Bible study beginners.",
      },
      executionMode: "async",
    });

    expect(command).toBe('@exec async codex "Summarize the approved content for Bible study beginners."');
  });

  it("builds an openclaw agent command", () => {
    const command = buildExecCommand({
      commandKind: "agent",
      targetId: "openclaw_cli",
      args: {
        request: "Reply with OK.",
      },
      executionMode: "sync",
    });

    expect(command).toBe('@exec openclaw "Reply with OK."');
  });

  it("builds an async openclaw agent command", () => {
    const command = buildExecCommand({
      commandKind: "agent",
      targetId: "openclaw_cli",
      args: {
        request: "Reply with OK.",
      },
      executionMode: "async",
    });

    expect(command).toBe('@exec async openclaw "Reply with OK."');
  });

  it("builds an OpenClaw command with a legacy provider skill hint", () => {
    const command = buildExecCommand({
      commandKind: "agent",
      targetId: "openclaw_cli",
      args: { request: "Summarize this.", skillHint: "summarizer" },
      executionMode: "sync",
    });

    expect(command).toBe('@exec openclaw use summarizer "Summarize this."');
  });

  it("builds structured execution_request metadata for agent composer submissions", () => {
    const executionRequest = buildExecutionRequestForComposer({
      commandKind: "agent",
      targetId: "openclaw_cli",
      executionMode: "async",
      args: {
        request: "Use selected artifacts.",
        artifactRefs: [
          {
            artifact_id: "artifact_chat",
            role: "source",
            reuse_mode: "inline_text",
          },
        ],
        expectedOutputs: [
          {
            output_id: "agent_output",
            artifact_type: "agent_output",
            persist_as_artifact: true,
          },
        ],
      },
    });

    expect(executionRequest).toEqual({
      request_type: "execute_agent",
      agent_backend: "openclaw_cli",
      execution_mode: "async",
      artifact_refs: [
        {
          artifact_id: "artifact_chat",
          role: "source",
          reuse_mode: "inline_text",
        },
      ],
      expected_outputs: [
        {
          output_id: "agent_output",
          artifact_type: "agent_output",
          persist_as_artifact: true,
        },
      ],
    });
  });

  it("builds structured execution metadata when only an Agent Skill is selected", () => {
    const executionRequest = buildExecutionRequestForComposer({
      commandKind: "agent",
      targetId: "codex_cli",
      executionMode: "sync",
      args: {
        request: "Find relevant papers.",
        agentSkillRef: {
          agent_skill_id: "agent-skill-1",
          approved_fingerprint: "sha256:v1:abc",
        },
      },
    });

    expect(executionRequest).toEqual({
      request_type: "execute_agent",
      agent_backend: "codex_cli",
      execution_mode: "sync",
      agent_skill_ref: {
        agent_skill_id: "agent-skill-1",
        approved_fingerprint: "sha256:v1:abc",
      },
    });
  });
});

describe("buildExecutionSubmitErrorTurn", () => {
  it("builds an actionable execution error turn from backend artifact failures", () => {
    const turn = buildExecutionSubmitErrorTurn(
      '@exec tool mcp.gmail.create_draft_with_attachments artifactIds=\'["artifact_missing"]\'',
      new Error('{"detail":"Artifact `artifact_missing` was not found in this session."}'),
    );

    expect(turn.role).toBe("assistant");
    expect(turn.content).toContain("Execution request failed before submission.");
    expect(turn.content).toContain("Artifact `artifact_missing` was not found in this session.");
    expect(turn.content).toContain("Select a current-session artifact");
    expect(turn.retrievalSummary.execution_override).toBe(true);
    expect(turn.retrievalSummary.command).toBe("tool");
    expect(turn.retrievalSummary.target_id).toBe("mcp.gmail.create_draft_with_attachments");
    expect(turn.retrievalSummary.execution_submit_result.error.code).toBe("EXECUTION_SUBMIT_FAILED");
  });
});

describe("classifyAssistantTurn", () => {
  it("marks execution override turns distinctly", () => {
    const result = classifyAssistantTurn({
      retrievalSummary: { execution_override: true },
    });

    expect(result.label).toBe("Execution");
  });

  it("marks approval events distinctly", () => {
    const result = classifyAssistantTurn({
      retrievalSummary: { approval_event: true },
    });

    expect(result.label).toBe("Approval");
  });
});

describe("buildExecutionResultPreview", () => {
  it("builds a compact notebook list preview for read-only tool results", () => {
    const preview = buildExecutionResultPreview({
      retrievalSummary: {
        execution_override: true,
        command: "tool",
        target_id: "adapter.notebooklm.list_notebooks",
        execution_submit_result: {
          status: "completed",
          result: {
            notebooks: [
              { title: "Notebook A" },
              { title: "Notebook B" },
            ],
          },
        },
      },
    });

    expect(preview).toContain("NotebookLM notebooks (2)");
    expect(preview).toContain("Notebook A");
  });

  it("returns empty preview for non-tool execution turns", () => {
    const preview = buildExecutionResultPreview({
      retrievalSummary: {
        execution_override: true,
        command: "skill",
        execution_submit_result: {
          status: "completed",
          result: { notebooks: [{ title: "Notebook A" }] },
        },
      },
    });

    expect(preview).toBe("");
  });

  it("builds a compact draft-created preview for Gmail tool results", () => {
    const preview = buildExecutionResultPreview({
      retrievalSummary: {
        execution_override: true,
        command: "tool",
        target_id: "mcp.gmail.create_draft",
        execution_submit_result: {
          status: "completed",
          result: {
            id: "draft_123",
            status: "draft",
          },
        },
      },
    });

    expect(preview).toBe("Draft created: draft_123");
  });

  it("builds a compact page-created preview for CMS tool results", () => {
    const preview = buildExecutionResultPreview({
      retrievalSummary: {
        execution_override: true,
        command: "tool",
        target_id: "mcp.cms.create_page",
        execution_submit_result: {
          status: "completed",
          result: {
            id: "page_123",
            title: "Launch Plan",
          },
        },
      },
    });

    expect(preview).toBe("Page created: Launch Plan");
  });

  it("builds a compact drive export preview for download tool results", () => {
    const preview = buildExecutionResultPreview({
      retrievalSummary: {
        execution_override: true,
        command: "tool",
        target_id: "mcp.gdrive.download_file_content",
        execution_submit_result: {
          status: "completed",
          result: {
            file_id: "file_123",
            name: "quarterly-plan.pdf",
          },
        },
      },
    });

    expect(preview).toBe("Drive file exported: quarterly-plan.pdf");
  });

  it("builds a compact generation-task preview for notebooklm generate tool results", () => {
    const preview = buildExecutionResultPreview({
      retrievalSummary: {
        execution_override: true,
        command: "tool",
        target_id: "adapter.notebooklm.generate_video",
        execution_submit_result: {
          status: "completed",
          result: {
            artifact_kind: "video",
            status: "submitted",
            task_id: "task_123",
          },
        },
      },
    });

    expect(preview).toBe("Video submitted: task_123");
  });

  it("builds a compact Codex-agent preview for completed agent runs", () => {
    const preview = buildExecutionResultPreview({
      retrievalSummary: {
        execution_override: true,
        command: "codex",
        execution_submit_result: {
          status: "completed",
          result: {
            user_summary: {
              status: "completed",
              title: "NotebookLM question answered",
              subtitle: "GPT Application Designer",
              preview: "Learning GPT design offers transformative advantages that extend far beyond traditional programming.",
            },
            activated_skills: ["notebooklm"],
            tool_summary: ["notebooklm: generate study guide"],
            artifacts: [{ artifact_id: "artifact_1" }],
          },
        },
      },
    });

    expect(preview).toContain("NotebookLM question answered (GPT Application Designer)");
    expect(preview).toContain("Learning GPT design offers transformative advantages");
  });

  it("builds a compact Codex-agent preview for confirmation-required runs", () => {
    const preview = buildExecutionResultPreview({
      retrievalSummary: {
        execution_override: true,
        command: "codex",
        execution_submit_result: {
          status: "pending_confirmation",
          result: {
            risk_class: "agent_external_write",
          },
        },
      },
    });

    expect(preview).toBe("Codex confirmation required (external write)");
  });

  it("renders authoritative Codex failed, partial, processing, and verified states", () => {
    const message = (status, result) => ({
      retrievalSummary: {
        execution_override: true,
        command: "codex",
        execution_status_result: { status, result },
      },
    });

    expect(buildExecutionResultPreview(message("failed", {
      summary: "Required operation was not run.",
      provider_metadata: { raw_exit_code: 0 },
    }))).toBe("Codex failed: Required operation was not run.");
    expect(buildExecutionResultPreview(message("partial", {
      summary: "Source added; report not started.",
    }))).toBe("Codex partially completed: Source added; report not started.");
    expect(buildExecutionResultPreview(message("completed", {
      summary: "Generation started; external output is still processing.",
      operation_verification: [{ status: "processing", required: true }],
    }))).toBe("Codex generation started: Generation started; external output is still processing.");
    expect(buildExecutionResultPreview(message("completed", {
      summary: "All required operations were independently verified.",
      operation_verification: [{ status: "completed", level: "independently_verified" }],
    }))).toBe("Codex completed: All required operations were independently verified.");
  });

  it("renders authoritative OpenClaw running, partial, and failed states", () => {
    const baseMessage = {
      retrievalSummary: {
        execution_override: true,
        command: "openclaw",
      },
    };

    expect(
      buildExecutionResultPreview({
        ...baseMessage,
        retrievalSummary: {
          ...baseMessage.retrievalSummary,
          execution_submit_result: { status: "running", result: {} },
        },
      }),
    ).toBe("OpenClaw execution is running");
    expect(
      buildExecutionResultPreview({
        ...baseMessage,
        retrievalSummary: {
          ...baseMessage.retrievalSummary,
          execution_submit_result: {
            status: "partial",
            result: { summary: "Optional artifact persistence failed." },
          },
        },
      }),
    ).toBe(
      "OpenClaw execution completed with warnings: Optional artifact persistence failed.",
    );
    expect(
      buildExecutionResultPreview({
        ...baseMessage,
        retrievalSummary: {
          ...baseMessage.retrievalSummary,
          execution_submit_result: {
            status: "failed",
            result: {
              diagnostics: { failure_message: "Required output was missing." },
            },
          },
        },
      }),
    ).toBe("OpenClaw execution failed: Required output was missing.");
  });

  it("builds a compact OpenClaw-agent preview from normalized result metadata", () => {
    const preview = buildExecutionResultPreview({
      retrievalSummary: {
        execution_override: true,
        command: "openclaw",
        target_id: "openclaw_cli",
        execution_status_result: {
          status: "completed",
          result: {
            backend: "openclaw_cli",
            status: "completed",
            summary: "OpenClaw completed and verified 1 output(s).",
            output_text: "Created a markdown summary for the approved content.",
            artifacts: [{ artifact_id: "artifact_1" }],
            provider_metadata: {
              provider_name: "OpenClaw",
              verified_output_count: 1,
              required_output_count: 1,
            },
          },
        },
      },
    });

    expect(preview).toContain("OpenClaw completed");
    expect(preview).toContain("Created a markdown summary");
    expect(preview).toContain("Verified outputs: 1/1");
    expect(preview).toContain("Artifacts: 1");
  });
});

describe("App artifact fetch propagation", () => {
  beforeEach(() => {
    uploadArtifactMock.mockReset();
    vi.stubGlobal("crypto", {
      ...globalThis.crypto,
      randomUUID: vi.fn(() => "session-1"),
    });
    vi.stubGlobal("fetch", buildAppFetchMock({
      sessions: [{ id: "session-1", title: "Persisted session" }],
      artifactResponse: () => Promise.resolve({
        ok: false,
        text: async () => "Artifact backend unavailable.",
      }),
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("does not request artifacts for a draft session that is not persisted yet", async () => {
    const requests = [];
    vi.stubGlobal("fetch", buildAppFetchMock({
      sessions: [],
      onRequest: (url) => requests.push(String(url)),
      artifactResponse: () => {
        throw new Error("artifact inventory must not be requested for a draft session");
      },
    }));

    render(<App />);

    expect(await screen.findByRole("heading", { name: /artifact library/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(requests.some((url) => url.includes("/apps/app-1/sessions?"))).toBe(true);
    });
    expect(requests.some((url) => url.includes("/sessions/session-1/artifacts?"))).toBe(false);
    expect(screen.getByText(/no artifacts have been saved in this session yet/i)).toBeInTheDocument();
  });

  it("shows the artifact fetch failure inside Artifact Library", async () => {
    render(<App />);

    expect(await screen.findByRole("heading", { name: /artifact library/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/unable to load artifacts: artifact backend unavailable\./i)).toBeInTheDocument();
    });
  });

  it("shows execution subsystem artifact warnings from a successful response", async () => {
    vi.stubGlobal("fetch", buildAppFetchMock({
      sessions: [{ id: "session-1", title: "Persisted session" }],
      artifactResponse: () => mockJsonResponse({
        items: [],
        warning: "Execution subsystem is unavailable.",
      }),
    }));

    render(<App />);

    expect(await screen.findByRole("heading", { name: /artifact library/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/unable to load artifacts: execution subsystem is unavailable\./i)).toBeInTheDocument();
    });
  });

  it("shows the artifact loading state while the session artifact request is in flight", async () => {
    const deferredArtifacts = createDeferred();
    vi.stubGlobal("fetch", buildAppFetchMock({
      sessions: [{ id: "session-1", title: "Persisted session" }],
      artifactResponse: () => deferredArtifacts.promise,
    }));

    render(<App />);

    expect(await screen.findByRole("heading", { name: /artifact library/i })).toBeInTheDocument();
    expect(await screen.findByText(/loading session artifacts/i)).toBeInTheDocument();

    deferredArtifacts.resolve({
      ok: true,
      text: async () => JSON.stringify({ items: [] }),
    });
    await waitFor(() => {
      expect(screen.getByText(/no artifacts have been saved in this session yet/i)).toBeInTheDocument();
    });
  });

  it("shows the true empty-session state when artifacts load successfully with no items", async () => {
    vi.stubGlobal("fetch", buildAppFetchMock({
      sessions: [{ id: "session-1", title: "Persisted session" }],
      artifactResponse: () => mockJsonResponse({ items: [] }),
    }));

    render(<App />);

    expect(await screen.findByRole("heading", { name: /artifact library/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/no artifacts have been saved in this session yet/i)).toBeInTheDocument();
    });
  });

  it("shows the artifact-first chat reuse labels in a populated session", async () => {
    vi.stubGlobal("fetch", buildAppFetchMock({
      sessions: [{ id: "session-1", title: "Persisted session" }],
      artifactResponse: () => mockJsonResponse({ items: [] }),
      messages: [
        {
          id: "msg_1",
          role: "assistant",
          content: "Reusable assistant answer.",
          retrieval_summary: {},
        },
      ],
    }));

    render(<App />);

    const selectForReuse = await screen.findByRole("button", { name: /select for reuse/i });
    expect(screen.getByRole("button", { name: /create reuse artifact \(0\)/i })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /save selected chat/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /approve this reply/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /mark reviewed/i })).toBeInTheDocument();

    fireEvent.click(selectForReuse);

    expect(screen.getByRole("button", { name: /create reuse artifact \(1\)/i })).toBeEnabled();
  });

  it("posts agent composer artifact refs and expected outputs as execution_request", async () => {
    const requests = [];
    vi.stubGlobal("fetch", buildAppFetchMock({
      sessions: [{ id: "session-1", title: "Persisted session" }],
      onRequest: (url, options) => requests.push({ url: String(url || ""), options }),
      artifactResponse: () => mockJsonResponse({
        items: [
          {
            artifact_id: "artifact_chat",
            display_name: "Reviewed Chat.md",
            artifact_type: "chat_export",
            mime_type: "text/markdown",
            consumption: {
              default_mode: "inline_text",
              supported_modes: ["inline_text", "file_backed"],
            },
          },
        ],
      }),
    }));

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /run tool or skill/i }));
    fireEvent.change(screen.getByLabelText("Mode"), { target: { value: "agent" } });
    fireEvent.change(screen.getByLabelText("Agent Backend"), { target: { value: "openclaw_cli" } });
    fireEvent.click(screen.getAllByLabelText(/reviewed chat\.md/i)[0]);
    fireEvent.change(screen.getByLabelText("Agent Request"), {
      target: { value: "Use the selected artifact to write a study note." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    await waitFor(() => {
      const chatPost = requests.find((request) => request.url.includes("/sessions/") && request.url.endsWith("/chat"));
      expect(chatPost).toBeTruthy();
      const body = JSON.parse(chatPost.options.body);
      expect(body.user_query).toBe('@exec openclaw "Use the selected artifact to write a study note."');
      expect(body.execution_request).toMatchObject({
        request_type: "execute_agent",
        agent_backend: "openclaw_cli",
        execution_mode: "sync",
        artifact_refs: [
          {
            artifact_id: "artifact_chat",
            role: "source",
            reuse_mode: "inline_text",
          },
        ],
      });
      expect(body.execution_request.expected_outputs[0]).toMatchObject({
        output_id: "agent_output",
        artifact_type: "agent_output",
        persist_as_artifact: true,
      });
    });
  });

  it("uploads an Agent artifact through the canonical operation and submits only its artifact ref", async () => {
    const requests = [];
    const preparedInput = {
      status: "ready",
      artifact: {
        artifact_id: "artifact_video", display_name: "video.mp4", artifact_type: "session_upload",
        mime_type: "video/mp4", status: "ready",
        consumption: { default_mode: "file_backed", supported_modes: ["file_backed"] },
      },
    };
    uploadArtifactMock.mockResolvedValue(preparedInput);
    vi.stubGlobal("fetch", buildAppFetchMock({
      sessions: [],
      onRequest: (url, options) => requests.push({ url: String(url || ""), options }),
      artifactResponse: () => mockJsonResponse({ items: [preparedInput.artifact] }),
    }));

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /run tool or skill/i }));
    fireEvent.change(screen.getByLabelText("Mode"), { target: { value: "agent" } });
    const file = new File(["video-bytes"], "video.mp4", { type: "video/mp4" });
    fireEvent.change(screen.getAllByLabelText("Upload artifact")[1], { target: { files: [file] } });
    await waitFor(() => expect(screen.getAllByText(/video\.mp4.*file backed/i)).toHaveLength(2));
    fireEvent.change(screen.getByLabelText("Agent Request"), { target: { value: "Publish the selected video." } });
    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    await waitFor(() => expect(requests.some((request) => request.url.endsWith("/chat"))).toBe(true));
    expect(requests.some((request) => request.url.endsWith("/prepare"))).toBe(true);
    expect(uploadArtifactMock).toHaveBeenCalledWith(expect.objectContaining({
      appId: "app-1",
      userId: "user1",
      sessionId: "session-1",
      file,
      analysisMode: "none",
    }));
    const chatBody = JSON.parse(requests.find((request) => request.url.endsWith("/chat")).options.body);
    expect(chatBody.execution_request.artifact_refs).toEqual([
      { artifact_id: "artifact_video", role: "attachment", reuse_mode: "file_backed" },
    ]);
    expect(JSON.stringify(chatBody)).not.toMatch(/C:\\\\|\/mnt\//);
  });

  it("uses the canonical normal-query upload without rendering a session-file inventory", async () => {
    const requests = [];
    uploadArtifactMock.mockResolvedValue({
      status: "ready",
      artifact: {
        artifact_id: "artifact_notes", display_name: "notes.txt",
        artifact_type: "session_upload", mime_type: "text/plain", status: "ready",
      },
    });
    vi.stubGlobal("fetch", buildAppFetchMock({
      sessions: [{ id: "session-1", title: "Persisted session" }],
      onRequest: (url, options) => requests.push({ url: String(url || ""), options }),
      artifactResponse: () => mockJsonResponse({ items: [] }),
    }));
    render(<App />);
    const file = new File(["notes"], "notes.txt", { type: "text/plain" });

    fireEvent.change(await screen.findByLabelText("Upload artifact"), { target: { files: [file] } });

    await waitFor(() => expect(uploadArtifactMock).toHaveBeenCalledWith(expect.objectContaining({
      analysisMode: "normal_query", file,
    })));
    expect(screen.queryByText("Session Artifact Upload")).toBeNull();
    expect(screen.queryByText("Session files")).toBeNull();
    await waitFor(() => expect(requests.filter((request) => request.url.includes("/artifacts?")).length).toBeGreaterThan(1));
  });

  it("loads session-scoped Agent Skills and submits the approved immutable reference", async () => {
    const requests = [];
    vi.stubGlobal("fetch", buildAppFetchMock({
      sessions: [{ id: "session-1", title: "Persisted session" }],
      onRequest: (url, options) => requests.push({ url: String(url || ""), options }),
      agentSkillResponse: (url) => {
        const backend = new URL(url).searchParams.get("backend");
        return mockJsonResponse({
          inventory_revision: "builder-1:7:sha256:test",
          projection_status: "active",
          items: backend === "codex_cli"
            ? [{
                agent_skill_id: "agent-research",
                approved_fingerprint: "sha256:v1:research",
                backend: "codex_cli",
                display_name: "Research Papers",
                provider_skill_name: "research-paper-finder",
              }]
            : [],
        });
      },
    }));

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /run tool or skill/i }));
    fireEvent.change(screen.getByLabelText("Mode"), { target: { value: "agent" } });
    await waitFor(() => expect(screen.getByRole("option", { name: "Research Papers" })).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Agent Skill"), { target: { value: "agent-research" } });
    fireEvent.change(screen.getByLabelText("Agent Request"), { target: { value: "Find relevant papers." } });
    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    await waitFor(() => {
      const inventoryUrls = requests
        .map((request) => request.url)
        .filter((url) => url.includes("/sessions/session-1/exec/agent-skills?"));
      expect(inventoryUrls).toEqual(expect.arrayContaining([
        expect.stringContaining("app_id=app-1&user_id=user1&backend=codex_cli"),
        expect.stringContaining("app_id=app-1&user_id=user1&backend=openclaw_cli"),
      ]));
      const chatPost = requests.find((request) => request.url.endsWith("/sessions/session-1/chat"));
      const body = JSON.parse(chatPost.options.body);
      expect(body.user_query).toBe('@exec codex use research-paper-finder "Find relevant papers."');
      expect(body.execution_request.agent_skill_ref).toEqual({
        agent_skill_id: "agent-research",
        approved_fingerprint: "sha256:v1:research",
      });
    });
  });

  it("refreshes only the active scoped Agent Skill inventory while Composer is open", async () => {
    const requests = [];
    vi.stubGlobal("fetch", buildAppFetchMock({
      sessions: [{ id: "session-1", title: "Persisted session" }],
      onRequest: (url, options) => requests.push({ url: String(url || ""), options }),
      agentSkillResponse: () => mockJsonResponse({
        inventory_revision: "builder-1:9:sha256:refresh",
        projection_status: "active",
        items: [],
      }),
    }));
    render(<App />);

    fireEvent(window, new Event("focus"));
    expect(requests.filter((request) => request.url.includes("/exec/agent-skills?")).length).toBe(0);

    fireEvent.click(await screen.findByRole("button", { name: /run tool or skill/i }));
    fireEvent.change(screen.getByLabelText("Mode"), { target: { value: "agent" } });
    await waitFor(() => expect(
      requests.filter((request) => request.url.includes("/exec/agent-skills?")).length,
    ).toBe(2));

    fireEvent.change(screen.getByLabelText("Agent Backend"), {
      target: { value: "openclaw_cli" },
    });
    await waitFor(() => expect(
      requests.filter((request) => request.url.includes("backend=openclaw_cli")).length,
    ).toBe(2));

    fireEvent(window, new Event("focus"));
    await waitFor(() => expect(
      requests.filter((request) => request.url.includes("backend=openclaw_cli")).length,
    ).toBe(3));
    fireEvent.click(screen.getByRole("button", { name: "Refresh Agent Skills" }));
    await waitFor(() => expect(
      requests.filter((request) => request.url.includes("backend=openclaw_cli")).length,
    ).toBe(4));

    const inventoryRequests = requests.filter((request) => request.url.includes("/exec/agent-skills?"));
    expect(inventoryRequests.every((request) => request.url.includes("app_id=app-1"))).toBe(true);
    expect(inventoryRequests.every((request) => request.url.includes("user_id=user1"))).toBe(true);

    fireEvent.click(within(screen.getByRole("region", { name: "Execution Composer" }))
      .getByRole("button", { name: "Close" }));
    const countAfterClose = requests.filter((request) => request.url.includes("/exec/agent-skills?")).length;
    fireEvent(window, new Event("focus"));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(requests.filter((request) => request.url.includes("/exec/agent-skills?")).length).toBe(countAfterClose);
  });

  it("preserves selected Agent Skill when refresh returns the same inventory revision", async () => {
    let codexCalls = 0;
    vi.stubGlobal("fetch", buildAppFetchMock({
      sessions: [{ id: "session-1", title: "Persisted session" }],
      agentSkillResponse: (url) => {
        const backend = new URL(url).searchParams.get("backend");
        if (backend !== "codex_cli") {
          return mockJsonResponse({
            inventory_revision: "builder-1:10:sha256:same",
            projection_status: "active",
            items: [],
          });
        }
        codexCalls += 1;
        return mockJsonResponse({
          inventory_revision: "builder-1:10:sha256:same",
          projection_status: "active",
          items: codexCalls === 1
            ? [{
                agent_skill_id: "agent-stable",
                approved_fingerprint: "sha256:v1:stable",
                backend: "codex_cli",
                display_name: "Stable Skill",
                provider_skill_name: "stable-skill",
              }]
            : [],
        });
      },
    }));
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /run tool or skill/i }));
    fireEvent.change(screen.getByLabelText("Mode"), { target: { value: "agent" } });
    await waitFor(() => expect(screen.getByRole("option", { name: "Stable Skill" })).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Agent Skill"), {
      target: { value: "agent-stable" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Refresh Agent Skills" }));

    await waitFor(() => expect(codexCalls).toBe(2));
    expect(screen.getByLabelText("Agent Skill")).toHaveValue("agent-stable");
    expect(screen.getByRole("option", { name: "Stable Skill" })).toBeInTheDocument();
  });

  it("prepares a draft session before loading Agent Skills in Composer", async () => {
    const requests = [];
    vi.stubGlobal("fetch", buildAppFetchMock({
      sessions: [],
      onRequest: (url, options) => requests.push({ url: String(url || ""), options }),
      agentSkillResponse: (url) => {
        const backend = new URL(url).searchParams.get("backend");
        return mockJsonResponse({
          inventory_revision: "builder-1:8:sha256:draft",
          projection_status: "active",
          items: backend === "codex_cli"
            ? [{
                agent_skill_id: "agent-notebooklm",
                approved_fingerprint: "sha256:v1:notebooklm",
                backend: "codex_cli",
                display_name: "notebooklm",
                provider_skill_name: "notebooklm",
              }]
            : [],
        });
      },
    }));

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /run tool or skill/i }));
    fireEvent.change(screen.getByLabelText("Mode"), { target: { value: "agent" } });

    await waitFor(() => expect(screen.getByRole("option", { name: "notebooklm" })).toBeInTheDocument());
    const prepareRequest = requests.find((request) => (
      request.url.includes("/sessions/")
      && request.url.endsWith("/prepare")
      && request.options.method === "POST"
    ));
    expect(prepareRequest).toBeTruthy();
    const preparedSessionId = prepareRequest.url.match(/\/sessions\/([^/]+)\/prepare$/)?.[1];
    expect(preparedSessionId).toBeTruthy();
    expect(requests.some((request) => (
      request.url.includes(`/sessions/${preparedSessionId}/exec/agent-skills?`)
      && request.url.includes("backend=codex_cli")
    ))).toBe(true);
  });

  it("opens Composer in Agent mode when reusing an agent output execution artifact", async () => {
    vi.stubGlobal("fetch", buildAppFetchMock({
      sessions: [{ id: "session-1", title: "Persisted session" }],
      artifactResponse: () => mockJsonResponse({
        items: [
          {
            artifact_id: "artifact_agent",
            display_name: "Agent Output - Study Notes.md",
            artifact_type: "agent_output",
            mime_type: "text/markdown",
            consumption: {
              default_mode: "inline_text",
              supported_modes: ["inline_text", "file_backed"],
            },
            capabilities: {
              can_reuse: true,
              can_open: true,
              can_preview: true,
            },
            routes: {
              open: "/sessions/session-1/artifacts/artifact_agent/file",
              preview: "/sessions/session-1/artifacts/artifact_agent/preview",
            },
          },
        ],
      }),
      messages: [
        {
          id: "msg_agent_output",
          role: "assistant",
          content: "OpenClaw completed and saved a reusable output.",
          retrieval_summary: {
            execution_override: true,
            command: "openclaw",
            target_id: "openclaw_cli",
            execution_status_result: {
              status: "completed",
              result: {
                artifacts: [
                  {
                    artifact_id: "artifact_agent",
                    artifact_type: "agent_output",
                    display_name: "Agent Output - Study Notes.md",
                    mime_type: "text/markdown",
                    routes: {
                      open: "/sessions/session-1/artifacts/artifact_agent/file",
                      preview: "/sessions/session-1/artifacts/artifact_agent/preview",
                    },
                    capabilities: {
                      can_reuse: true,
                      can_open: true,
                      can_preview: true,
                    },
                  },
                ],
              },
            },
          },
        },
      ],
    }));

    render(<App />);

    await screen.findByText(/openclaw completed and saved a reusable output/i);
    fireEvent.click(screen.getAllByRole("button", { name: /reuse in composer/i })[0]);

    expect(await screen.findByRole("heading", { name: /execution composer/i })).toBeInTheDocument();
    expect(screen.getByLabelText("Mode")).toHaveValue("agent");
    expect(screen.getByLabelText("Agent Backend")).toHaveValue("openclaw_cli");
    expect(screen.getByText(/selected artifacts \(1\)/i)).toBeInTheDocument();
    expect(screen.getByText(/agent output - study notes\.md \(inline text\)/i)).toBeInTheDocument();
  });
});
