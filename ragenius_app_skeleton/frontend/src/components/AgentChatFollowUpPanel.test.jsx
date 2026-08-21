import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
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
});
