import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import AgentInteractionCard from "./AgentInteractionCard";

const styles = {
  secondaryButton: {},
  button: {},
  compactNote: {},
  error: {},
  input: {},
  row: {},
  pill: {},
  statusWarn: {},
};

function interaction(overrides = {}) {
  return {
    interaction_id: "interaction_1",
    type: "approval",
    state: "pending",
    version: 2,
    prompt: "Allow this external action?",
    options: [],
    allows_free_text: false,
    expires_at: "2099-08-13T12:00:00Z",
    ...overrides,
  };
}

describe("AgentInteractionCard", () => {
  it("submits typed allow-once and deny decisions with duplicate-click suppression", () => {
    const onRespond = vi.fn();
    const onCancel = vi.fn();
    const { rerender } = render(
      <AgentInteractionCard interaction={interaction()} onRespond={onRespond} onCancel={onCancel} styles={styles} />,
    );

    expect(screen.getByText(/approval applies once/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /allow once/i }));
    expect(onRespond).toHaveBeenCalledWith({ kind: "approval", decision: "allow_once" });
    fireEvent.click(screen.getByRole("button", { name: /cancel execution/i }));
    expect(onCancel).toHaveBeenCalledTimes(1);

    rerender(
      <AgentInteractionCard interaction={interaction()} onRespond={onRespond} submitting styles={styles} />,
    );
    expect(screen.getByRole("button", { name: /allow once/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^deny$/i })).toBeDisabled();
  });

  it("supports bounded clarification text without rendering secret input", () => {
    const onRespond = vi.fn();
    render(
      <AgentInteractionCard
        interaction={interaction({ type: "clarification", allows_free_text: true, prompt: "Which title?" })}
        onRespond={onRespond}
        styles={styles}
      />,
    );

    expect(screen.queryByLabelText(/password|secret|token/i)).toBeNull();
    fireEvent.change(screen.getByLabelText(/your response/i), { target: { value: "A concise title" } });
    fireEvent.click(screen.getByRole("button", { name: /submit response/i }));
    expect(onRespond).toHaveBeenCalledWith({ kind: "clarification", text: "A concise title" });
  });

  it("renders selection and authentication handoff as typed actions", () => {
    const onRespond = vi.fn();
    const { rerender } = render(
      <AgentInteractionCard
        interaction={interaction({
          type: "selection",
          prompt: "Choose outputs",
          options: [
            { id: "report", label: "Report" },
            { id: "slides", label: "Slides" },
          ],
        })}
        onRespond={onRespond}
        styles={styles}
      />,
    );
    fireEvent.click(screen.getByRole("checkbox", { name: /report/i }));
    fireEvent.click(screen.getByRole("button", { name: /submit selection/i }));
    expect(onRespond).toHaveBeenCalledWith({ kind: "selection", option_ids: ["report"] });

    rerender(
      <AgentInteractionCard
        interaction={interaction({ type: "authentication_handoff", prompt: "Sign in in the provider window." })}
        onRespond={onRespond}
        styles={styles}
      />,
    );
    expect(screen.getByText(/sign in in the provider window/i)).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /i completed this step/i }));
    expect(onRespond).toHaveBeenLastCalledWith({ kind: "user_action", outcome: "completed" });
  });

  it("disables stale or expired interactions and offers refresh", () => {
    const onRefresh = vi.fn();
    render(
      <AgentInteractionCard
        interaction={interaction({ state: "expired", expires_at: "2020-01-01T00:00:00Z" })}
        onRefresh={onRefresh}
        styles={styles}
      />,
    );
    expect(screen.getByText(/no longer pending/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /allow once/i })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: /refresh interaction/i }));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });
});
