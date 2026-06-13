import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { z } from "zod";

import { AppError } from "../../src/core/errors/app-error.js";
import { ToolEngine } from "../../src/core/tools/tool-engine.js";
import { ToolRegistry } from "../../src/core/tools/tool-registry.js";
import { MockRagAdapterProvider } from "../../src/core/tools/providers/rag-adapter-provider.js";

describe("rag adapter placeholder", () => {
  it("returns read-only retrieval results", async () => {
    const registry = new ToolRegistry();
    const engine = new ToolEngine();

    const result = await engine.execute(registry.get("rag_retrieval_tool"), {
      query: "What is RAG?",
      topK: 2
    }, { appId: "app_001" });

    assert.equal(Array.isArray(result.items), true);
  });

  it("rejects attempted RAG mutation", async () => {
    const registry = new ToolRegistry();
    const engine = new ToolEngine();

    await assert.rejects(
      () =>
        engine.execute(registry.get("rag_retrieval_tool"), {
          query: "What is RAG?",
          operation: "delete"
        }, { appId: "app_001" }),
      (error: unknown) =>
        error instanceof AppError && error.code === "RAG_MUTATION_FORBIDDEN"
    );
  });

  it("returns metadata-only rows for search_metadata", async () => {
    const provider = new MockRagAdapterProvider();
    const result = (await provider.execute(
      {
        id: "search_metadata",
        name: "Search Metadata",
        providerType: "rag_adapter",
        inputSchema: z.object({ query: z.string() }),
        outputSchema: z.object({
          items: z.array(
            z.object({
              document_id: z.string(),
              title: z.string(),
              tags: z.array(z.string())
            })
          )
        }),
        permissionScopes: ["metadata.read"],
        sideEffecting: false
      },
      {
        query: "guide",
        limit: 5
      }
    )) as {
      items: Array<{ document_id: string; title: string; tags: string[] }>;
    };

    assert.equal(Array.isArray(result.items), true);
    assert.equal(result.items[0]?.document_id, "doc-metadata-1");
  });
});
