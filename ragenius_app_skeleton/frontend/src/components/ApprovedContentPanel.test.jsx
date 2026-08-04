import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ApprovedContentPanel from "./ApprovedContentPanel";

const styles = {
  approvedContentShell: {},
  approvedContentHeader: {},
  approvedContentCard: {},
  approvedContentList: {},
  approvedContentListItem: () => ({}),
  sidebarSectionTitle: {},
  small: {},
  secondaryButton: {},
  approvedContentMeta: {},
  compactNote: {},
  row: {},
  pill: {},
  statusOk: {},
};

describe("ApprovedContentPanel", () => {
  it("shows legacy approved content collapsed and reveals details on demand", () => {
    render(
      <ApprovedContentPanel
        approvedContent={[
          {
            approved_content_id: "ac_1",
            revision_id: "rev_1",
            content_text: "Friendly approved content for execution.",
            source_message_id: "msg_1",
            created_at: "2026-06-03T08:15:00+00:00",
          },
        ]}
        selectedApprovedContentId="ac_1"
        onSelectApprovedContent={() => {}}
        latestAssistantMessage={{ role: "assistant", content: "Friendly approved content for execution." }}
        onApproveLatest={() => {}}
        approving={false}
        styles={styles}
      />,
    );

    expect(screen.getByText("Legacy Approved Content")).toBeInTheDocument();
    expect(screen.queryByText(/selected revision: rev_1/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/friendly approved content for execution/i)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /show legacy approved content/i }));

    fireEvent.click(screen.getByRole("button", { name: /details/i }));

    expect(screen.getByText(/selected revision: rev_1/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /approve latest reply/i })).toBeEnabled();
    expect(screen.getByText(/friendly approved content for execution/i)).toBeInTheDocument();
    expect(screen.getByText(/approved 2026-06-03 08:15 utc/i)).toBeInTheDocument();
    expect(screen.getByText(/source message: msg_1/i)).toBeInTheDocument();
  });

  it("disables approval when there is no assistant reply to approve", () => {
    render(
      <ApprovedContentPanel
        approvedContent={[]}
        selectedApprovedContentId=""
        onSelectApprovedContent={() => {}}
        latestAssistantMessage={null}
        onApproveLatest={() => {}}
        approving={false}
        styles={styles}
      />,
    );

    expect(screen.getByRole("button", { name: /approve latest reply/i })).toBeDisabled();
  });

  it("calls approval handler when the user approves the latest reply", () => {
    const onApproveLatest = vi.fn();
    render(
      <ApprovedContentPanel
        approvedContent={[]}
        selectedApprovedContentId=""
        onSelectApprovedContent={() => {}}
        latestAssistantMessage={{ role: "assistant", content: "Reply" }}
        onApproveLatest={onApproveLatest}
        approving={false}
        styles={styles}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /approve latest reply/i }));

    expect(onApproveLatest).toHaveBeenCalledTimes(1);
  });

  it("allows selecting a prior approved revision for @exec from history", () => {
    const onSelectApprovedContent = vi.fn();
    render(
      <ApprovedContentPanel
        approvedContent={[
          {
            approved_content_id: "ac_1",
            revision_id: "rev_1",
            content_text: "First approved revision.",
            source_message_id: "msg_1",
            created_at: "2026-06-02T08:15:00+00:00",
          },
          {
            approved_content_id: "ac_2",
            revision_id: "rev_2",
            content_text: "Second approved revision.",
            source_message_id: "msg_2",
            created_at: "2026-06-03T08:15:00+00:00",
          },
        ]}
        selectedApprovedContentId="ac_2"
        onSelectApprovedContent={onSelectApprovedContent}
        latestAssistantMessage={{ role: "assistant", content: "Reply" }}
        onApproveLatest={() => {}}
        approving={false}
        styles={styles}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /show legacy approved content/i }));
    fireEvent.click(screen.getByRole("button", { name: /history/i }));
    fireEvent.click(screen.getByRole("button", { name: /use for @exec/i }));

    expect(onSelectApprovedContent).toHaveBeenCalledWith("ac_1");
    expect(screen.getByText(/legacy selected for @exec/i)).toBeInTheDocument();
    expect(screen.getAllByText(/^Latest$/)).not.toHaveLength(0);
    expect(screen.getByText(/approved 2026-06-02 08:15 utc/i)).toBeInTheDocument();
    expect(screen.getByText(/source message: msg_1/i)).toBeInTheDocument();
  });
});
