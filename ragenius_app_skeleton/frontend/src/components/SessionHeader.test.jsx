import React from "react";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import SessionHeader from "./SessionHeader";

const styles = {
  sessionHeaderGroup: { display: "grid", gap: 10, minWidth: 0 },
  sessionHeader: {},
  sessionHeaderTitle: {},
  sessionHeaderMeta: {},
  workflowStrip: {},
  workflowBadge: () => ({}),
  row: {},
  secondaryButton: {},
};

describe("SessionHeader", () => {
  it("keeps the title and current workflow step in one grid item", () => {
    render(
      <SessionHeader
        appName="Bible Tutor"
        phaseLabel="Formulate Questions"
        workflowStatus={{
          workflow_title: "Study workflow",
          current_step: { order: 1, title: "Formulate Questions" },
        }}
        styles={styles}
        loading={false}
        appId="app-1"
        onAdvanceWorkflow={vi.fn()}
        onOpenInspector={vi.fn()}
        hasAssistantTurn
      />,
    );

    const sessionContext = screen.getByRole("group", { name: /session context/i });
    expect(sessionContext).toHaveStyle({ display: "grid", gap: "10px", minWidth: 0 });
    expect(within(sessionContext).getByText("Bible Tutor")).toBeInTheDocument();
    expect(within(sessionContext).getByText(/current: formulate questions/i)).toBeInTheDocument();
  });
});
