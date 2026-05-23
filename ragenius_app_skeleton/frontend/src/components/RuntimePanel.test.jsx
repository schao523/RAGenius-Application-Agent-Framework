import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import RuntimePanel from "./RuntimePanel";

const styles = {
  card: {},
  sectionTitle: {},
  muted: {},
  row: {},
  button: {},
  linkButton: {},
  disabledLinkButton: {},
  metricGrid: {},
  metric: {},
  metricLabel: {},
  metricValue: {},
  label: {},
  code: {},
  pill: {},
  error: {},
};

function renderPanel(fetchJson = vi.fn()) {
  return render(
    <RuntimePanel
      baseUrl="http://api.example.test"
      builderBaseUrl="http://builder.example.test"
      builderAvailable
      appId="app-1"
      styles={styles}
      fetchJson={fetchJson}
    />,
  );
}

describe("RuntimePanel", () => {
  it("renders compact instruction-understanding status from runtime payload", async () => {
    const fetchJson = vi.fn().mockResolvedValue({
      provider: "openai",
      domain: "church-ministry",
      models: { chat: "gpt-4.1" },
      config_summary: { goal_count: 3 },
      adapter_summary: { guardrail_count: 2 },
      instruction_understanding_preview: {
        compiled_status: "ready",
        review_status: "reviewed_with_warnings",
        cache_status: "hot",
      },
    });

    renderPanel(fetchJson);

    fireEvent.click(screen.getByRole("button", { name: /load runtime summary/i }));

    await waitFor(() => {
      expect(fetchJson).toHaveBeenCalledWith(
        "http://api.example.test/apps/app-1/runtime",
        { headers: { "x-role": "admin" } },
      );
    });

    expect(screen.getByText("Compiled: ready")).toBeInTheDocument();
    expect(screen.getByText("Review: reviewed_with_warnings")).toBeInTheDocument();
    expect(screen.getByText("Cache: hot")).toBeInTheDocument();
    expect(screen.getByText("openai")).toBeInTheDocument();
    expect(screen.getByText("church-ministry")).toBeInTheDocument();
  });

  it("shows preview ids and stale reasons when present", async () => {
    const fetchJson = vi.fn().mockResolvedValue({
      provider: "openai",
      domain: "church-ministry",
      models: { chat: "gpt-4.1" },
      config_summary: { goal_count: 1 },
      adapter_summary: { guardrail_count: 1 },
      instruction_understanding_preview: {
        compiled_id: "compiled-42",
        compiled_status: "ready",
        review_id: "review-7",
        review_status: "not_reviewed",
        cache_status: "stale_resource_catalog",
        stale_reasons: ["resource_catalog_hash", "binding_logic_version"],
      },
    });

    renderPanel(fetchJson);

    fireEvent.click(screen.getByRole("button", { name: /load runtime summary/i }));

    expect(await screen.findByText("Review: not_reviewed")).toBeInTheDocument();
    expect(screen.getByText("Compiled ID: compiled-42")).toBeInTheDocument();
    expect(screen.getByText("Review ID: review-7")).toBeInTheDocument();
    expect(
      screen.getByText("Stale Reasons: resource_catalog_hash, binding_logic_version"),
    ).toBeInTheDocument();
  });
});
