import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ExecutionInspector from "./ExecutionInspector";

const styles = {
  inspectorPane: {},
  card: {},
  inspectorHeader: {},
  secondaryButton: {},
  small: {},
  inspectorTabRow: {},
  inspectorTab: () => ({}),
  inspectorSection: {},
  inspectorGroup: {},
  inspectorGroupTitle: {},
  inspectorKeyValue: {},
  debugCode: {},
  sourceList: {},
};

describe("ExecutionInspector", () => {
  it("renders execution-specific summary and request details", () => {
    render(
      <ExecutionInspector
        open
        tab="summary"
        onChangeTab={vi.fn()}
        onClose={vi.fn()}
        message={{
          retrievalSummary: {
            execution_override: true,
            command: "tool",
            target_id: "adapter.notebooklm.generate_video",
            approved_revision_id: "rev_1",
            execution_intent: {
              mapped_input: {
                notebookTitle: "GPT Application Designer",
              },
            },
            execution_submit_result: {
              execution_id: "execution_123",
              status: "submitted",
              task_id: "task_123",
            },
          },
        }}
        sessionLaneState={{
          execution_lane: {
            latest_execution_id: "execution_123",
            latest_async_task_status: "submitted",
          },
        }}
        styles={styles}
      />,
    );

    expect(screen.getByText(/execution details/i)).toBeInTheDocument();
    expect(screen.getByText(/command:/i)).toBeInTheDocument();
    expect(screen.getByText(/tool/i)).toBeInTheDocument();
    expect(screen.getByText(/adapter.notebooklm.generate_video/i)).toBeInTheDocument();
    expect(screen.getByText(/rev_1/i)).toBeInTheDocument();
    expect(screen.getByText(/execution_123/i)).toBeInTheDocument();
    expect(screen.getByText(/task_123/i)).toBeInTheDocument();
  });

  it("renders Codex-agent-specific tabs and details", () => {
    render(
      <ExecutionInspector
        open
        tab="skills"
        onChangeTab={vi.fn()}
        onClose={vi.fn()}
        message={{
          retrievalSummary: {
            execution_override: true,
            command: "codex",
            target_id: "codex_cli",
            skill_id: "codex_cli:notebooklm",
            agent_query: "Use NotebookLM to create a study guide.",
            agent_skill_hint: "notebooklm",
            approved_revision_id: "rev_1",
            execution_submit_result: {
              status: "completed",
              result: {
                final_message: "Codex completed the NotebookLM task.",
                activated_skills: ["notebooklm"],
                tool_summary: ["notebooklm: generate study guide"],
                artifacts: [
                  {
                    artifact_id: "artifact_1",
                    artifact_type: "report",
                    name: "study-guide.md",
                    path: "/tmp/study-guide.md",
                  },
                ],
                policy_class: "agent_read_only",
                workspace_access: "none",
                network_access: "allowlisted",
              },
            },
          },
        }}
        sessionLaneState={{
          execution_lane: {
            latest_execution_id: "execution_codex_1",
          },
        }}
        styles={styles}
      />,
    );

    expect(screen.getByRole("button", { name: /skills/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /tools/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /artifacts/i })).toBeInTheDocument();
    expect(screen.getByText("Activated skills")).toBeInTheDocument();
    expect(screen.getByText(/notebooklm/i)).toBeInTheDocument();
  });

  it("renders OpenClaw normalized output and verification metadata", () => {
    render(
      <ExecutionInspector
        open
        tab="summary"
        onChangeTab={vi.fn()}
        onClose={vi.fn()}
        message={{
          retrievalSummary: {
            execution_override: true,
            command: "openclaw",
            target_id: "openclaw_cli",
            agent_backend: "openclaw_cli",
            agent_query: "Create a markdown summary.",
            execution_status_result: {
              execution_id: "execution_openclaw_1",
              status: "completed",
              result: {
                backend: "openclaw_cli",
                status: "completed",
                summary: "OpenClaw completed and verified 1 output(s).",
                output_text: "Created a markdown summary for the approved content.",
                provider_metadata: {
                  provider_name: "OpenClaw",
                  execution_mode: "output_required",
                  verified_output_count: 1,
                  required_output_count: 1,
                  expected_output_count: 1,
                },
                verification_results: [
                  {
                    output_id: "openclaw_answer",
                    workspace_relative_path: "outputs/openclaw_answer-openclaw-result.md",
                    verified: true,
                    exists: true,
                  },
                ],
              },
            },
          },
        }}
        sessionLaneState={{ execution_lane: {} }}
        styles={styles}
      />,
    );

    expect(screen.getByText(/openclaw result/i)).toBeInTheDocument();
    expect(screen.getByText(/provider:/i)).toBeInTheDocument();
    expect(screen.getByText(/^OpenClaw$/)).toBeInTheDocument();
    expect(screen.getByText(/execution mode:/i)).toBeInTheDocument();
    expect(screen.getByText(/output_required/i)).toBeInTheDocument();
    expect(screen.getByText(/verified outputs:/i)).toBeInTheDocument();
    expect(screen.getByText("1 / 1")).toBeInTheDocument();
    expect(screen.getByText(/Created a markdown summary/i)).toBeInTheDocument();
    expect(screen.getByText(/outputs\/openclaw_answer-openclaw-result\.md/i)).toBeInTheDocument();
  });

  it("prefers the selected execution turn payload over latest session-lane execution state", () => {
    render(
      <ExecutionInspector
        open
        tab="summary"
        onChangeTab={vi.fn()}
        onClose={vi.fn()}
        message={{
          retrievalSummary: {
            execution_override: true,
            command: "tool",
            target_id: "adapter.notebooklm.list_notebooks",
            execution_submit_result: {
              execution_id: "execution_old_123",
              status: "completed",
              task_id: "task_old_123",
            },
          },
        }}
        sessionLaneState={{
          execution_lane: {
            latest_execution_id: "execution_new_456",
            latest_async_task_id: "task_new_456",
            latest_async_task_status: "running",
            latest_execution_result: {
              execution_id: "execution_new_456",
              status: "running",
            },
          },
        }}
        styles={styles}
      />,
    );

    expect(screen.getByText(/execution_old_123/i)).toBeInTheDocument();
    expect(screen.getByText(/task_old_123/i)).toBeInTheDocument();
    expect(screen.queryByText(/execution_new_456/i)).toBeNull();
    expect(screen.queryByText(/task_new_456/i)).toBeNull();
  });

  it("shows an artifacts tab for non-agent execution turns when artifacts are present", () => {
    render(
      <ExecutionInspector
        open
        tab="artifacts"
        onChangeTab={vi.fn()}
        onClose={vi.fn()}
        message={{
          retrievalSummary: {
            execution_override: true,
            command: "tool",
            target_id: "save_chat_export_artifact",
            execution_submit_result: {
              execution_id: "execution_artifact_1",
              status: "completed",
              result: {
                artifacts: [
                  {
                    artifact_id: "artifact_1",
                    artifact_type: "chat_export",
                    display_name: "session-1-chat-export.md",
                    summary: "Chat export from 1 selected message",
                    file_path: "D:\\exports\\session-1-chat-export.md",
                    consumption: {
                      default_mode: "file_backed",
                      supported_modes: ["file_backed", "inline_text", "metadata_only"],
                    },
                    eligible_consumers: ["export", "future_markdown_processors"],
                  },
                ],
              },
            },
          },
        }}
        sessionLaneState={{ execution_lane: {} }}
        styles={styles}
      />,
    );

    expect(screen.getByRole("button", { name: /artifacts/i })).toBeInTheDocument();
    expect(screen.getAllByText(/session-1-chat-export\.md/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/chat export from 1 selected message/i)).toBeInTheDocument();
    expect(screen.getByText(/default reuse mode: file backed/i)).toBeInTheDocument();
    expect(screen.getByText(/supported reuse modes: file backed, inline text, metadata only/i)).toBeInTheDocument();
    expect(screen.getByText(/eligible consumers: export, future_markdown_processors/i)).toBeInTheDocument();
    expect(screen.getByText(/d:\\exports\\session-1-chat-export\.md/i)).toBeInTheDocument();
  });

  it("shows artifact field mapping and resolved reuse mode from the execution request", () => {
    render(
      <ExecutionInspector
        open
        tab="request"
        onChangeTab={vi.fn()}
        onClose={vi.fn()}
        message={{
          retrievalSummary: {
            execution_override: true,
            command: "tool",
            target_id: "mcp.gmail.create_draft_with_attachments",
            execution_intent: {
              mapped_input: {
                to: "alice@example.com",
                artifactIds: ["artifact_pdf"],
              },
            },
            execution_submit_result: {
              execution_id: "execution_attach_1",
              status: "completed",
              result: {
                artifacts: [
                  {
                    artifact_id: "artifact_pdf",
                    artifact_type: "google_drive_export",
                    display_name: "Execution Summary.pdf",
                    mime_type: "application/pdf",
                    consumption: {
                      default_mode: "binary_payload",
                      supported_modes: ["binary_payload", "file_backed", "metadata_only"],
                    },
                  },
                ],
              },
            },
          },
        }}
        sessionLaneState={{ execution_lane: {} }}
        styles={styles}
      />,
    );

    expect(screen.getByText(/submitted artifact inputs/i)).toBeInTheDocument();
    expect(screen.getByText(/artifactIds -> Execution Summary\.pdf/i)).toBeInTheDocument();
    expect(screen.getByText(/Resolved mode: binary payload/i)).toBeInTheDocument();
  });

  it("shows artifact reuse summary from resolved request artifact refs", () => {
    render(
      <ExecutionInspector
        open
        tab="request"
        onChangeTab={vi.fn()}
        onClose={vi.fn()}
        message={{
          retrievalSummary: {
            command: "tool",
            target_id: "mcp.gmail.create_draft_with_attachments",
            skill_id: "gmail_create_draft_with_attachments",
            execution_intent: {
              mapped_input: {
                artifactIds: ["artifact_pdf"],
                artifactRefs: [
                  {
                    artifact_id: "artifact_pdf",
                    field_name: "artifactIds",
                    display_name: "Execution Summary.pdf",
                    consumption: {
                      resolved_mode: "binary_payload",
                    },
                  },
                ],
              },
            },
            execution_submit_result: {
              execution_id: "execution_123",
              status: "completed",
              result: { status: "completed" },
            },
          },
        }}
        sessionLaneState={{}}
        styles={styles}
      />,
    );

    expect(screen.getByText(/submitted artifact inputs/i)).toBeInTheDocument();
    expect(screen.getByText(/artifactIds -> Execution Summary\.pdf/i)).toBeInTheDocument();
    expect(screen.getByText(/Resolved mode: binary payload/i)).toBeInTheDocument();
  });

  it("labels produced artifacts separately from submitted artifact inputs", () => {
    render(
      <ExecutionInspector
        open
        tab="artifacts"
        onChangeTab={vi.fn()}
        onClose={vi.fn()}
        message={{
          retrievalSummary: {
            execution_override: true,
            command: "tool",
            target_id: "save_chat_export_artifact",
            execution_submit_result: {
              status: "completed",
              result: {
                artifacts: [
                  {
                    artifact_id: "artifact_output",
                    artifact_type: "chat_export",
                    display_name: "Chat Export.md",
                  },
                ],
              },
            },
          },
        }}
        sessionLaneState={{}}
        styles={styles}
      />,
    );

    expect(screen.getByText(/produced artifacts/i)).toBeInTheDocument();
    expect(screen.queryByText(/submitted artifact inputs/i)).toBeNull();
  });
});
