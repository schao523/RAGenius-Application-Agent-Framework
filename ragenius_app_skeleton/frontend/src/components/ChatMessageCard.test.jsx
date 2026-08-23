import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ChatMessageCard from "./ChatMessageCard";

const styles = {
  messageCard: () => ({}),
  assistantMetaRow: {},
  messageRoleLabel: {},
  pill: {},
  statusWarn: {},
  messageBodyText: {},
  compactNote: {},
  actionRow: {},
  inlineActionButton: {},
  small: {},
};

describe("ChatMessageCard", () => {
  it("shows a mark reviewed action for assistant replies and calls the legacy approval handler", () => {
    const onApproveMessage = vi.fn();
    render(
      <ChatMessageCard
        message={{ role: "assistant", content: "Helpful reply" }}
        index={2}
        styles={styles}
        onOpenInspector={() => {}}
        onOpenSources={() => {}}
        onApproveMessage={onApproveMessage}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /mark reviewed/i }));
    expect(screen.queryByRole("button", { name: /approve this reply/i })).not.toBeInTheDocument();

    expect(onApproveMessage).toHaveBeenCalledWith(2);
  });

  it("does not show an approve action for user messages", () => {
    render(
      <ChatMessageCard
        message={{ role: "user", content: "User message" }}
        index={0}
        styles={styles}
        onOpenInspector={() => {}}
        onOpenSources={() => {}}
        onApproveMessage={() => {}}
      />,
    );

    expect(screen.queryByRole("button", { name: /mark reviewed/i })).toBeNull();
  });

  it("shows artifacts attached to a user message", () => {
    render(
      <ChatMessageCard
        message={{
          role: "user",
          content: "Summarize these notes.",
          retrievalSummary: {
            attached_artifact_refs: [{
              artifact_id: "artifact-notes",
              display_name: "notes.txt",
              mime_type: "text/plain",
              role: "attachment",
            }],
          },
        }}
        index={0}
        styles={styles}
        onOpenInspector={() => {}}
        onOpenSources={() => {}}
        onApproveMessage={() => {}}
      />,
    );

    expect(screen.getByText("notes.txt")).toBeInTheDocument();
    expect(screen.getByText("Attached")).toBeInTheDocument();
  });

  it("shows reuse selection controls for selectable messages", () => {
    const onToggleSelectedForExport = vi.fn();
    render(
      <ChatMessageCard
        message={{ id: "msg_1", role: "user", content: "User message" }}
        index={0}
        styles={styles}
        selectable
        selectedForExport={false}
        onToggleSelectedForExport={onToggleSelectedForExport}
        onOpenInspector={() => {}}
        onOpenSources={() => {}}
        onApproveMessage={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /select for reuse/i }));

    expect(onToggleSelectedForExport).toHaveBeenCalledWith("msg_1");
  });

  it("toggles reuse selection when the message card body is clicked", () => {
    const onToggleSelectedForExport = vi.fn();
    render(
      <ChatMessageCard
        message={{ id: "msg_2", role: "assistant", content: "Assistant message" }}
        index={0}
        styles={styles}
        selectable
        selectedForExport={false}
        onToggleSelectedForExport={onToggleSelectedForExport}
        onOpenInspector={() => {}}
        onOpenSources={() => {}}
        onApproveMessage={() => {}}
      />,
    );

    fireEvent.click(screen.getByText("Assistant message"));

    expect(onToggleSelectedForExport).toHaveBeenCalledWith("msg_2");
  });

  it("uses execution-specific actions for execution turns", () => {
    const onOpenInspector = vi.fn();
    const onRefreshExecutionStatus = vi.fn();
    const onRetryExecution = vi.fn();
    render(
      <ChatMessageCard
        message={{
          id: "msg_exec",
          role: "assistant",
          content: "Execution submitted.",
          retrievalSummary: {
            execution_override: true,
          },
        }}
        index={1}
        styles={styles}
        onOpenInspector={onOpenInspector}
        onOpenSources={() => {}}
        onRefreshExecutionStatus={onRefreshExecutionStatus}
        onRetryExecution={onRetryExecution}
      />,
    );

    expect(screen.getByRole("button", { name: /execution details/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /sources/i })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /execution details/i }));
    fireEvent.click(screen.getByRole("button", { name: /refresh status/i }));
    fireEvent.click(screen.getByRole("button", { name: /^retry$/i }));
    expect(onOpenInspector).toHaveBeenCalledWith(1);
    expect(onRefreshExecutionStatus).toHaveBeenCalled();
    expect(onRetryExecution).toHaveBeenCalled();
  });

  it("shows a confirm action for pending-confirmation execution turns", () => {
    const onConfirmExecution = vi.fn();
    render(
      <ChatMessageCard
        message={{
          id: "msg_exec_pending",
          role: "assistant",
          content: "Execution pending confirmation.",
          retrievalSummary: {
            execution_override: true,
            execution_submit_result: {
              execution_id: "execution_123",
              status: "pending_confirmation",
            },
          },
        }}
        index={1}
        styles={styles}
        onOpenInspector={() => {}}
        onOpenSources={() => {}}
        onRefreshExecutionStatus={() => {}}
        onRetryExecution={() => {}}
        onConfirmExecution={onConfirmExecution}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /^confirm$/i }));
    expect(onConfirmExecution).toHaveBeenCalled();
  });

  it("shows a compact execution result preview when provided", () => {
    render(
      <ChatMessageCard
        message={{
          id: "msg_exec",
          role: "assistant",
          content: "Execution completed.",
          retrievalSummary: {
            execution_override: true,
          },
        }}
        executionResultPreview="NotebookLM notebooks (2): Notebook A, Notebook B"
        index={1}
        styles={styles}
        onOpenInspector={() => {}}
        onOpenSources={() => {}}
      />,
    );

    expect(screen.getByText(/notebooklm notebooks \(2\)/i)).toBeInTheDocument();
  });

  it("does not create file links from execution inventory paths", () => {
    render(
      <ChatMessageCard
        message={{
          id: "msg_export",
          role: "assistant",
          content: "Saved 1 selected message(s) as `session-1-chat-export.md`.",
          retrievalSummary: {
            execution_override: true,
            command: "export",
            execution_submit_result: {
              status: "completed",
              result: {
                artifacts: [
                  {
                    artifact_id: "artifact_123",
                    artifact_type: "chat_export",
                    display_name: "session-1-chat-export.md",
                    summary: "Chat export from 1 selected message",
                    file_path: "D:\\GitHub\\Codex-RAGenius-System\\ragenius_execution_subsystem\\storage\\artifacts\\app-1\\chat_export\\artifact_123-session-1-chat-export.md",
                  },
                ],
              },
            },
          },
        }}
        index={1}
        styles={styles}
        onOpenInspector={() => {}}
        onOpenSources={() => {}}
      />,
    );

    expect(screen.getAllByText(/session-1-chat-export\.md/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/chat export from 1 selected message/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /open saved file/i })).toBeNull();
    expect(screen.queryByText(/saved file:/i)).toBeNull();
  });

  it("renders artifact reuse actions for export confirmation turns with backend routes", () => {
    const onUseArtifactInComposer = vi.fn();
    const onViewArtifactLibrary = vi.fn();
    render(
      <ChatMessageCard
        message={{
          id: "msg_export_route",
          role: "assistant",
          content: "Created reuse artifact: Chat Export - Bible observation questions.md",
          retrievalSummary: {
            execution_override: true,
            command: "export",
            artifact_export: true,
            export_artifact: {
              artifact_id: "artifact_1",
              artifact_type: "chat_export",
              display_name: "Chat Export - Bible observation questions.md",
              summary: "Chat export from 2 selected messages.",
              routes: {
                open: "/sessions/session-1/artifacts/artifact_1/file",
                preview: "/sessions/session-1/artifacts/artifact_1/preview",
              },
              capabilities: {
                can_open: true,
                can_preview: true,
                can_reuse: true,
              },
            },
          },
        }}
        index={1}
        styles={styles}
        baseUrl="http://127.0.0.1:8012"
        onUseArtifactInComposer={onUseArtifactInComposer}
        onViewArtifactLibrary={onViewArtifactLibrary}
        onOpenInspector={() => {}}
        onOpenSources={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /reuse in composer/i }));
    fireEvent.click(screen.getByRole("button", { name: /view in artifact library/i }));

    expect(onUseArtifactInComposer).toHaveBeenCalledWith(
      expect.objectContaining({ artifact_id: "artifact_1" }),
      expect.any(Object),
    );
    expect(onViewArtifactLibrary).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("link", { name: /open saved file/i })).toHaveAttribute(
      "href",
      "http://127.0.0.1:8012/sessions/session-1/artifacts/artifact_1/file",
    );
  });

  it("does not fall back to nested execution result filesystem paths", () => {
    render(
      <ChatMessageCard
        message={{
          id: "msg_export_nested",
          role: "assistant",
          content: "Saved 1 selected message(s) as `session-1-chat-export.md`.",
          retrievalSummary: {
            execution_override: true,
            command: "export",
            artifact_export: true,
            export_artifact: {
              name: "session-1-chat-export.md",
            },
            execution_submit_result: {
              status: "completed",
              result: {
                path: "D:\\GitHub\\Codex-RAGenius-System\\ragenius_execution_subsystem\\storage\\artifacts\\app-1\\chat_export\\artifact_123.json",
                file_path: "D:\\GitHub\\Codex-RAGenius-System\\ragenius_execution_subsystem\\storage\\artifacts\\app-1\\chat_export\\artifact_123-session-1-chat-export.md",
              },
            },
          },
        }}
        index={1}
        styles={styles}
        onOpenInspector={() => {}}
        onOpenSources={() => {}}
      />,
    );

    expect(screen.queryByRole("link", { name: /open saved file/i })).toBeNull();
    expect(screen.queryByText(/saved file:/i)).toBeNull();
  });

  it("uses approval-specific actions for approval turns", () => {
    const onOpenInspector = vi.fn();
    render(
      <ChatMessageCard
        message={{
          id: "msg_approval",
          role: "assistant",
          content: "Approved revision selected.",
          retrievalSummary: {
            approval_event: true,
          },
        }}
        index={3}
        styles={styles}
        onOpenInspector={onOpenInspector}
        onOpenSources={() => {}}
        onApproveMessage={() => {}}
      />,
    );

    expect(screen.getByRole("button", { name: /view revision/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /sources/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /mark reviewed/i })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /view revision/i }));
    expect(onOpenInspector).toHaveBeenCalledWith(3);
  });

  it("renders reviewed artifact actions for mark-reviewed confirmation turns", () => {
    const onUseArtifactInComposer = vi.fn();
    const onViewArtifactLibrary = vi.fn();
    render(
      <ChatMessageCard
        message={{
          id: "msg_reviewed",
          role: "assistant",
          content: "Marked reviewed and saved `Reviewed Chat - Helpful reply.md` for reuse.",
          retrievalSummary: {
            approval_event: true,
            reviewed_artifact: {
              artifact_id: "artifact_reviewed_1",
              artifact_type: "chat_export",
              display_name: "Reviewed Chat - Helpful reply.md",
              summary: "Reviewed chat content saved for reuse.",
              reviewed: true,
              routes: {
                open: "/sessions/session-1/artifacts/artifact_reviewed_1/file",
                preview: "/sessions/session-1/artifacts/artifact_reviewed_1/preview",
              },
              capabilities: {
                can_open: true,
                can_preview: true,
                can_reuse: true,
              },
            },
          },
        }}
        index={3}
        styles={styles}
        baseUrl="http://127.0.0.1:8012"
        onUseArtifactInComposer={onUseArtifactInComposer}
        onViewArtifactLibrary={onViewArtifactLibrary}
        onOpenInspector={() => {}}
        onOpenSources={() => {}}
        onApproveMessage={() => {}}
      />,
    );

    expect(screen.getAllByText(/reviewed chat - helpful reply\.md/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/chat_export \| reviewed/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /reuse in composer/i }));
    fireEvent.click(screen.getByRole("button", { name: /view in artifact library/i }));
    expect(onUseArtifactInComposer).toHaveBeenCalledWith(
      expect.objectContaining({ artifact_id: "artifact_reviewed_1", reviewed: true }),
      expect.any(Object),
    );
    expect(onViewArtifactLibrary).toHaveBeenCalledTimes(1);
  });

  it("renders agent output artifact actions and passes agent reuse context", () => {
    const onUseArtifactInComposer = vi.fn();
    const onViewArtifactLibrary = vi.fn();
    render(
      <ChatMessageCard
        message={{
          id: "msg_agent_output",
          role: "assistant",
          content: "OpenClaw completed and saved a reusable output.",
          retrievalSummary: {
            execution_override: true,
            command: "openclaw",
            target_id: "openclaw_cli",
            execution_status_result: {
              status: "completed",
              result: {
                artifacts: [
                  {
                    artifact_id: "artifact_agent_1",
                    artifact_type: "agent_output",
                    display_name: "Agent Output - Study Notes.md",
                    summary: "Verified OpenClaw output saved for reuse.",
                    mime_type: "text/markdown",
                    routes: {
                      preview: "/sessions/session-1/artifacts/artifact_agent_1/preview",
                      open: "/sessions/session-1/artifacts/artifact_agent_1/file",
                    },
                    capabilities: {
                      can_open: true,
                      can_preview: true,
                      can_reuse: true,
                    },
                  },
                ],
              },
            },
          },
        }}
        index={4}
        styles={styles}
        baseUrl="http://127.0.0.1:8012"
        onUseArtifactInComposer={onUseArtifactInComposer}
        onViewArtifactLibrary={onViewArtifactLibrary}
        onOpenInspector={() => {}}
        onOpenSources={() => {}}
        onRefreshExecutionStatus={() => {}}
        onRetryExecution={() => {}}
        selectable
        onToggleSelectedForExport={() => {}}
        onApproveMessage={() => {}}
      />,
    );

    expect(screen.getByText(/agent output - study notes\.md/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /preview/i })).toHaveAttribute(
      "href",
      "http://127.0.0.1:8012/sessions/session-1/artifacts/artifact_agent_1/preview",
    );
    expect(screen.getByRole("link", { name: /preview/i })).toHaveAttribute("target", "_blank");
    expect(screen.getByRole("link", { name: /open saved file/i })).toHaveAttribute(
      "href",
      "http://127.0.0.1:8012/sessions/session-1/artifacts/artifact_agent_1/file",
    );
    expect(screen.getByRole("link", { name: /open saved file/i })).toHaveAttribute("target", "_blank");
    expect(screen.queryByRole("button", { name: /select for reuse/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /mark reviewed/i })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /reuse in composer/i }));
    fireEvent.click(screen.getByRole("button", { name: /view in artifact library/i }));

    expect(onUseArtifactInComposer).toHaveBeenCalledWith(
      expect.objectContaining({ artifact_id: "artifact_agent_1", artifact_type: "agent_output" }),
      expect.objectContaining({ commandKind: "agent", agentBackend: "openclaw_cli" }),
    );
    expect(onViewArtifactLibrary).toHaveBeenCalledTimes(1);
  });

  it("does not expose an unpersisted provider-relative output as an openable file", () => {
    render(
      <ChatMessageCard
        message={{
          id: "msg_codex_temporary_output",
          role: "assistant",
          content: "Codex completed and reported a temporary output.",
          retrievalSummary: {
            execution_override: true,
            command: "codex",
            target_id: "codex_cli",
            execution_status_result: {
              status: "completed",
              result: {
                artifacts: [{
                  path: "outputs/study-report.md",
                  media_type: "text/markdown",
                }],
              },
            },
          },
        }}
        index={5}
        styles={styles}
        baseUrl="http://127.0.0.1:8012"
        onOpenInspector={() => {}}
        onOpenSources={() => {}}
        onRefreshExecutionStatus={() => {}}
        onRetryExecution={() => {}}
      />,
    );

    expect(screen.queryByRole("link", { name: /open saved file/i })).toBeNull();
    expect(screen.queryByText(/outputs\/study-report\.md/i)).toBeNull();
  });
});
