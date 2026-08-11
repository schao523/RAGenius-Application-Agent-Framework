import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ExecutionComposer from "./ExecutionComposer";

const styles = {
  card: {},
  executionLaneHeader: {},
  sectionTitle: {},
  small: {},
  row: {},
  secondaryButton: {},
  formGrid: {},
  label: {},
  select: {},
  compactNote: {},
  input: {},
  textarea: {},
  error: {},
  actionRow: {},
  button: {},
};

describe("ExecutionComposer", () => {
  it("uses the unified upload control and removes session preparation controls", async () => {
    const onUploadExecutionInput = vi.fn().mockResolvedValue({
      status: "ready",
      artifact: {
        artifact_id: "artifact_video", display_name: "video.mp4",
        artifact_type: "session_upload", mime_type: "video/mp4", status: "ready",
      },
    });
    render(<ExecutionComposer
      toolInventory={[]} skillInventory={[]} artifactInventory={[]}
      initialCommandKind="agent" onUploadExecutionInput={onUploadExecutionInput}
      onSubmit={vi.fn()} onClose={vi.fn()} styles={styles}
    />);

    expect(screen.getByLabelText("Upload artifact")).toBeInTheDocument();
    expect(screen.queryByLabelText("Select session file")).toBeNull();
    expect(screen.queryByRole("button", { name: "Prepare selected file" })).toBeNull();
    const file = new File(["video"], "video.mp4", { type: "video/mp4" });
    await act(async () => fireEvent.change(screen.getByLabelText("Upload artifact"), {
      target: { files: [file] },
    }));
    await waitFor(() => expect(screen.getAllByText(/video\.mp4/i).length).toBeGreaterThan(0));
  });

  it("uploads and automatically selects a prepared Agent input", async () => {
    const onSubmit = vi.fn();
    const onUploadExecutionInput = vi.fn().mockResolvedValue({
      status: "ready",
      artifact: {
        artifact_id: "artifact_video", display_name: "video.mp4", artifact_type: "session_upload",
        mime_type: "video/mp4", status: "ready",
        consumption: { default_mode: "file_backed", supported_modes: ["file_backed"] },
      },
    });
    render(<ExecutionComposer
      toolInventory={[]} skillInventory={[]} artifactInventory={[]}
      initialCommandKind="agent" onUploadExecutionInput={onUploadExecutionInput}
      onSubmit={onSubmit} onClose={vi.fn()} styles={styles}
    />);
    fireEvent.change(screen.getByLabelText("Agent Request"), { target: { value: "Publish this video." } });
    const file = new File(["video-bytes"], "video.mp4", { type: "video/mp4" });
    await act(async () => fireEvent.change(screen.getByLabelText("Upload artifact"), { target: { files: [file] } }));
    await waitFor(() => expect(screen.getAllByText(/video\.mp4.*file backed/i)).toHaveLength(2));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Run" })));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      args: expect.objectContaining({
        artifactRefs: [{ artifact_id: "artifact_video", role: "attachment", reuse_mode: "file_backed" }],
      }),
    }));
  });

  it("renders tool and skill modes and schema-driven fields", async () => {
    render(
      <ExecutionComposer
        toolInventory={[
          {
            tool_id: "adapter.notebooklm.generate_video",
            name: "NotebookLM Generate Video",
            description: "Generate a video.",
            input_schema: {
              type: "object",
              properties: {
                notebookTitle: { type: "string" },
                instructions: { type: "string" },
              },
              required: ["instructions"],
            },
          },
        ]}
        skillInventory={[
          {
            skill_id: "notebooklm-video-generator",
            name: "NotebookLM Video Generator",
            description: "Published skill.",
            input_schema: {
              type: "object",
              properties: {
                notebookTitle: { type: "string" },
              },
            },
          },
        ]}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
        styles={styles}
      />,
    );

    expect(screen.getByLabelText("Mode")).toBeInTheDocument();
    expect(screen.getByLabelText("Target")).toBeInTheDocument();
    expect(screen.getByLabelText("Execution Mode")).toBeInTheDocument();
    expect(screen.getByLabelText("instructions")).toBeInTheDocument();
    expect(screen.getByText("Required arguments")).toBeInTheDocument();
    expect(screen.queryByLabelText("notebookTitle")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /optional arguments/i }));
    expect(screen.getByLabelText("notebookTitle")).toBeInTheDocument();
  });

  it("applies the dedicated scrollable composer card style when provided", () => {
    render(
      <ExecutionComposer
        toolInventory={[
          {
            tool_id: "adapter.notebooklm.add_source_file",
            name: "NotebookLM Add Source File",
            description: "Upload a file source.",
            input_schema: {
              type: "object",
              properties: {
                filePath: { type: "string" },
                notebookTitle: { type: "string" },
                title: { type: "string" },
              },
              required: ["filePath"],
            },
          },
        ]}
        skillInventory={[]}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
        styles={{
          ...styles,
          card: { border: "1px solid #dbeafe" },
          executionComposerCard: {
            maxHeight: "72vh",
            overflowY: "auto",
          },
        }}
      />,
    );

    expect(screen.getByLabelText("Execution Composer")).toHaveStyle({
      maxHeight: "72vh",
      overflowY: "auto",
    });
  });

  it("submits structured payload from schema-driven form fields", async () => {
    const onSubmit = vi.fn();
    render(
      <ExecutionComposer
        toolInventory={[
          {
            tool_id: "adapter.notebooklm.generate_video",
            name: "NotebookLM Generate Video",
            description: "Generate a video.",
            input_schema: {
              type: "object",
              properties: {
                notebookTitle: { type: "string" },
                instructions: { type: "string" },
              },
              required: ["instructions"],
            },
          },
        ]}
        skillInventory={[]}
        onSubmit={onSubmit}
        onClose={vi.fn()}
        styles={styles}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /optional arguments/i }));
    fireEvent.change(screen.getByLabelText("notebookTitle"), { target: { value: "GPT Application Designer" } });
    fireEvent.change(screen.getByLabelText("instructions"), { target: { value: "Create a short intro video." } });
    fireEvent.change(screen.getByLabelText("Execution Mode"), { target: { value: "async" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run" }));
    });

    expect(onSubmit).toHaveBeenCalledWith({
      commandKind: "tool",
      targetId: "adapter.notebooklm.generate_video",
      executionMode: "async",
      args: expect.objectContaining({
        notebookTitle: "GPT Application Designer",
        instructions: "Create a short intro video.",
        execution_mode: "async",
      }),
    });
  });

  it("filters disabled inventory rows and parses array fields from comma-separated input", async () => {
    const onSubmit = vi.fn();
    render(
      <ExecutionComposer
        toolInventory={[
          {
            tool_id: "disabled.tool",
            name: "Disabled Tool",
            enabled: false,
            exec_capable: false,
            input_schema: { type: "object", properties: {} },
          },
          {
            tool_id: "adapter.notebooklm.ask",
            name: "NotebookLM Ask",
            description: "Ask a notebook question.",
            exec_capable: true,
            enabled: true,
            input_schema: {
              type: "object",
              properties: {
                notebookTitle: { type: "string" },
                sourceIds: { type: "array", items: { type: "string" } },
              },
            },
          },
        ]}
        skillInventory={[]}
        onSubmit={onSubmit}
        onClose={vi.fn()}
        styles={styles}
      />,
    );

    expect(screen.queryByText("Disabled Tool")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /optional arguments/i }));
    fireEvent.change(screen.getByLabelText("notebookTitle"), { target: { value: "GPT Application Designer" } });
    fireEvent.change(screen.getByLabelText("sourceIds"), { target: { value: "src1, src2" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run" }));
    });

    expect(onSubmit).toHaveBeenCalledWith({
      commandKind: "tool",
      targetId: "adapter.notebooklm.ask",
      executionMode: "sync",
      args: expect.objectContaining({
        notebookTitle: "GPT Application Designer",
        sourceIds: ["src1", "src2"],
      }),
    });
  });

  it("shows running state and surfaces submit errors without closing itself", async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error("Execution request failed."));
    render(
      <ExecutionComposer
        toolInventory={[
          {
            tool_id: "adapter.notebooklm.list_notebooks",
            name: "NotebookLM List Notebooks",
            description: "List notebooks.",
            input_schema: {
              type: "object",
              properties: {},
            },
          },
        ]}
        skillInventory={[]}
        onSubmit={onSubmit}
        onClose={vi.fn()}
        styles={styles}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    expect(screen.getByRole("button", { name: /running/i })).toBeDisabled();
    await waitFor(() => expect(screen.getByText(/execution request failed/i)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Run" })).toBeEnabled();
  });

  it("shows enriched descriptions, required fields first, and collapses optional arguments by default", async () => {
    render(
      <ExecutionComposer
        toolInventory={[
          {
            tool_id: "adapter.notebooklm.generate_report",
            name: "NotebookLM Generate Report",
            description: "Generate a notebook report.",
            exec_binding_skill_id: "notebooklm_generate_report",
            input_schema: {
              type: "object",
              properties: {
                instructions: { type: "string", description: "What the report should cover." },
                notebookTitle: { type: "string", description: "Notebook title." },
                audience: { type: "string", default: "general" },
              },
              required: ["instructions"],
            },
          },
        ]}
        skillInventory={[]}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
        styles={styles}
      />,
    );

    expect(screen.getByText("Generate a notebook report.")).toBeInTheDocument();
    expect(screen.getByText(/runtime tool \| adapter\.notebooklm\.generate_report/i)).toBeInTheDocument();
    expect(screen.getByText(/execution contract \| notebooklm_generate_report/i)).toBeInTheDocument();
    expect(screen.getByText("Required arguments")).toBeInTheDocument();
    expect(screen.getByLabelText("instructions")).toBeInTheDocument();
    expect(screen.queryByLabelText("notebookTitle")).toBeNull();
    expect(screen.queryByLabelText("audience")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /optional arguments/i }));

    expect(screen.getByLabelText("notebookTitle")).toBeInTheDocument();
    expect(screen.getByLabelText("audience")).toBeInTheDocument();
    expect(screen.getByText("Default: general")).toBeInTheDocument();
  });

  it("renders fields from composed allOf schemas used by refined tool definitions", async () => {
    render(
      <ExecutionComposer
        toolInventory={[
          {
            tool_id: "adapter.notebooklm.ask",
            name: "NotebookLM Ask",
            description: "Ask a question against an existing NotebookLM notebook.",
            exec_binding_skill_id: "notebooklm_existing_notebook_ask",
            input_schema: {
              allOf: [
                {
                  type: "object",
                  properties: {
                    notebookId: { type: "string" },
                    notebookTitle: { type: "string" },
                    question: { type: "string" },
                    sourceIds: { type: "array", items: { type: "string" } },
                    conversationId: { type: "string" },
                  },
                  required: ["question"],
                },
                {
                  anyOf: [{ required: ["notebookId"] }, { required: ["notebookTitle"] }],
                },
              ],
            },
          },
        ]}
        skillInventory={[]}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
        styles={styles}
      />,
    );

    expect(screen.getByLabelText("question")).toBeInTheDocument();
    expect(screen.queryByLabelText("notebookTitle")).toBeNull();
    expect(screen.getByText(/one of these argument groups is required/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /optional arguments/i }));

    expect(screen.getByLabelText("notebookTitle")).toBeInTheDocument();
    expect(screen.getByLabelText("notebookId")).toBeInTheDocument();
    expect(screen.getByLabelText("sourceIds")).toBeInTheDocument();
    expect(screen.getByLabelText("conversationId")).toBeInTheDocument();
  });

  it("distinguishes app-bound skills from runtime workflows in skill mode", async () => {
    render(
      <ExecutionComposer
        toolInventory={[]}
        skillInventory={[
          {
            skill_id: "gmail_drive_attachment_sender",
            name: "Gmail Drive Attachment Sender",
            inventory_source: "builder_bound",
            description: "Send a prepared Drive attachment by email.",
            input_schema: {
              type: "object",
              properties: {
                recipient: { type: "string" },
              },
              required: ["recipient"],
            },
          },
          {
            skill_id: "video_director_skill",
            name: "Video Director Skill",
            inventory_source: "runtime",
            workflow_kind: "multi_step_workflow",
            description: "Coordinate a multi-step video workflow.",
            input_schema: {
              type: "object",
              properties: {
                brief: { type: "string" },
              },
              required: ["brief"],
            },
          },
        ]}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
        styles={styles}
      />,
    );

    fireEvent.change(screen.getByLabelText("Mode"), { target: { value: "skill" } });

    expect(screen.getByText(/choose an app skill or runtime workflow/i)).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /gmail drive attachment sender \[app skill\]/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /video director skill \[workflow\]/i })).toBeInTheDocument();
    expect(screen.getByText(/app skill \| builder-bound published skill/i)).toBeInTheDocument();
    expect(screen.getByText(/skill id \| gmail_drive_attachment_sender/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Target"), { target: { value: "video_director_skill" } });

    expect(screen.getByText(/runtime workflow \| multi-step workflow/i)).toBeInTheDocument();
    expect(screen.getByText(/skill id \| video_director_skill/i)).toBeInTheDocument();
  });

  it("groups runtime tool targets by provider family", async () => {
    render(
      <ExecutionComposer
        toolInventory={[
          {
            tool_id: "adapter.notebooklm.list_notebooks",
            name: "NotebookLM List Notebooks",
            input_schema: { type: "object", properties: {} },
          },
          {
            tool_id: "mcp.gmail.search_messages",
            name: "Gmail Message Search",
            input_schema: { type: "object", properties: { query: { type: "string" } } },
          },
        ]}
        skillInventory={[]}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
        styles={styles}
      />,
    );

    expect(screen.getByRole("group", { name: /notebooklm tools/i })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: /gmail tools/i })).toBeInTheDocument();
  });

  it("supports agent mode with natural-language request and optional skill hint", async () => {
    const onSubmit = vi.fn();
    render(
      <ExecutionComposer
        toolInventory={[]}
        skillInventory={[]}
        agentSkillInventory={[
          {
            agent_skill_id: "agent-notebooklm",
            approved_fingerprint: "sha256:v1:notebooklm",
            backend: "codex_cli",
            display_name: "NotebookLM",
            provider_skill_name: "notebooklm",
          },
        ]}
        selectedApprovedContent={{ approved_content_id: "ac_123", revision_id: "rev_123" }}
        onSubmit={onSubmit}
        onClose={vi.fn()}
        styles={styles}
      />,
    );

    fireEvent.change(screen.getByLabelText("Mode"), { target: { value: "agent" } });

    expect(screen.getByText(/describe the task in natural language/i)).toBeInTheDocument();
    expect(screen.getByText(/selected approved revision \| rev_123/i)).toBeInTheDocument();
    expect(screen.getByText(/predicted policy \| read only/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Agent Skill"), { target: { value: "agent-notebooklm" } });
    fireEvent.change(screen.getByLabelText("Agent Request"), {
      target: { value: "Use NotebookLM to create a Traditional Chinese study guide for Micah 2." },
    });

    expect(screen.getByText(/predicted policy \| needs confirmation/i)).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run" }));
    });

    expect(onSubmit).toHaveBeenCalledWith({
      commandKind: "agent",
      targetId: "codex_cli",
      executionMode: "sync",
      args: {
        request: "Use NotebookLM to create a Traditional Chinese study guide for Micah 2.",
        skillHint: "notebooklm",
        agentSkillRef: {
          agent_skill_id: "agent-notebooklm",
          approved_fingerprint: "sha256:v1:notebooklm",
        },
        expectedOutputs: [
          expect.objectContaining({
            output_id: "agent_output",
            persist_as_artifact: true,
          }),
        ],
      },
    });
  });

  it("defaults agent backend to Codex CLI", () => {
    render(
      <ExecutionComposer
        toolInventory={[]}
        skillInventory={[]}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
        styles={styles}
      />,
    );

    fireEvent.change(screen.getByLabelText("Mode"), { target: { value: "agent" } });

    expect(screen.getByLabelText("Agent Backend")).toHaveValue("codex_cli");
    expect(screen.getByLabelText("Agent Skill")).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "NotebookLM" })).not.toBeInTheDocument();
  });

  it("filters approved Agent Skills by backend and resets selection", async () => {
    const onSubmit = vi.fn();
    render(
      <ExecutionComposer
        toolInventory={[]}
        skillInventory={[]}
        agentSkillInventory={[
          {
            agent_skill_id: "agent-codex",
            approved_fingerprint: "sha256:v1:codex",
            backend: "codex_cli",
            display_name: "Codex Research",
            provider_skill_name: "research-paper-finder",
          },
          {
            agent_skill_id: "agent-openclaw",
            approved_fingerprint: "sha256:v1:openclaw",
            backend: "openclaw_cli",
            display_name: "OpenClaw Summarizer",
            provider_skill_name: "summarizer",
          },
        ]}
        onSubmit={onSubmit}
        onClose={vi.fn()}
        styles={styles}
      />,
    );

    fireEvent.change(screen.getByLabelText("Mode"), { target: { value: "agent" } });
    fireEvent.change(screen.getByLabelText("Agent Skill"), { target: { value: "agent-codex" } });
    expect(screen.getByRole("option", { name: "Codex Research" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "OpenClaw Summarizer" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Agent Backend"), { target: { value: "openclaw_cli" } });

    expect(screen.getByLabelText("Agent Skill")).toHaveValue("");
    expect(screen.getByRole("option", { name: "OpenClaw Summarizer" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Codex Research" })).not.toBeInTheDocument();
    expect(screen.getByText(/openclaw agent mode/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Agent Skill"), { target: { value: "agent-openclaw" } });

    fireEvent.change(screen.getByLabelText("Agent Request"), {
      target: { value: "Reply with OK." },
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run" }));
    });

    expect(onSubmit).toHaveBeenCalledWith({
      commandKind: "agent",
      targetId: "openclaw_cli",
      executionMode: "sync",
      args: {
        request: "Reply with OK.",
        skillHint: "summarizer",
        agentSkillRef: {
          agent_skill_id: "agent-openclaw",
          approved_fingerprint: "sha256:v1:openclaw",
        },
        expectedOutputs: [
          expect.objectContaining({
            output_id: "agent_output",
            persist_as_artifact: true,
          }),
        ],
      },
    });
  });

  it("shows missing projection and inventory failures without inventing skills", () => {
    render(
      <ExecutionComposer
        toolInventory={[]}
        skillInventory={[]}
        agentSkillInventory={[]}
        agentSkillInventoryError="Inventory request failed."
        agentSkillProjectionStatusByBackend={{ codex_cli: "unavailable" }}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
        styles={styles}
      />,
    );

    fireEvent.change(screen.getByLabelText("Mode"), { target: { value: "agent" } });

    expect(screen.getByRole("option", { name: "Auto" })).toBeInTheDocument();
    expect(screen.getByText(/inventory request failed/i)).toBeInTheDocument();
    expect(screen.getByText(/approved skill projection is unavailable/i)).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "NotebookLM" })).not.toBeInTheDocument();
  });

  it("submits agent mode with selected artifacts and expected reusable output", async () => {
    const onSubmit = vi.fn();
    render(
      <ExecutionComposer
        toolInventory={[]}
        skillInventory={[]}
        artifactInventory={[
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
        ]}
        onSubmit={onSubmit}
        onClose={vi.fn()}
        styles={styles}
      />,
    );

    fireEvent.change(screen.getByLabelText("Mode"), { target: { value: "agent" } });
    fireEvent.change(screen.getByLabelText("Agent Backend"), { target: { value: "openclaw_cli" } });

    expect(screen.getByText(/agent artifacts/i)).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/reviewed chat\.md/i));
    fireEvent.change(screen.getByLabelText("Agent Request"), {
      target: { value: "Use the selected artifact to produce a concise study note." },
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run" }));
    });

    expect(onSubmit).toHaveBeenCalledWith({
      commandKind: "agent",
      targetId: "openclaw_cli",
      executionMode: "sync",
      args: {
        request: "Use the selected artifact to produce a concise study note.",
        artifactRefs: [
          {
            artifact_id: "artifact_chat",
            role: "source",
            reuse_mode: "inline_text",
          },
        ],
        expectedOutputs: [
          expect.objectContaining({
            output_id: "agent_output",
            artifact_type: "agent_output",
            persist_as_artifact: true,
          }),
        ],
      },
    });
  });

  it("renders an artifact picker for artifactIds fields and submits selected artifact ids", async () => {
    const onSubmit = vi.fn();
    render(
      <ExecutionComposer
        toolInventory={[
          {
            tool_id: "mcp.gmail.create_draft_with_attachments",
            name: "Gmail Create Draft With Attachments",
            description: "Create a Gmail draft with attachments.",
            artifact_picker: {
              enabled: true,
              field_name: "artifactIds",
              selection_mode: "multiple",
              allowed_artifact_types: ["google_drive_export", "chat_export"],
              allowed_mime_types: ["application/pdf", "text/markdown"],
              eligible_for: "attachments",
              accepted_artifact_types: ["google_drive_export", "chat_export"],
              required_consumption_mode: "binary_payload",
              max_artifact_count: 5,
            },
            input_schema: {
              type: "object",
              properties: {
                to: { type: "string" },
                subject: { type: "string" },
                body: { type: "string" },
                artifactIds: { type: "array", items: { type: "string" } },
              },
              required: ["to", "subject", "body", "artifactIds"],
            },
          },
        ]}
        skillInventory={[]}
        artifactInventory={[
          {
            artifact_id: "artifact_pdf",
            display_name: "Execution Summary.pdf",
            artifact_type: "google_drive_export",
            mime_type: "application/pdf",
            status: "ready",
            consumption: {
              default_mode: "binary_payload",
              supported_modes: ["binary_payload", "file_backed", "metadata_only"],
            },
          },
          {
            artifact_id: "artifact_md",
            display_name: "chat-export.md",
            artifact_type: "chat_export",
            mime_type: "text/markdown",
            status: "ready",
            consumption: {
              default_mode: "file_backed",
              supported_modes: ["file_backed", "inline_text", "binary_payload", "metadata_only"],
            },
          },
        ]}
        onSubmit={onSubmit}
        onClose={vi.fn()}
        styles={styles}
      />,
    );

    expect(screen.getByRole("checkbox", { name: /execution summary\.pdf/i })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /chat-export\.md/i })).toBeInTheDocument();
    expect(screen.getAllByText(/required consumption mode: binary payload/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/accepted artifact types: google_drive_export, chat_export/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/maximum artifacts: 5/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("to"), { target: { value: "alice@example.com" } });
    fireEvent.change(screen.getByLabelText("subject"), { target: { value: "Review" } });
    fireEvent.change(screen.getByLabelText("body"), { target: { value: "Please review the attached summary." } });
    fireEvent.click(screen.getByRole("checkbox", { name: /execution summary\.pdf/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /chat-export\.md/i }));

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run" }));
    });

    expect(onSubmit).toHaveBeenCalledWith({
      commandKind: "tool",
      targetId: "mcp.gmail.create_draft_with_attachments",
      executionMode: "sync",
      args: expect.objectContaining({
        to: "alice@example.com",
        subject: "Review",
        body: "Please review the attached summary.",
        artifactIds: ["artifact_pdf", "artifact_md"],
      }),
    });
    expect(screen.getByText(/execution summary\.pdf \(binary payload\)/i)).toBeInTheDocument();
    expect(screen.getByText(/reuse summary/i)).toBeInTheDocument();
    expect(screen.getByText(/artifact ids -> execution summary\.pdf/i)).toBeInTheDocument();
    expect(screen.getByText(/artifact ids -> chat-export\.md/i)).toBeInTheDocument();
    expect(screen.getAllByText(/resolved mode: binary payload/i)).toHaveLength(2);
  });

  it("removes a selected artifact from the picker before submission", async () => {
    const onSubmit = vi.fn();
    render(
      <ExecutionComposer
        toolInventory={[
          {
            tool_id: "mcp.gmail.create_draft_with_attachments",
            name: "Gmail Create Draft With Attachments",
            artifact_picker: {
              enabled: true,
              field_name: "artifactIds",
              selection_mode: "multiple",
              accepted_artifact_types: ["google_drive_export"],
              required_consumption_mode: "binary_payload",
            },
            input_schema: {
              type: "object",
              properties: {
                to: { type: "string" },
                subject: { type: "string" },
                body: { type: "string" },
                artifactIds: { type: "array", items: { type: "string" } },
              },
              required: ["to", "subject", "body"],
            },
          },
        ]}
        skillInventory={[]}
        artifactInventory={[
          {
            artifact_id: "artifact_pdf",
            display_name: "Execution Summary.pdf",
            artifact_type: "google_drive_export",
            mime_type: "application/pdf",
            status: "ready",
            consumption: {
              default_mode: "binary_payload",
              supported_modes: ["binary_payload", "file_backed", "metadata_only"],
            },
          },
        ]}
        onSubmit={onSubmit}
        onClose={vi.fn()}
        styles={styles}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /optional arguments/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /execution summary\.pdf/i }));
    expect(screen.getByText(/execution summary\.pdf \(binary payload\)/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("checkbox", { name: /execution summary\.pdf/i }));
    expect(screen.queryByText(/artifact ids -> execution summary\.pdf/i)).toBeNull();

    fireEvent.change(screen.getByLabelText("to"), { target: { value: "alice@example.com" } });
    fireEvent.change(screen.getByLabelText("subject"), { target: { value: "Review" } });
    fireEvent.change(screen.getByLabelText("body"), { target: { value: "Please review." } });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run" }));
    });

    expect(onSubmit).toHaveBeenCalledWith({
      commandKind: "tool",
      targetId: "mcp.gmail.create_draft_with_attachments",
      executionMode: "sync",
      args: expect.not.objectContaining({
        artifactIds: expect.anything(),
      }),
    });
  });

  it("uses checkboxes for multi-artifact fields and enforces the configured selection limit", async () => {
    render(
      <ExecutionComposer
        toolInventory={[
          {
            tool_id: "mcp.gmail.create_draft_with_attachments",
            name: "Gmail Create Draft With Attachments",
            artifact_picker: {
              enabled: true,
              field_name: "artifactIds",
              selection_mode: "multiple",
              accepted_artifact_types: ["google_drive_export"],
              required_consumption_mode: "binary_payload",
              max_artifact_count: 2,
            },
            input_schema: {
              type: "object",
              properties: {
                artifactIds: { type: "array", items: { type: "string" } },
              },
              required: ["artifactIds"],
            },
          },
        ]}
        skillInventory={[]}
        artifactInventory={[
          {
            artifact_id: "artifact_a",
            display_name: "Drive Export A.pdf",
            artifact_type: "google_drive_export",
            mime_type: "application/pdf",
            status: "ready",
            consumption: {
              default_mode: "binary_payload",
              supported_modes: ["binary_payload"],
            },
          },
          {
            artifact_id: "artifact_b",
            display_name: "Drive Export B.pdf",
            artifact_type: "google_drive_export",
            mime_type: "application/pdf",
            status: "ready",
            consumption: {
              default_mode: "binary_payload",
              supported_modes: ["binary_payload"],
            },
          },
          {
            artifact_id: "artifact_c",
            display_name: "Drive Export C.pdf",
            artifact_type: "google_drive_export",
            mime_type: "application/pdf",
            status: "ready",
            consumption: {
              default_mode: "binary_payload",
              supported_modes: ["binary_payload"],
            },
          },
        ]}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
        styles={styles}
      />,
    );

    const first = screen.getByRole("checkbox", { name: /drive export a\.pdf/i });
    const second = screen.getByRole("checkbox", { name: /drive export b\.pdf/i });
    const third = screen.getByRole("checkbox", { name: /drive export c\.pdf/i });

    expect(screen.getByText(/selected artifacts \(0 of 2\)/i)).toBeInTheDocument();
    fireEvent.click(first);
    fireEvent.click(second);

    expect(first).toBeChecked();
    expect(second).toBeChecked();
    expect(third).toBeDisabled();
    expect(screen.getByText(/selected artifacts \(2 of 2\)/i)).toBeInTheDocument();

    fireEvent.click(first);

    expect(first).not.toBeChecked();
    expect(third).not.toBeDisabled();
    expect(screen.getByText(/selected artifacts \(1 of 2\)/i)).toBeInTheDocument();
  });

  it("shows a suggested artifact in the picker even when inventory is empty", async () => {
    render(
      <ExecutionComposer
        toolInventory={[
          {
            tool_id: "adapter.notebooklm.add_source_file",
            name: "NotebookLM Add Source File",
            artifact_picker: {
              enabled: true,
              field_name: "filePath",
              selection_mode: "single",
              accepted_artifact_types: ["chat_export"],
              required_consumption_mode: "file_backed",
            },
            input_schema: {
              type: "object",
              properties: {
                filePath: { type: "string" },
              },
              required: ["filePath"],
            },
          },
        ]}
        skillInventory={[]}
        artifactInventory={[]}
        initialArtifactSuggestion={{
          artifact_id: "artifact_chat_export",
          display_name: "Chat Export.md",
          artifact_type: "chat_export",
          mime_type: "text/markdown",
          consumption: {
            default_mode: "file_backed",
            supported_modes: ["file_backed", "inline_text", "metadata_only"],
          },
        }}
        initialTargetId="adapter.notebooklm.add_source_file"
        onSubmit={vi.fn()}
        onClose={vi.fn()}
        styles={styles}
      />,
    );

    expect(screen.getByRole("radio", { name: /chat export\.md/i })).toBeChecked();
    expect(screen.getByRole("button", { name: /remove chat export\.md/i })).toBeInTheDocument();
  });

  it("inherits artifact picker metadata from a skill required tool", async () => {
    const onSubmit = vi.fn();
    render(
      <ExecutionComposer
        toolInventory={[
          {
            tool_id: "mcp.gmail.create_draft_with_attachments",
            name: "Gmail Create Draft With Attachments",
            artifact_picker: {
              enabled: true,
              field_name: "artifactIds",
              selection_mode: "multiple",
              allowed_artifact_types: ["google_drive_export"],
              allowed_mime_types: ["application/pdf"],
              eligible_for: "attachments",
              accepted_artifact_types: ["google_drive_export"],
              required_consumption_mode: "binary_payload",
              max_artifact_count: 5,
            },
          },
        ]}
        skillInventory={[
          {
            skill_id: "gmail_drive_attachment_sender",
            name: "gmail-drive-attachment-sender",
            inventory_source: "builder_bound",
            description: "Send a Gmail message with an artifact attachment.",
            required_tools: ["mcp.gmail.create_draft_with_attachments"],
            input_schema: {
              type: "object",
              properties: {
                to: { type: "string" },
                subject: { type: "string" },
                body: { type: "string" },
                artifactIds: { type: "array", items: { type: "string" } },
              },
              required: ["to", "subject", "body", "artifactIds"],
            },
          },
        ]}
        artifactInventory={[
          {
            artifact_id: "artifact_pdf",
            display_name: "Execution Summary.pdf",
            artifact_type: "google_drive_export",
            mime_type: "application/pdf",
            status: "ready",
            consumption: {
              default_mode: "binary_payload",
              supported_modes: ["binary_payload", "file_backed", "metadata_only"],
            },
          },
        ]}
        onSubmit={onSubmit}
        onClose={vi.fn()}
        styles={styles}
      />,
    );

    fireEvent.change(screen.getByLabelText("Mode"), { target: { value: "skill" } });

    expect(screen.getByRole("checkbox", { name: /execution summary\.pdf/i })).toBeInTheDocument();
    expect(screen.queryByLabelText("artifactIds")).toBeNull();
    fireEvent.click(screen.getByRole("checkbox", { name: /execution summary\.pdf/i }));
    fireEvent.change(screen.getByLabelText("to"), { target: { value: "alice@example.com" } });
    fireEvent.change(screen.getByLabelText("subject"), { target: { value: "Review" } });
    fireEvent.change(screen.getByLabelText("body"), { target: { value: "Please review." } });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run" }));
    });

    expect(onSubmit).toHaveBeenCalledWith({
      commandKind: "skill",
      targetId: "gmail_drive_attachment_sender",
      executionMode: "sync",
      args: expect.objectContaining({
        artifactIds: ["artifact_pdf"],
      }),
    });
  });

  it("shows incompatible artifacts with reasons when no artifact can be selected", async () => {
    render(
      <ExecutionComposer
        toolInventory={[
          {
            tool_id: "mcp.gmail.create_draft_with_attachments",
            name: "Gmail Create Draft With Attachments",
            artifact_picker: {
              enabled: true,
              field_name: "artifactIds",
              selection_mode: "multiple",
              accepted_artifact_types: ["google_drive_export"],
              required_consumption_mode: "binary_payload",
            },
          },
        ]}
        skillInventory={[
          {
            skill_id: "gmail_drive_attachment_sender",
            name: "gmail-drive-attachment-sender",
            inventory_source: "builder_bound",
            required_tools: ["mcp.gmail.create_draft_with_attachments"],
            input_schema: {
              type: "object",
              properties: {
                to: { type: "string" },
                subject: { type: "string" },
                body: { type: "string" },
                artifactIds: { type: "array", items: { type: "string" } },
              },
              required: ["to", "subject", "body", "artifactIds"],
            },
          },
        ]}
        artifactInventory={[
          {
            artifact_id: "artifact_chat_export",
            display_name: "Chat Export.md",
            artifact_type: "chat_export",
            mime_type: "text/markdown",
            status: "ready",
            consumption: {
              default_mode: "file_backed",
              supported_modes: ["file_backed", "inline_text", "metadata_only"],
            },
          },
        ]}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
        styles={styles}
      />,
    );

    fireEvent.change(screen.getByLabelText("Mode"), { target: { value: "skill" } });

    expect(screen.getByText("Available artifacts")).toBeInTheDocument();
    expect(screen.getByText(/no compatible artifacts are loaded for this field/i)).toBeInTheDocument();
    expect(screen.getByText(/unavailable artifacts/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /chat export\.md/i })).toBeDisabled();
    expect(screen.getByText(/not selectable: accepted artifact types: google_drive_export/i)).toBeInTheDocument();
  });

  it("preselects a suggested artifact from the library into a compatible tool", async () => {
    const onSubmit = vi.fn();
    render(
      <ExecutionComposer
        toolInventory={[
          {
            tool_id: "mcp.gmail.create_draft_with_attachments",
            name: "Gmail Create Draft With Attachments",
            description: "Create a Gmail draft with attachments.",
            artifact_picker: {
              enabled: true,
              field_name: "artifactIds",
              selection_mode: "multiple",
              accepted_artifact_types: ["google_drive_export"],
              allowed_mime_types: ["application/pdf"],
              required_consumption_mode: "binary_payload",
            },
            input_schema: {
              type: "object",
              properties: {
                to: { type: "string" },
                subject: { type: "string" },
                body: { type: "string" },
                artifactIds: { type: "array", items: { type: "string" } },
              },
              required: ["to", "subject", "body", "artifactIds"],
            },
          },
        ]}
        skillInventory={[]}
        artifactInventory={[
          {
            artifact_id: "artifact_pdf",
            display_name: "Execution Summary.pdf",
            artifact_type: "google_drive_export",
            mime_type: "application/pdf",
            status: "ready",
            consumption: {
              default_mode: "binary_payload",
              supported_modes: ["binary_payload", "file_backed", "metadata_only"],
            },
          },
        ]}
        initialArtifactSuggestion={{
          artifact_id: "artifact_pdf",
          display_name: "Execution Summary.pdf",
          artifact_type: "google_drive_export",
          mime_type: "application/pdf",
        }}
        onSubmit={onSubmit}
        onClose={vi.fn()}
        styles={styles}
      />,
    );

    expect(screen.getByText(/suggested artifact \| execution summary\.pdf/i)).toBeInTheDocument();
    expect(screen.getByText(/the suggested artifact is compatible with this tool and will be preselected/i)).toBeInTheDocument();
    expect(screen.getByText(/execution summary\.pdf \(binary payload\)/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("to"), { target: { value: "alice@example.com" } });
    fireEvent.change(screen.getByLabelText("subject"), { target: { value: "Review" } });
    fireEvent.change(screen.getByLabelText("body"), { target: { value: "See attached." } });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run" }));
    });

    expect(onSubmit).toHaveBeenCalledWith({
      commandKind: "tool",
      targetId: "mcp.gmail.create_draft_with_attachments",
      executionMode: "sync",
      args: expect.objectContaining({
        artifactIds: ["artifact_pdf"],
      }),
    });
  });

  it("opens in agent mode with suggested agent output artifact preselected", async () => {
    const onSubmit = vi.fn();
    render(
      <ExecutionComposer
        toolInventory={[]}
        skillInventory={[]}
        artifactInventory={[
          {
            artifact_id: "artifact_agent",
            display_name: "Agent Output - Study Notes.md",
            artifact_type: "agent_output",
            mime_type: "text/markdown",
            consumption: {
              default_mode: "inline_text",
              supported_modes: ["inline_text", "file_backed"],
            },
          },
        ]}
        initialCommandKind="agent"
        initialAgentBackend="openclaw_cli"
        initialArtifactSuggestion={{
          artifact_id: "artifact_agent",
          display_name: "Agent Output - Study Notes.md",
          artifact_type: "agent_output",
          mime_type: "text/markdown",
        }}
        onSubmit={onSubmit}
        onClose={vi.fn()}
        styles={styles}
      />,
    );

    expect(screen.getByLabelText("Mode")).toHaveValue("agent");
    expect(screen.getByLabelText("Agent Backend")).toHaveValue("openclaw_cli");
    expect(screen.getByText(/selected artifacts \(1\)/i)).toBeInTheDocument();
    expect(screen.getByText(/agent output - study notes\.md \(inline text\)/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Agent Request"), {
      target: { value: "Reuse the selected agent output." },
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run" }));
    });

    expect(onSubmit).toHaveBeenCalledWith({
      commandKind: "agent",
      targetId: "openclaw_cli",
      executionMode: "sync",
      args: expect.objectContaining({
        request: "Reuse the selected agent output.",
        artifactRefs: [
          {
            artifact_id: "artifact_agent",
            role: "source",
            reuse_mode: "inline_text",
          },
        ],
      }),
    });
  });

  it("honors a preferred initial target id from artifact reuse recommendations", async () => {
    render(
      <ExecutionComposer
        toolInventory={[
          {
            tool_id: "adapter.notebooklm.ask",
            name: "NotebookLM Ask",
            description: "Ask a notebook question.",
            input_schema: {
              type: "object",
              properties: {
                question: { type: "string" },
              },
              required: ["question"],
            },
          },
          {
            tool_id: "mcp.gmail.create_draft_with_attachments",
            name: "Gmail Create Draft With Attachments",
            description: "Create a Gmail draft with attachments.",
            artifact_picker: {
              enabled: true,
              field_name: "artifactIds",
              selection_mode: "multiple",
              accepted_artifact_types: ["google_drive_export"],
              allowed_mime_types: ["application/pdf"],
              required_consumption_mode: "binary_payload",
            },
            input_schema: {
              type: "object",
              properties: {
                to: { type: "string" },
                subject: { type: "string" },
                body: { type: "string" },
                artifactIds: { type: "array", items: { type: "string" } },
              },
              required: ["to", "subject", "body", "artifactIds"],
            },
          },
        ]}
        skillInventory={[]}
        artifactInventory={[
          {
            artifact_id: "artifact_pdf",
            display_name: "Execution Summary.pdf",
            artifact_type: "google_drive_export",
            mime_type: "application/pdf",
            status: "ready",
            consumption: {
              default_mode: "binary_payload",
              supported_modes: ["binary_payload", "file_backed", "metadata_only"],
            },
          },
        ]}
        initialArtifactSuggestion={{
          artifact_id: "artifact_pdf",
          display_name: "Execution Summary.pdf",
          artifact_type: "google_drive_export",
          mime_type: "application/pdf",
        }}
        initialTargetId="mcp.gmail.create_draft_with_attachments"
        onSubmit={vi.fn()}
        onClose={vi.fn()}
        styles={styles}
      />,
    );

    expect(screen.getByLabelText("Target")).toHaveValue("mcp.gmail.create_draft_with_attachments");
    expect(screen.getByText(/the suggested artifact is compatible with this tool and will be preselected/i)).toBeInTheDocument();
  });

  it("explains when a suggested artifact is incompatible with the selected tool", async () => {
    render(
      <ExecutionComposer
        toolInventory={[
          {
            tool_id: "mcp.gmail.create_draft_with_attachments",
            name: "Gmail Create Draft With Attachments",
            description: "Create a Gmail draft with attachments.",
            artifact_picker: {
              enabled: true,
              field_name: "artifactIds",
              selection_mode: "multiple",
              accepted_artifact_types: ["google_drive_export"],
              allowed_mime_types: ["application/pdf"],
              required_consumption_mode: "binary_payload",
            },
            input_schema: {
              type: "object",
              properties: {
                to: { type: "string" },
                subject: { type: "string" },
                body: { type: "string" },
                artifactIds: { type: "array", items: { type: "string" } },
              },
              required: ["to", "subject", "body", "artifactIds"],
            },
          },
        ]}
        skillInventory={[]}
        artifactInventory={[
          {
            artifact_id: "artifact_chat",
            display_name: "Chat Export - Bible Study.md",
            artifact_type: "chat_export",
            mime_type: "text/markdown",
            status: "ready",
            consumption: {
              default_mode: "file_backed",
              supported_modes: ["file_backed", "metadata_only"],
            },
          },
        ]}
        initialArtifactSuggestion={{
          artifact_id: "artifact_chat",
          display_name: "Chat Export - Bible Study.md",
          artifact_type: "chat_export",
          mime_type: "text/markdown",
        }}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
        styles={styles}
      />,
    );

    expect(screen.getByText(/suggested artifact \| chat export - bible study\.md/i)).toBeInTheDocument();
    expect(
      screen.getByText(/the suggested artifact is not compatible with this tool/i),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/accepted artifact types: google_drive_export/i).length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText(/accepted mime types: application\/pdf/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/required consumption mode: binary payload/i).length).toBeGreaterThanOrEqual(1);
  });

  it("filters artifact picker options by required consumption mode", async () => {
    render(
      <ExecutionComposer
        toolInventory={[
          {
            tool_id: "mcp.gmail.create_draft_with_attachments",
            name: "Gmail Create Draft With Attachments",
            description: "Create a Gmail draft with attachments.",
            artifact_picker: {
              enabled: true,
              field_name: "artifactIds",
              selection_mode: "multiple",
              accepted_artifact_types: ["google_drive_export"],
              allowed_mime_types: ["application/pdf"],
              required_consumption_mode: "binary_payload",
            },
            input_schema: {
              type: "object",
              properties: {
                to: { type: "string" },
                subject: { type: "string" },
                body: { type: "string" },
                artifactIds: { type: "array", items: { type: "string" } },
              },
              required: ["to", "subject", "body", "artifactIds"],
            },
          },
        ]}
        skillInventory={[]}
        artifactInventory={[
          {
            artifact_id: "artifact_good",
            display_name: "Execution Summary.pdf",
            artifact_type: "google_drive_export",
            mime_type: "application/pdf",
            status: "ready",
            consumption: {
              default_mode: "binary_payload",
              supported_modes: ["binary_payload", "file_backed"],
            },
          },
          {
            artifact_id: "artifact_bad",
            display_name: "Drive Export Metadata.pdf",
            artifact_type: "google_drive_export",
            mime_type: "application/pdf",
            status: "ready",
            consumption: {
              default_mode: "metadata_only",
              supported_modes: ["metadata_only"],
            },
          },
        ]}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
        styles={styles}
      />,
    );

    expect(screen.getByRole("checkbox", { name: /execution summary\.pdf/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /drive export metadata\.pdf/i })).toBeDisabled();
    expect(screen.getByText(/1 eligible artifact available for this field/i)).toBeInTheDocument();
    expect(screen.getByText(/unavailable artifacts/i)).toBeInTheDocument();
    expect(screen.getByText(/not selectable: required consumption mode: binary payload/i)).toBeInTheDocument();
  });

  it("renders an artifact picker for non-artifactIds file-backed fields", async () => {
    const onSubmit = vi.fn();
    render(
      <ExecutionComposer
        toolInventory={[
          {
            tool_id: "adapter.notebooklm.add_source_file",
            name: "NotebookLM Add Source File",
            description: "Add a saved file artifact to a notebook.",
            artifact_picker: {
              enabled: true,
              field_name: "filePath",
              selection_mode: "single",
              accepted_artifact_types: ["chat_export"],
              required_consumption_mode: "file_backed",
            },
            input_schema: {
              type: "object",
              properties: {
                notebookTitle: { type: "string" },
                filePath: { type: "string" },
              },
              required: ["notebookTitle", "filePath"],
            },
          },
        ]}
        skillInventory={[]}
        artifactInventory={[
          {
            artifact_id: "artifact_chat_export",
            display_name: "Chat Export.md",
            artifact_type: "chat_export",
            mime_type: "text/markdown",
            status: "ready",
            consumption: {
              default_mode: "file_backed",
              supported_modes: ["file_backed", "inline_text", "metadata_only"],
            },
          },
        ]}
        onSubmit={onSubmit}
        onClose={vi.fn()}
        styles={styles}
      />,
    );

    expect(screen.getByText(/required consumption mode: file backed/i)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /chat export\.md/i })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("notebookTitle"), { target: { value: "GPT Application Designer" } });
    fireEvent.click(screen.getByRole("radio", { name: /chat export\.md/i }));
    expect(screen.getByRole("button", { name: /remove chat export\.md/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /remove chat export\.md/i }));
    expect(screen.getByText(/no artifact selected/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: /chat export\.md/i }));

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run" }));
    });

    expect(onSubmit).toHaveBeenCalledWith({
      commandKind: "tool",
      targetId: "adapter.notebooklm.add_source_file",
      executionMode: "sync",
      args: expect.objectContaining({
        notebookTitle: "GPT Application Designer",
        filePath: "artifact_chat_export",
      }),
    });
  });

  it("uses radio controls for single-artifact fields and replaces the prior selection", async () => {
    const onSubmit = vi.fn();
    render(
      <ExecutionComposer
        toolInventory={[
          {
            tool_id: "adapter.notebooklm.add_source_file",
            name: "NotebookLM Add Source File",
            artifact_picker: {
              enabled: true,
              field_name: "filePath",
              selection_mode: "single",
              accepted_artifact_types: ["chat_export"],
              required_consumption_mode: "file_backed",
            },
            input_schema: {
              type: "object",
              properties: {
                filePath: { type: "string" },
              },
              required: ["filePath"],
            },
          },
        ]}
        skillInventory={[]}
        artifactInventory={[
          {
            artifact_id: "artifact_first",
            display_name: "First Chat Export.md",
            artifact_type: "chat_export",
            mime_type: "text/markdown",
            status: "ready",
            consumption: {
              default_mode: "file_backed",
              supported_modes: ["file_backed"],
            },
          },
          {
            artifact_id: "artifact_second",
            display_name: "Second Chat Export.md",
            artifact_type: "chat_export",
            mime_type: "text/markdown",
            status: "ready",
            consumption: {
              default_mode: "file_backed",
              supported_modes: ["file_backed"],
            },
          },
        ]}
        onSubmit={onSubmit}
        onClose={vi.fn()}
        styles={styles}
      />,
    );

    const first = screen.getByRole("radio", { name: /first chat export\.md/i });
    const second = screen.getByRole("radio", { name: /second chat export\.md/i });

    fireEvent.click(first);
    expect(first).toBeChecked();
    expect(second).not.toBeChecked();

    fireEvent.click(second);
    expect(first).not.toBeChecked();
    expect(second).toBeChecked();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run" }));
    });

    expect(onSubmit).toHaveBeenCalledWith({
      commandKind: "tool",
      targetId: "adapter.notebooklm.add_source_file",
      executionMode: "sync",
      args: expect.objectContaining({
        filePath: "artifact_second",
      }),
    });
  });
});
