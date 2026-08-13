import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import AgentInteractionCard from "./AgentInteractionCard";

const styles = { button: {}, compactNote: {}, error: {}, input: {}, pill: {}, row: {}, secondaryButton: {}, statusWarn: {} };

describe("interactive Agent UI flow", () => {
  it("moves from approval to clarification without carrying the prior response", () => {
    const onRespond = vi.fn();
    const { rerender } = render(
      <AgentInteractionCard
        interaction={{
          interaction_id: "approval_1", type: "approval", state: "pending", version: 1,
          prompt: "Allow once?", options: [], expires_at: "2099-01-01T00:00:00Z",
        }}
        onRespond={onRespond}
        styles={styles}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /allow once/i }));
    expect(onRespond).toHaveBeenLastCalledWith({ kind: "approval", decision: "allow_once" });

    rerender(
      <AgentInteractionCard
        interaction={{
          interaction_id: "clarification_1", type: "clarification", state: "pending", version: 1,
          prompt: "Which title?", options: [], allows_free_text: true, expires_at: "2099-01-01T00:00:00Z",
        }}
        onRespond={onRespond}
        styles={styles}
      />,
    );
    expect(screen.getByLabelText(/your response/i)).toHaveValue("");
    fireEvent.change(screen.getByLabelText(/your response/i), { target: { value: "Study Notes" } });
    fireEvent.click(screen.getByRole("button", { name: /submit response/i }));
    expect(onRespond).toHaveBeenLastCalledWith({ kind: "clarification", text: "Study Notes" });
  });

  it("keeps an OpenClaw cancellation action provider-neutral", () => {
    const onCancel = vi.fn();
    render(
      <AgentInteractionCard
        interaction={{
          interaction_id: "approval_1", type: "approval", state: "pending", version: 1,
          prompt: "Allow command?", options: [], expires_at: "2099-01-01T00:00:00Z",
        }}
        onRespond={vi.fn()}
        onCancel={onCancel}
        styles={styles}
      />,
    );
    expect(screen.queryByText(/openclaw|codex/i)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /cancel execution/i }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
