import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  default as App,
  applyApprovedContentSelectionToExecQuery,
  buildExecutionResultPreview,
  buildExecutionSubmitErrorTurn,
  buildExecCommand,
  classifyAssistantTurn,
  resolveActiveAppDisplay,
  resolveInstructionUnderstandingState,
} from "./App";

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
  messages = [],
} = {}) {
  return vi.fn(async (url) => {
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
    if (normalizedUrl.includes("/apps/app-1/sessions?")) {
      return mockJsonResponse({ sessions: [] });
    }
    if (normalizedUrl.includes("/apps/app-1/documents")) {
      return mockJsonResponse({ documents: [] });
    }
    if (normalizedUrl.includes("/apps/app-1/instructions")) {
      return mockJsonResponse({
        instructions: null,
        instruction_understanding_status: {},
        instruction_understanding_preview: {},
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
      });
    }
    if (normalizedUrl.includes("/sessions/") && normalizedUrl.includes("/messages?")) {
      return mockJsonResponse({
        session_id: "session-1",
        messages,
        session_lane_state: {},
        workflow_status: null,
        diagnostics: {},
        session_uploads: [],
        approved_content: [],
      });
    }
    if (normalizedUrl.includes("/sessions/") && normalizedUrl.includes("/artifacts?")) {
      if (typeof artifactResponse === "function") {
        return artifactResponse(normalizedUrl);
      }
      return mockJsonResponse({ items: [] });
    }
    return mockJsonResponse({});
  });
}

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
});

describe("App artifact fetch propagation", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", buildAppFetchMock({
      artifactResponse: () => Promise.resolve({
        ok: false,
        text: async () => "Artifact backend unavailable.",
      }),
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
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
});
