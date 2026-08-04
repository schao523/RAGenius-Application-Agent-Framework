import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import RuntimeInspector from "./RuntimeInspector";

const styles = {
  inspectorSection: {},
  inspectorGroup: {},
  inspectorGroupTitle: {},
  inspectorKeyValue: {},
  sourceList: {},
  debugCode: {},
  inspectorPane: {},
  card: {},
  inspectorHeader: {},
  small: {},
  secondaryButton: {},
  inspectorTabRow: {},
  inspectorTab: () => ({}),
};

const commonProps = {
  open: true,
  tab: "state",
  onChangeTab: () => {},
  onClose: () => {},
  styles,
  humanizeActionType: (value) => String(value || ""),
  humanizePresentationMode: (value) => String(value || ""),
  summarizePrimaryScope: () => "",
};

describe("RuntimeInspector", () => {
  it("shows the selected message workflow state instead of the latest session state", () => {
    render(
      <RuntimeInspector
        {...commonProps}
        message={{
          role: "assistant",
          workflowStatus: {
            workflow_title: "Bible Study",
            current_step: { order: 1, title: "Observation" },
          },
          sessionExecutionState: { execution_status: "guiding" },
          retrievalSummary: {},
        }}
        workflowStatus={{
          workflow_title: "Bible Study",
          current_step: { order: 2, title: "Identify Relationships" },
        }}
      />,
    );

    expect(screen.getByText("Observation")).toBeInTheDocument();
    expect(screen.queryByText(/Identify Relationships/)).toBeNull();
  });

  it("derives a historical turn state from its persisted workflow progress", () => {
    render(
      <RuntimeInspector
        {...commonProps}
        message={{
          role: "assistant",
          workflowProgress: {
            workflow_id: "bible_study",
            workflow_title: "Bible Study",
            step_order: 1,
            step_title: "Observation",
          },
          retrievalSummary: {},
        }}
        workflowStatus={null}
      />,
    );

    expect(screen.getByText("Bible Study")).toBeInTheDocument();
    expect(screen.getByText("Observation")).toBeInTheDocument();
  });

  it("shows compact-mode token savings for the selected turn in Details", () => {
    render(
      <RuntimeInspector
        {...commonProps}
        tab="details"
        message={{
          role: "assistant",
          retrievalSummary: {
            task_model_diagnostics: {
              context_optimization: { eligible: true, mode: "compact" },
              turn_token_accounting: {
                call_count: 3,
                turn_estimated_outbound_tokens: 4280,
                turn_actual_full_tokens: 11220,
                turn_compact_candidate_tokens: 4280,
                turn_estimated_tokens_saved: 6940,
                turn_estimated_saving_percent: 61.9,
                budget_limit_tokens: 25000,
                budget_exceeded: false,
                calls: [
                  {
                    task: "planner",
                    actual_full_tokens: 4000,
                    actual_outbound_tokens: 1600,
                    estimated_tokens_saved: 2400,
                    estimated_saving_percent: 60,
                    estimator_name: "chars_per_token",
                    estimator_version: "v1",
                  },
                ],
              },
            },
          },
        }}
        workflowStatus={null}
      />,
    );

    expect(screen.getByText("Token Optimization")).toBeInTheDocument();
    expect(screen.getByText(/Mode:/).parentElement).toHaveTextContent("Compact");
    expect(screen.getByText(/Estimated outbound:/).parentElement).toHaveTextContent("4,280 tokens");
    expect(screen.getByText(/Estimated saved:/).parentElement).toHaveTextContent("6,940 tokens (61.9%)");
    expect(screen.getByText("Call breakdown")).toBeInTheDocument();
    expect(screen.getByText("Planning")).toBeInTheDocument();
  });

  it("labels diagnostic-mode reductions as potential rather than realized savings", () => {
    render(
      <RuntimeInspector
        {...commonProps}
        tab="details"
        message={{
          role: "assistant",
          retrievalSummary: {
            task_model_diagnostics: {
              context_optimization: { eligible: true, mode: "diagnostic" },
              turn_token_accounting: {
                call_count: 1,
                turn_estimated_outbound_tokens: 11220,
                turn_actual_full_tokens: 11220,
                turn_compact_candidate_tokens: 4280,
                turn_estimated_tokens_saved: 6940,
                turn_estimated_saving_percent: 61.9,
                budget_limit_tokens: 25000,
                budget_exceeded: false,
                calls: [],
              },
            },
          },
        }}
        workflowStatus={null}
      />,
    );

    expect(screen.getByText(/Actually sent:/).parentElement).toHaveTextContent("11,220 tokens");
    expect(screen.getByText(/Compact candidate:/).parentElement).toHaveTextContent("4,280 tokens");
    expect(screen.getByText(/Potential saving:/).parentElement).toHaveTextContent("6,940 tokens (61.9%)");
    expect(screen.queryByText(/Estimated saved:/)).toBeNull();
  });

  it("explains when a historical turn has no recorded token diagnostics", () => {
    render(
      <RuntimeInspector
        {...commonProps}
        tab="details"
        message={{ role: "assistant", retrievalSummary: {} }}
        workflowStatus={null}
      />,
    );

    expect(screen.getByText("Token Optimization")).toBeInTheDocument();
    expect(screen.getByText(/not recorded for this turn/i)).toBeInTheDocument();
  });

  it("includes token diagnostics in Raw", () => {
    render(
      <RuntimeInspector
        {...commonProps}
        tab="raw"
        message={{
          role: "assistant",
          retrievalSummary: {
            task_model_diagnostics: {
              context_optimization: { mode: "compact" },
              turn_token_accounting: { call_count: 2 },
            },
          },
        }}
        workflowStatus={null}
      />,
    );

    expect(screen.getByText(/"task_model_diagnostics"/)).toBeInTheDocument();
    expect(screen.getByText(/"call_count": 2/)).toBeInTheDocument();
  });
});
