import { describe, expect, it } from "vitest";

import { resolveActiveAppDisplay, resolveInstructionUnderstandingState } from "./App";

describe("resolveActiveAppDisplay", () => {
  it("prefers detailed app info only when it matches the selected app", () => {
    const selectedApp = {
      id: "app-b",
      name: "App B",
      starter_questions: ["B1", "B2"],
    };
    const staleAppInfo = {
      id: "app-a",
      name: "App A",
      starter_questions: ["A1", "A2"],
    };

    const display = resolveActiveAppDisplay(selectedApp, staleAppInfo, "app-b");

    expect(display.appName).toBe("App B");
    expect(display.starterQuestions).toEqual(["B1", "B2"]);
  });

  it("uses detailed app info when it matches the selected app", () => {
    const selectedApp = {
      id: "app-b",
      name: "App B",
      starter_questions: ["B1"],
    };
    const appInfo = {
      id: "app-b",
      name: "App B Detailed",
      starter_questions: ["BD1", "BD2"],
    };

    const display = resolveActiveAppDisplay(selectedApp, appInfo, "app-b");

    expect(display.appName).toBe("App B Detailed");
    expect(display.starterQuestions).toEqual(["BD1", "BD2"]);
  });
});

describe("resolveInstructionUnderstandingState", () => {
  it("marks compile required when preview is missing", () => {
    const state = resolveInstructionUnderstandingState({});

    expect(state.compileRequired).toBe(true);
    expect(state.message).toContain("run Recompile");
  });

  it("marks compile available when preview has a compiled id", () => {
    const state = resolveInstructionUnderstandingState({
      instruction_understanding_preview: {
        compiled_id: "compiled-1",
        compile_required: false,
      },
    });

    expect(state.compileRequired).toBe(false);
    expect(state.message).toBe("");
  });

  it("keeps compile required for hybrid apps when semantic validity is false", () => {
    const state = resolveInstructionUnderstandingState({
      instruction_understanding_preview: {
        compiled_id: "compiled-1",
        compile_required: false,
        semantic_compile_attached: true,
        semantic_compile_valid: false,
        primary_service_mode: "intent_routed_multi_workflow",
      },
    });

    expect(state.compileRequired).toBe(true);
    expect(state.message).toContain("run Recompile");
  });

  it("keeps compile available for interaction-logic apps when semantic model is valid", () => {
    const state = resolveInstructionUnderstandingState({
      instruction_understanding_preview: {
        compiled_id: "compiled-1",
        compile_required: false,
        semantic_compile_attached: true,
        semantic_compile_valid: true,
        primary_service_mode: "intent_routed_interaction_logic",
      },
    });

    expect(state.compileRequired).toBe(false);
    expect(state.message).toBe("");
  });
});
