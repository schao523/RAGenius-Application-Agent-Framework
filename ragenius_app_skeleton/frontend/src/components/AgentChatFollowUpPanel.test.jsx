import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import AgentChatFollowUpPanel from "./AgentChatFollowUpPanel";

const styles = {
  compactNote: {}, errorText: {}, input: {}, primaryButton: {}, row: {}, secondaryButton: {}, sidebarSectionTitle: {}
};

describe("AgentChatFollowUpPanel", () => {
  it("submits reply text as a new same-session Agent run", () => {
    const onFollowUp = vi.fn();
    render(<AgentChatFollowUpPanel
      chatSession={{ state: "ready_for_follow_up", session_version: 3 }}
      onFollowUp={onFollowUp}
      onEnd={vi.fn()}
      styles={styles}
    />);
    fireEvent.change(screen.getByLabelText("OpenClaw follow-up"), { target: { value: "Use title two." } });
    fireEvent.click(screen.getByRole("button", { name: "Reply" }));
    expect(onFollowUp).toHaveBeenCalledWith({ kind: "reply", text: "Use title two." });
    expect(screen.getByText(/new Agent run in the same OpenClaw session/i)).toBeInTheDocument();
  });

  it("offers active cancellation while a follow-up run is running", () => {
    const onCancel = vi.fn();
    render(<AgentChatFollowUpPanel
      chatSession={{ state: "running", session_version: 4 }}
      onCancel={onCancel}
      styles={styles}
    />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel current run" }));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("labels an empty continuation explicitly", () => {
    const onFollowUp = vi.fn();
    render(<AgentChatFollowUpPanel
      chatSession={{ state: "ready_for_follow_up", session_version: 4 }}
      onFollowUp={onFollowUp}
      onEnd={vi.fn()}
      styles={styles}
    />);

    fireEvent.click(screen.getByRole("button", { name: "Continue without reply" }));
    expect(onFollowUp).toHaveBeenCalledWith({ kind: "continue" });
  });

  it("closes a waiting chat interaction without starting another Agent turn", () => {
    const onEnd = vi.fn();
    const onFollowUp = vi.fn();
    render(<AgentChatFollowUpPanel
      chatSession={{ state: "ready_for_follow_up", session_version: 5 }}
      onEnd={onEnd}
      onFollowUp={onFollowUp}
      styles={styles}
    />);

    fireEvent.click(screen.getByRole("button", { name: "Cancel interaction" }));

    expect(onEnd).toHaveBeenCalledOnce();
    expect(onFollowUp).not.toHaveBeenCalled();
  });

  it("shows the latest OpenClaw prompt and offers numbered choices", () => {
    render(<AgentChatFollowUpPanel
      chatSession={{ state: "ready_for_follow_up", session_version: 6 }}
      prompt={[
        "Choose one title:",
        "1. **Dependable by Design**",
        "2. **Trust in Every Turn**",
        "3. **Reliable by Default**",
        "Please reply 1, 2, or 3.",
      ].join("\n")}
      onEnd={vi.fn()}
      onFollowUp={vi.fn()}
      styles={styles}
    />);

    expect(screen.getByText(/choose one title/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /2\. trust in every turn/i }));
    expect(screen.getByLabelText("OpenClaw follow-up")).toHaveValue("2");
  });

  it("keeps controls visible outside a bounded long-response scroller", () => {
    const longResponse = Array.from(
      { length: 30 },
      (_, index) => `Section ${index + 1}: detailed OpenClaw response content.`,
    ).join("\n");

    render(<AgentChatFollowUpPanel
      chatSession={{ state: "ready_for_follow_up", session_version: 7 }}
      prompt={longResponse}
      onEnd={vi.fn()}
      onFollowUp={vi.fn()}
      styles={styles}
    />);

    const responseScroller = screen.getByLabelText("OpenClaw question");
    const replyField = screen.getByLabelText("OpenClaw follow-up");
    const stopButton = screen.getByRole("button", { name: "Stop and summarize" });

    expect(responseScroller).toHaveStyle({ overflowY: "auto" });
    expect(responseScroller).toHaveStyle({ maxHeight: "min(24vh, 220px)" });
    expect(responseScroller).not.toContainElement(replyField);
    expect(responseScroller).not.toContainElement(stopButton);
    expect(replyField).toHaveAttribute("rows", "2");
  });

  it.each(["completed", "failed", "cancelled"])(
    "does not show a follow-up panel for a %s chat session",
    (state) => {
      render(<AgentChatFollowUpPanel
        chatSession={{ state, session_version: 7 }}
        onEnd={vi.fn()}
        onFollowUp={vi.fn()}
        styles={styles}
      />);

      expect(screen.queryByRole("region", { name: /openclaw chat continuation/i })).toBeNull();
    },
  );

  it("finishes a summarized chat instead of offering another follow-up", async () => {
    const onEnd = vi.fn();
    render(<AgentChatFollowUpPanel
      chatSession={{
        state: "ready_for_follow_up",
        session_version: 8,
        turns: [{ kind: "graceful_cancel", result: { output_text: "Final summary." } }],
      }}
      onEnd={onEnd}
      onFollowUp={vi.fn()}
      styles={styles}
    />);

    expect(screen.getByText("Final summary.")).toBeInTheDocument();
    expect(screen.queryByLabelText("OpenClaw follow-up")).toBeNull();
    expect(screen.getByRole("button", { name: "Finish and close" })).toBeInTheDocument();
    await waitFor(() => expect(onEnd).toHaveBeenCalledWith({ persistFinalOutput: true }));
  });
});
