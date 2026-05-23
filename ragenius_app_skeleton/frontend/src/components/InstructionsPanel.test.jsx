import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import InstructionsPanel from "./InstructionsPanel";

const styles = {
  card: {},
  sectionTitle: {},
  muted: {},
  row: {},
  button: {},
  linkButton: {},
  disabledLinkButton: {},
  pill: {},
  label: {},
  code: {},
  error: {},
};

function renderPanel(fetchJson = vi.fn()) {
  return render(
    <InstructionsPanel
      baseUrl="http://api.example.test"
      builderBaseUrl="http://builder.example.test"
      builderAvailable
      appId="app-1"
      styles={styles}
      fetchJson={fetchJson}
    />,
  );
}

describe("InstructionsPanel", () => {
  it("shows flattened preview status after loading instructions only", async () => {
    const fetchJson = vi.fn().mockResolvedValue({
      instructions: {
        version: "v3",
        checksum: "abcdef1234567890",
        content: "# Instructions\n\nPreview only.",
      },
      instruction_understanding_preview: {
        compiled_status: "ready",
        review_status: "reviewed_ok",
        cache_status: "warm",
        semantic_compile_attached: true,
        semantic_compile_valid: true,
      },
    });

    renderPanel(fetchJson);

    fireEvent.click(screen.getByRole("button", { name: /load instructions/i }));

    await waitFor(() => {
      expect(fetchJson).toHaveBeenCalledWith(
        "http://api.example.test/apps/app-1/instructions",
        { headers: { "x-role": "admin" } },
      );
    });

    expect(screen.getByText("Compiled: ready")).toBeInTheDocument();
    expect(screen.getByText("Review: reviewed_ok")).toBeInTheDocument();
    expect(screen.getByText("Cache: warm")).toBeInTheDocument();
    expect(screen.getByText("Semantic Compile: attached")).toBeInTheDocument();
    expect(screen.getByText("Semantic Valid: yes")).toBeInTheDocument();
    expect(screen.getByText(/Preview only\./)).toBeInTheDocument();
  });

  it("renders review summary and findings after loading understanding detail", async () => {
    const fetchJson = vi.fn().mockResolvedValue({
      app_id: "app-1",
      compiled: {
        id: "compiled-1",
        compiled_status: "ready",
        metadata: {
          semantic_compile_attached: true,
          semantic_compile_valid: true,
        },
        compiled_contract: {
          hybrid_instruction_runtime_model: {
            default_workflow_id: "workflow:default",
          },
        },
      },
      review: {
        id: "review-1",
        review_status: "reviewed_with_warnings",
        review_summary_md: "# Review\n\nWarning present.",
        review_findings: {
          warnings: ["Check trigger specificity"],
          confidence: 0.61,
        },
      },
      status: {
        compiled_status: "ready",
        review_status: "reviewed_with_warnings",
        cache_status: "hot",
      },
      cache_status: "hot",
      stale_reasons: [],
    });

    renderPanel(fetchJson);

    fireEvent.click(screen.getByRole("button", { name: /load understanding/i }));

    await waitFor(() => {
      expect(fetchJson).toHaveBeenCalledWith(
        "http://api.example.test/apps/app-1/instruction-understanding",
        { headers: { "x-role": "admin" } },
      );
    });

    expect(screen.getByText("Compiled: ready")).toBeInTheDocument();
    expect(screen.getByText("Review: reviewed_with_warnings")).toBeInTheDocument();
    expect(screen.getByText("Cache: hot")).toBeInTheDocument();
    expect(screen.getByText("Semantic Compile: attached")).toBeInTheDocument();
    expect(screen.getByText("Semantic Valid: yes")).toBeInTheDocument();
    expect(screen.getByText("workflow:default")).toBeInTheDocument();
    expect(screen.getByText(/Warning present\./)).toBeInTheDocument();
    expect(screen.getByText("warnings")).toBeInTheDocument();
    expect(screen.getByText(/Check trigger specificity/)).toBeInTheDocument();
  });

  it("shows empty review state when no review exists", async () => {
    const fetchJson = vi.fn().mockResolvedValue({
      app_id: "app-1",
      compiled: { id: "compiled-1", compiled_status: "ready" },
      review: null,
      status: {
        compiled_status: "ready",
        review_status: "not_reviewed",
        cache_status: "stale_resource_catalog",
      },
      cache_status: "stale_resource_catalog",
      stale_reasons: ["resource_catalog_hash"],
    });

    renderPanel(fetchJson);

    fireEvent.click(screen.getByRole("button", { name: /load understanding/i }));

    await screen.findByText("Review: not_reviewed");
    expect(screen.getByText("Compiled: ready")).toBeInTheDocument();
    expect(screen.getByText("Cache: stale_resource_catalog")).toBeInTheDocument();
    expect(screen.getByText(/No review has been run yet\./)).toBeInTheDocument();
  });

  it("shows latest failed attempt separately from the active model", async () => {
    const fetchJson = vi.fn().mockResolvedValue({
      app_id: "app-1",
      compiled: {
        id: "compiled-active-1",
        compiled_status: "ready",
        metadata: {
          semantic_compile_attached: true,
          semantic_compile_valid: true,
        },
      },
      latest_attempt: {
        id: "attempt-bad-2",
        semantic_compile_valid: false,
        validation_errors: [
          "intent_routed_multi_workflow requires executable procedure_steps",
          "routing rules must resolve to executable workflow or module targets",
        ],
      },
      review: null,
      status: {
        compiled_status: "ready",
        review_status: "not_reviewed",
        cache_status: "hot",
      },
      cache_status: "hot",
      stale_reasons: [],
    });

    renderPanel(fetchJson);

    fireEvent.click(screen.getByRole("button", { name: /load understanding/i }));

    await screen.findByText("Compiled: ready");
    expect(screen.getByText("Latest Failed Attempt")).toBeInTheDocument();
    expect(screen.getByText("Attempt: attempt-bad-2")).toBeInTheDocument();
    expect(screen.getByText("Semantic Valid: no")).toBeInTheDocument();
    expect(
      screen.getByText(/intent_routed_multi_workflow requires executable procedure_steps/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/routing rules must resolve to executable workflow or module targets/i),
    ).toBeInTheDocument();
  });

  it("can invoke recompile and run review actions against the right endpoints", async () => {
    const fetchJson = vi
      .fn()
      .mockResolvedValueOnce({
        app_id: "app-1",
        compiled: { id: "compiled-1", compiled_status: "ready" },
        review: null,
        status: {
          compiled_status: "ready",
          review_status: "not_reviewed",
          cache_status: "hot",
        },
        cache_status: "hot",
        stale_reasons: [],
      })
      .mockResolvedValueOnce({
        app_id: "app-1",
        compiled: { id: "compiled-2", compiled_status: "ready" },
        review: null,
        status: {
          compiled_status: "ready",
          review_status: "not_reviewed",
          cache_status: "recompiled",
        },
        cache_status: "recompiled",
        stale_reasons: ["forced_recompile"],
      })
      .mockResolvedValueOnce({
        app_id: "app-1",
        compiled: { id: "compiled-2", compiled_status: "ready" },
        review: {
          id: "review-2",
          review_status: "reviewed_ok",
          review_summary_md: "# Review\n\nLooks good.",
          review_findings: { ok: true },
        },
        status: {
          compiled_status: "ready",
          review_status: "reviewed_ok",
          cache_status: "reviewed",
        },
        cache_status: "reviewed",
        stale_reasons: [],
      });

    renderPanel(fetchJson);

    fireEvent.click(screen.getByRole("button", { name: /load understanding/i }));
    await screen.findByText("Review: not_reviewed");

    fireEvent.click(screen.getByRole("button", { name: /recompile/i }));
    await waitFor(() => {
      expect(fetchJson).toHaveBeenNthCalledWith(
        2,
        "http://api.example.test/apps/app-1/instruction-understanding/recompile",
        {
          method: "POST",
          headers: { "x-role": "admin" },
        },
      );
    });

    fireEvent.click(screen.getByRole("button", { name: /run review/i }));
    await waitFor(() => {
      expect(fetchJson).toHaveBeenNthCalledWith(
        3,
        "http://api.example.test/apps/app-1/instruction-understanding/review",
        {
          method: "POST",
          headers: { "x-role": "admin" },
        },
      );
    });

    expect(await screen.findByText("Review: reviewed_ok")).toBeInTheDocument();
    expect(screen.getByText(/Looks good\./)).toBeInTheDocument();
  });
});
