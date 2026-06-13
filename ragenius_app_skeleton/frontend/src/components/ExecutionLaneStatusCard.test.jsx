import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ExecutionLaneStatusCard from "./ExecutionLaneStatusCard";

const styles = {
  executionLaneShell: {},
  executionLaneHeader: {},
  executionLaneGrid: {},
  executionLaneMetric: {},
  executionLaneValue: {},
  executionDetailsShell: {},
  executionDetailsTitle: {},
  executionDetailsBlock: {},
  executionDetailsList: {},
  executionDetailsItem: {},
  sidebarSectionTitle: {},
  small: {},
  metricLabel: {},
  compactNote: {},
  secondaryButton: {},
  row: {},
};

describe("ExecutionLaneStatusCard", () => {
  it("shows a compact execution summary for the selected revision and latest status", () => {
    render(
      <ExecutionLaneStatusCard
        selectedApprovedContent={{
          approved_content_id: "ac_1",
          revision_id: "rev_1",
        }}
        sessionLaneState={{
          execution_lane: {
            latest_execution_request_skill_id: "notebooklm_generate_video",
            latest_execution_id: "execution_123",
            latest_execution_mode: "async",
            latest_async_task_id: "task_video_123",
            latest_async_task_status: "submitted",
            latest_execution_result: {
              status: "completed",
              execution_metadata: {
                used_fallback: true,
                fallback_count: 1,
                execution_paths: ["adapter", "rest_fallback"],
              },
            },
          },
        }}
        styles={styles}
      />,
    );

    expect(screen.getByText(/revision: rev_1/i)).toBeInTheDocument();
    expect(screen.getByText(/last exec: notebooklm_generate_video/i)).toBeInTheDocument();
    expect(screen.getByText(/status: completed/i)).toBeInTheDocument();
    expect(screen.getByText(/mode: async/i)).toBeInTheDocument();
    expect(screen.getByText(/task: submitted/i)).toBeInTheDocument();
    expect(screen.getByText(/this execution was submitted as a background provider job/i)).toBeInTheDocument();
    expect(screen.getByText(/path: adapter, rest_fallback/i)).toBeInTheDocument();
    expect(screen.getByText(/fallback: yes \(1\)/i)).toBeInTheDocument();
  });

  it("shows the empty-state hint when there is no execution activity", () => {
    render(
      <ExecutionLaneStatusCard
        selectedApprovedContent={null}
        sessionLaneState={{}}
        styles={styles}
      />,
    );

    expect(screen.getByText(/approve a revision, then use the execution composer/i)).toBeInTheDocument();
  });

  it("allows opening details and refreshing the latest execution status when an execution id exists", () => {
    const onRefreshStatus = vi.fn();
    const onOpenComposer = vi.fn();
    const onOpenInspector = vi.fn();
    render(
      <ExecutionLaneStatusCard
        selectedApprovedContent={null}
        sessionLaneState={{
          execution_lane: {
            latest_execution_id: "execution_123",
            latest_execution_result: { status: "submitted" },
          },
        }}
        onRefreshStatus={onRefreshStatus}
        onOpenComposer={onOpenComposer}
        onOpenInspector={onOpenInspector}
        refreshing={false}
        styles={styles}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /open composer/i }));
    fireEvent.click(screen.getByRole("button", { name: /^details$/i }));
    fireEvent.click(screen.getByRole("button", { name: /refresh execution status/i }));

    expect(onOpenComposer).toHaveBeenCalledTimes(1);
    expect(onOpenInspector).toHaveBeenCalledTimes(1);
    expect(onRefreshStatus).toHaveBeenCalledTimes(1);
  });

  it("shows notebooklm login and retry actions when auth is required", () => {
    const onLoginNotebookLm = vi.fn();
    const onRetryExecution = vi.fn();
    render(
      <ExecutionLaneStatusCard
        selectedApprovedContent={null}
        sessionLaneState={{
          execution_lane: {
            latest_execution_id: "execution_auth_1",
            latest_execution_request_query: '@exec skill notebooklm_generate_video notebookTitle="GPT Application Designer"',
            latest_login_requirement: {
              auth_required: true,
              provider: "notebooklm",
              login_command: "python -m notebooklm login",
            },
            latest_execution_result: {
              error: {
                code: "NOTEBOOKLM_AUTH_REQUIRED",
                message: "NotebookLM login is required.",
              },
            },
          },
        }}
        onLoginNotebookLm={onLoginNotebookLm}
        loggingInToNotebookLm={false}
        onRetryExecution={onRetryExecution}
        styles={styles}
      />,
    );

    expect(screen.getByText(/notebooklm login is required/i)).toBeInTheDocument();
    expect(screen.getByText(/python -m notebooklm login/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /login to notebooklm/i }));
    fireEvent.click(screen.getByRole("button", { name: /retry last @exec/i }));
    expect(onLoginNotebookLm).toHaveBeenCalledTimes(1);
    expect(onRetryExecution).toHaveBeenCalledTimes(1);
  });
});
