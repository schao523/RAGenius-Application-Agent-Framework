import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import AgentInteractionCard from "./AgentInteractionCard";

const base = {
  interaction_id: "interaction_auth",
  state: "pending",
  version: 1,
  expires_at: "2099-01-01T00:00:00Z",
  options: [],
};

describe("AgentInteractionCard", () => {
  it("renders an approved authentication launch without a secret input", () => {
    const onLaunch = vi.fn();
    const onRespond = vi.fn();
    render(<AgentInteractionCard
      interaction={{
        ...base,
        type: "authentication_handoff",
        prompt: "Sign in to continue.",
        presentation: {
          target_label: "Google sign-in",
          target_host: "accounts.google.com",
          launch_available: true,
          completion_label: "Authentication completed",
        },
      }}
      onLaunch={onLaunch}
      onRespond={onRespond}
    />);

    expect(screen.getByText(/google sign-in \(accounts\.google\.com\)/i)).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /open sign-in/i }));
    fireEvent.click(screen.getByRole("button", { name: /authentication completed/i }));
    expect(onLaunch).toHaveBeenCalledOnce();
    expect(onRespond).toHaveBeenCalledWith({ kind: "user_action", outcome: "completed" });
  });

  it("renders a bounded manual action with completion and cancellation", () => {
    const onRespond = vi.fn();
    render(<AgentInteractionCard
      interaction={{
        ...base,
        type: "user_action_required",
        prompt: "Choose the file in Chrome.",
        presentation: { completion_label: "File selected" },
      }}
      onRespond={onRespond}
    />);
    fireEvent.click(screen.getByRole("button", { name: /file selected/i }));
    fireEvent.click(screen.getByRole("button", { name: /cancel step/i }));
    expect(onRespond).toHaveBeenNthCalledWith(1, { kind: "user_action", outcome: "completed" });
    expect(onRespond).toHaveBeenNthCalledWith(2, { kind: "user_action", outcome: "cancelled" });
  });
});
