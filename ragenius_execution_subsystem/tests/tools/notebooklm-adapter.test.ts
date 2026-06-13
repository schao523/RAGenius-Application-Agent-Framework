import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { afterEach, describe, it } from "node:test";

import { AppError } from "../../src/core/errors/app-error.js";
import { ArtifactStore } from "../../src/core/tools/providers/artifact-store.js";
import {
  NotebookLmAdapter,
  type NotebookLmBridgeExecutor
} from "../../src/core/tools/providers/notebooklm-adapter.js";

const artifactRoots = new Set<string>();

function createArtifactRoot(): string {
  const root = path.resolve(
    `D:/GitHub/Codex-RAGenius-System/outputs/test-notebooklm-artifacts-${randomUUID()}`
  );
  artifactRoots.add(root);
  return root;
}

async function cleanupArtifactRoot(root: string): Promise<void> {
  for (let attempt = 0; attempt < 5; attempt += 1) {
    try {
      await fs.rm(root, { recursive: true, force: true });
      return;
    } catch (error) {
      if (
        !(error && typeof error === "object" && "code" in error) ||
        (error as { code?: string }).code !== "EPERM" ||
        attempt === 4
      ) {
        if (
          error &&
          typeof error === "object" &&
          "code" in error &&
          (error as { code?: string }).code === "EPERM"
        ) {
          return;
        }
        throw error;
      }
      await new Promise((resolve) => setTimeout(resolve, 50 * (attempt + 1)));
    }
  }
}

describe("notebooklm adapter", () => {
  afterEach(async () => {
    await Promise.all(
      [...artifactRoots].map(async (root) => {
        await cleanupArtifactRoot(root);
        artifactRoots.delete(root);
      })
    );
  });

  it("executes list_notebooks through the bridge and normalizes notebooks", async () => {
    const executor: NotebookLmBridgeExecutor = async (request) => {
      assert.equal(request.operation, "list_notebooks");
      assert.deepEqual(request.arguments, {});

      return {
        ok: true,
        result: {
          notebooks: [{ id: "nb_1", title: "Research", sources_count: 3 }]
        }
      };
    };

    const adapter = new NotebookLmAdapter(
      {
        enabled: true,
        pythonCommand: "python",
        bridgeScript: "scripts/notebooklm_bridge.py",
        authMode: "env_json",
        allowedOperations: ["list_notebooks"],
        generationDefaults: {
          waitForCompletion: true,
          persistArtifacts: true
        }
      },
      executor
    );

    const result = await adapter.execute("list_notebooks", {}, { appId: "app_001" });

    assert.deepEqual(result, {
      notebooks: [{ id: "nb_1", title: "Research", sources_count: 3 }]
    });
  });

  it("maps bridge errors into AppError", async () => {
    const executor: NotebookLmBridgeExecutor = async () => ({
      ok: false,
      error: {
        code: "NOTEBOOKLM_AUTH_FAILED",
        message: "NotebookLM auth is invalid.",
        details: { auth_mode: "env_json" },
        recoverable: false,
        suggested_action: "Refresh NotebookLM auth."
      }
    });

    const adapter = new NotebookLmAdapter(
      {
        enabled: true,
        pythonCommand: "python",
        bridgeScript: "scripts/notebooklm_bridge.py",
        authMode: "env_json",
        allowedOperations: ["list_notebooks"],
        generationDefaults: {
          waitForCompletion: true,
          persistArtifacts: true
        }
      },
      executor
    );

    await assert.rejects(
      () => adapter.execute("list_notebooks", {}, { appId: "app_001" }),
      (error: unknown) =>
        error instanceof AppError && error.code === "NOTEBOOKLM_AUTH_FAILED"
    );
  });

  it("maps raw bridge execution failures into AppError diagnostics", async () => {
    const executor: NotebookLmBridgeExecutor = async () => {
      throw new Error("NotebookLM bridge exited with code 1. stderr details");
    };

    const adapter = new NotebookLmAdapter(
      {
        enabled: true,
        pythonCommand: "python",
        bridgeScript: "scripts/notebooklm_bridge.py",
        authMode: "profile",
        allowedOperations: ["list_notebooks"],
        generationDefaults: {
          waitForCompletion: true,
          persistArtifacts: true
        }
      },
      executor
    );

    await assert.rejects(
      () => adapter.execute("list_notebooks", {}, { appId: "app_001" }),
      (error: unknown) =>
        error instanceof AppError &&
        error.code === "NOTEBOOKLM_BRIDGE_FAILED" &&
        error.details !== undefined &&
        error.details !== null &&
        typeof error.details === "object" &&
        "operation" in error.details &&
        "cause" in error.details
    );
  });

  it("executes list_sources through the bridge and normalizes sources", async () => {
    const executor: NotebookLmBridgeExecutor = async (request) => {
      assert.equal(request.operation, "list_sources");
      assert.deepEqual(request.arguments, { notebookId: "nb_1" });

      return {
        ok: true,
        result: {
          sources: [
            {
              id: "src_1",
              title: "Paper A",
              kind: "pdf",
              status: "ready"
            }
          ]
        }
      };
    };

    const adapter = new NotebookLmAdapter(
      {
        enabled: true,
        pythonCommand: "python",
        bridgeScript: "scripts/notebooklm_bridge.py",
        authMode: "env_json",
        allowedOperations: ["list_sources"],
        generationDefaults: {
          waitForCompletion: true,
          persistArtifacts: true
        }
      },
      executor
    );

    const result = await adapter.execute(
      "list_sources",
      { notebookId: "nb_1" },
      { appId: "app_001" }
    );

    assert.deepEqual(result, {
      sources: [
        {
          id: "src_1",
          title: "Paper A",
          kind: "pdf",
          status: "ready"
        }
      ]
    });
  });

  it("resolves notebookTitle to notebookId for notebook-scoped operations", async () => {
    const requests: Array<{ operation: string; arguments: Record<string, unknown> }> =
      [];
    const executor: NotebookLmBridgeExecutor = async (request) => {
      requests.push({
        operation: request.operation,
        arguments: request.arguments
      });

      if (request.operation === "list_notebooks") {
        return {
          ok: true,
          result: {
            notebooks: [
              { id: "nb_1", title: "Research", sources_count: 3 },
              { id: "nb_2", title: "Other", sources_count: 1 }
            ]
          }
        };
      }

      assert.equal(request.operation, "ask");
      assert.deepEqual(request.arguments, {
        notebookId: "nb_1",
        question: "What are the themes?"
      });

      return {
        ok: true,
        result: {
          answer: "The themes are synthesis and evidence.",
          conversation_id: "conv_1",
          references: [{ source_id: "src_1", title: "Paper A" }],
          turn_number: 1
        }
      };
    };

    const adapter = new NotebookLmAdapter(
      {
        enabled: true,
        pythonCommand: "python",
        bridgeScript: "scripts/notebooklm_bridge.py",
        authMode: "env_json",
        allowedOperations: ["list_notebooks", "ask"],
        generationDefaults: {
          waitForCompletion: true,
          persistArtifacts: true
        }
      },
      executor
    );

    const result = await adapter.execute(
      "ask",
      { notebookTitle: "Research", question: "What are the themes?" },
      { appId: "app_001" }
    );

    assert.equal(requests[0]?.operation, "list_notebooks");
    assert.equal(requests[1]?.operation, "ask");
    assert.deepEqual(result, {
      answer: "The themes are synthesis and evidence.",
      conversation_id: "conv_1",
      references: [{ source_id: "src_1", title: "Paper A" }],
      turn_number: 1
    });
  });

  it("prefers notebookId over notebookTitle when both are provided", async () => {
    const executor: NotebookLmBridgeExecutor = async (request) => {
      assert.equal(request.operation, "list_sources");
      assert.deepEqual(request.arguments, { notebookId: "nb_direct" });
      return {
        ok: true,
        result: {
          sources: []
        }
      };
    };

    const adapter = new NotebookLmAdapter(
      {
        enabled: true,
        pythonCommand: "python",
        bridgeScript: "scripts/notebooklm_bridge.py",
        authMode: "env_json",
        allowedOperations: ["list_sources"],
        generationDefaults: {
          waitForCompletion: true,
          persistArtifacts: true
        }
      },
      executor
    );

    const result = await adapter.execute(
      "list_sources",
      { notebookId: "nb_direct", notebookTitle: "Research" },
      { appId: "app_001" }
    );

    assert.deepEqual(result, { sources: [] });
  });

  it("returns a clear error when notebookTitle cannot be resolved", async () => {
    const executor: NotebookLmBridgeExecutor = async (request) => {
      assert.equal(request.operation, "list_notebooks");
      return {
        ok: true,
        result: {
          notebooks: [{ id: "nb_1", title: "Other", sources_count: 1 }]
        }
      };
    };

    const adapter = new NotebookLmAdapter(
      {
        enabled: true,
        pythonCommand: "python",
        bridgeScript: "scripts/notebooklm_bridge.py",
        authMode: "env_json",
        allowedOperations: ["list_notebooks", "list_sources"],
        generationDefaults: {
          waitForCompletion: true,
          persistArtifacts: true
        }
      },
      executor
    );

    await assert.rejects(
      () =>
        adapter.execute(
          "list_sources",
          { notebookTitle: "Research" },
          { appId: "app_001" }
        ),
      (error: unknown) =>
        error instanceof AppError &&
        error.code === "NOTEBOOKLM_NOTEBOOK_NOT_FOUND"
    );
  });

  it("returns a clear error when notebookTitle is ambiguous", async () => {
    const executor: NotebookLmBridgeExecutor = async (request) => {
      assert.equal(request.operation, "list_notebooks");
      return {
        ok: true,
        result: {
          notebooks: [
            { id: "nb_1", title: "Research", sources_count: 3 },
            { id: "nb_2", title: "Research", sources_count: 1 }
          ]
        }
      };
    };

    const adapter = new NotebookLmAdapter(
      {
        enabled: true,
        pythonCommand: "python",
        bridgeScript: "scripts/notebooklm_bridge.py",
        authMode: "env_json",
        allowedOperations: ["list_notebooks", "list_sources"],
        generationDefaults: {
          waitForCompletion: true,
          persistArtifacts: true
        }
      },
      executor
    );

    await assert.rejects(
      () =>
        adapter.execute(
          "list_sources",
          { notebookTitle: "Research" },
          { appId: "app_001" }
        ),
      (error: unknown) =>
        error instanceof AppError &&
        error.code === "NOTEBOOKLM_NOTEBOOK_TITLE_AMBIGUOUS"
    );
  });

  it("executes ask through the bridge and normalizes answer payloads", async () => {
    const executor: NotebookLmBridgeExecutor = async (request) => {
      assert.equal(request.operation, "ask");
      assert.deepEqual(request.arguments, {
        notebookId: "nb_1",
        question: "What are the themes?"
      });

      return {
        ok: true,
        result: {
          answer: "The themes are synthesis and evidence.",
          conversation_id: "conv_1",
          references: [{ source_id: "src_1", title: "Paper A" }],
          turn_number: 1
        }
      };
    };

    const adapter = new NotebookLmAdapter(
      {
        enabled: true,
        pythonCommand: "python",
        bridgeScript: "scripts/notebooklm_bridge.py",
        authMode: "env_json",
        allowedOperations: ["ask"],
        generationDefaults: {
          waitForCompletion: true,
          persistArtifacts: true
        }
      },
      executor
    );

    const result = await adapter.execute(
      "ask",
      { notebookId: "nb_1", question: "What are the themes?" },
      { appId: "app_001" }
    );

    assert.deepEqual(result, {
      answer: "The themes are synthesis and evidence.",
      conversation_id: "conv_1",
      references: [{ source_id: "src_1", title: "Paper A" }],
      turn_number: 1
    });
  });

  it("executes add_source_text through the bridge", async () => {
    const executor: NotebookLmBridgeExecutor = async (request) => {
      assert.equal(request.operation, "add_source_text");
      assert.deepEqual(request.arguments, {
        notebookId: "nb_1",
        title: "RAGenius Notes",
        content: "Important findings",
        wait: true
      });

      return {
        ok: true,
        result: {
          notebook_id: "nb_1",
          source: {
            id: "src_2",
            title: "RAGenius Notes",
            kind: "text",
            status: "ready"
          }
        }
      };
    };

    const adapter = new NotebookLmAdapter(
      {
        enabled: true,
        pythonCommand: "python",
        bridgeScript: "scripts/notebooklm_bridge.py",
        authMode: "env_json",
        allowedOperations: ["add_source_text"],
        generationDefaults: {
          waitForCompletion: true,
          persistArtifacts: true
        }
      },
      executor
    );

    const result = await adapter.execute(
      "add_source_text",
      {
        notebookId: "nb_1",
        title: "RAGenius Notes",
        content: "Important findings",
        wait: true
      },
      { appId: "app_001" }
    );

    assert.deepEqual(result, {
      notebook_id: "nb_1",
      source: {
        id: "src_2",
        title: "RAGenius Notes",
        kind: "text",
        status: "ready"
      }
    });
  });

  it("applies generation defaults for generate_report", async () => {
    const executor: NotebookLmBridgeExecutor = async (request) => {
      assert.equal(request.operation, "generate_report");
      assert.deepEqual(request.arguments, {
        notebookId: "nb_1",
        customPrompt: "Make it concise",
        waitForCompletion: true,
        persistArtifacts: true
      });

      return {
        ok: true,
        result: {
          notebook_id: "nb_1",
          artifact_kind: "report",
          task_id: "task_1",
          status: "completed",
          content_markdown: "# Summary"
        }
      };
    };

    const adapter = new NotebookLmAdapter(
      {
        enabled: true,
        pythonCommand: "python",
        bridgeScript: "scripts/notebooklm_bridge.py",
        authMode: "env_json",
        allowedOperations: ["generate_report"],
        generationDefaults: {
          waitForCompletion: true,
          persistArtifacts: true
        }
      },
      executor
    );

    const result = await adapter.execute(
      "generate_report",
      {
        notebookId: "nb_1",
        customPrompt: "Make it concise"
      },
      { appId: "app_001" }
    );

    assert.deepEqual(result, {
      notebook_id: "nb_1",
      artifact_kind: "report",
      task_id: "task_1",
      status: "completed",
      content_markdown: "# Summary"
    });
  });

  it("persists completed notebooklm reports as stored artifacts when requested", async () => {
    const artifactStore = new ArtifactStore(createArtifactRoot());
    const adapter = new NotebookLmAdapter(
      {
        enabled: true,
        pythonCommand: "python",
        bridgeScript: "scripts/notebooklm_bridge.py",
        authMode: "env_json",
        allowedOperations: ["generate_report"],
        generationDefaults: {
          waitForCompletion: true,
          persistArtifacts: true
        }
      },
      async () => ({
        ok: true,
        result: {
          notebook_id: "nb_1",
          artifact_kind: "report",
          task_id: "task_1",
          status: "completed",
          content_markdown: "# NotebookLM Report"
        }
      }),
      { artifactStore }
    );

    const result = await adapter.execute(
      "generate_report",
      {
        notebookId: "nb_1",
        notebookTitle: "GPT Application Designer",
        customPrompt: "Summarize the notebook"
      },
      {
        appId: "app_001",
        executionId: "execution_001",
        skillId: "notebooklm_generate_report"
      }
    );

    const artifacts = (result as { artifacts?: Array<Record<string, unknown>> }).artifacts;
    assert.equal(Array.isArray(artifacts), true);
    assert.equal(artifacts?.length, 1);
    assert.equal(artifacts?.[0]?.artifact_type, "notebooklm_report");
    assert.equal(
      artifacts?.[0]?.display_name,
      "NotebookLM Report - GPT Application Designer.md"
    );
    assert.equal(artifacts?.[0]?.source_skill_id, "notebooklm_generate_report");
    assert.match(String(artifacts?.[0]?.file_path), /GPT Application Designer\.md$/);
  });

  it("executes poll_artifact_task through the bridge", async () => {
    const executor: NotebookLmBridgeExecutor = async (request) => {
      assert.equal(request.operation, "poll_artifact_task");
      assert.deepEqual(request.arguments, {
        notebookId: "nb_1",
        taskId: "task_video_1",
        artifactKind: "video"
      });

      return {
        ok: true,
        result: {
          notebook_id: "nb_1",
          artifact_kind: "video",
          task_id: "task_video_1",
          status: "completed"
        }
      };
    };

    const adapter = new NotebookLmAdapter(
      {
        enabled: true,
        pythonCommand: "python",
        bridgeScript: "scripts/notebooklm_bridge.py",
        authMode: "env_json",
        allowedOperations: ["poll_artifact_task"],
        generationDefaults: {
          waitForCompletion: true,
          persistArtifacts: true
        }
      },
      executor
    );

    const result = await adapter.execute(
      "poll_artifact_task",
      {
        notebookId: "nb_1",
        taskId: "task_video_1",
        artifactKind: "video"
      },
      { appId: "app_001" }
    );

    assert.deepEqual(result, {
      notebook_id: "nb_1",
      artifact_kind: "video",
      task_id: "task_video_1",
      status: "completed"
    });
  });
});
