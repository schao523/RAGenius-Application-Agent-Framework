import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { z } from "zod";

import { AppError } from "../../src/core/errors/app-error.js";
import { AdapterToolProvider } from "../../src/core/tools/providers/adapter-tool-provider.js";
import { NotebookLmAdapter } from "../../src/core/tools/providers/notebooklm-adapter.js";

describe("adapter tool provider", () => {
  it("executes an approved adapter", async () => {
    const provider = new AdapterToolProvider({
      tools: [
        {
          id: "content_transform_adapter",
          command: "internal:transform",
          args: [],
          enabled: true
        }
      ]
    });

    const result = await provider.execute(
      {
        id: "content_transform_adapter",
        name: "Content Transform Adapter",
        providerType: "adapter",
        inputSchema: z.object({ content: z.string() }),
        outputSchema: z.object({ output: z.string() }),
        permissionScopes: ["adapter.execute"],
        sideEffecting: false
      },
      { content: "hello" },
      { appId: "app_001" }
    );

    assert.deepEqual(result, { output: "HELLO" });
  });

  it("rejects non-allowlisted adapters", async () => {
    const provider = new AdapterToolProvider({ tools: [] });

    await assert.rejects(
      () =>
        provider.execute(
          {
            id: "unknown_adapter",
            name: "Unknown Adapter",
            providerType: "adapter",
            inputSchema: z.object({}),
            outputSchema: z.object({ output: z.string() }),
            permissionScopes: ["adapter.execute"],
            sideEffecting: false
          },
          {},
          { appId: "app_001" }
        ),
      (error: unknown) =>
        error instanceof AppError && error.code === "ADAPTER_NOT_ALLOWED"
    );
  });

  it("routes notebooklm adapter tools through the notebooklm adapter family", async () => {
    const notebooklmAdapter = new NotebookLmAdapter(
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
      async () => ({
        ok: true,
        result: {
          notebooks: [{ id: "nb_1", title: "Research", sources_count: 3 }]
        }
      })
    );

    const provider = new AdapterToolProvider(
      {
        tools: [
          {
            id: "adapter.notebooklm.list_notebooks",
            command: "python",
            args: ["scripts/notebooklm_bridge.py"],
            enabled: true
          }
        ]
      },
      { notebooklmAdapter }
    );

    const result = await provider.execute(
      {
        id: "adapter.notebooklm.list_notebooks",
        name: "NotebookLM List Notebooks",
        providerType: "adapter",
        inputSchema: z.object({}),
        outputSchema: z.object({
          notebooks: z.array(
            z.object({
              id: z.string(),
              title: z.string(),
              sources_count: z.number()
            })
          )
        }),
        permissionScopes: ["external_api.read"],
        sideEffecting: false
      },
      {},
      { appId: "app_001" }
    );

    assert.deepEqual(result, {
      notebooks: [{ id: "nb_1", title: "Research", sources_count: 3 }]
    });
  });
});
