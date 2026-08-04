import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";

import { AppError } from "../../src/core/errors/app-error.js";
import { PermissionEngine } from "../../src/core/permissions/permission-engine.js";
import { ToolEngine } from "../../src/core/tools/tool-engine.js";
import { ToolRegistry } from "../../src/core/tools/tool-registry.js";
import type { ToolDefinition } from "../../src/core/tools/tool.types.js";

const originalFetch = globalThis.fetch;
type PaperSearchResult = {
  source: string;
  papers: Array<{
    title: string;
    year: number;
    authors: string[];
  }>;
};

describe("tool engine placeholder", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("registers phase 1 safe core tools", () => {
    const registry = new ToolRegistry();

    assert.equal(registry.get("read_file").id, "read_file");
    assert.equal(registry.get("list_files").id, "list_files");
    assert.equal(registry.get("retrieve_documents").id, "retrieve_documents");
    assert.equal(registry.get("search_metadata").id, "search_metadata");
    assert.equal(registry.get("save_artifact").id, "save_artifact");
    assert.equal(registry.get("load_artifact").id, "load_artifact");
    assert.equal(registry.get("write_file").id, "write_file");
    assert.equal(registry.get("patch_file").id, "patch_file");
  });

  it("validates tool input before execution", async () => {
    const registry = new ToolRegistry();
    const engine = new ToolEngine();

    await assert.rejects(
      () =>
        engine.execute(registry.get("mock_video_generation_tool"), {
          prompt: "hello",
          duration: "30"
        }, { appId: "app_001" }),
      (error: unknown) =>
        error instanceof AppError && error.errorClass === "validation"
    );
  });

  it("rejects unknown tools from the registry", () => {
    const registry = new ToolRegistry();

    assert.throws(
      () => registry.get("missing_tool"),
      (error: unknown) =>
        error instanceof AppError && error.code === "TOOL_NOT_FOUND"
    );
  });

  it("classifies provider failures as tool errors", async () => {
    const registry = new ToolRegistry();
    const permissions = new PermissionEngine([
      {
        appId: "app_001",
        toolId: "mock_video_generation_tool",
        scope: "external_api.write",
        mode: "auto_allow"
      }
    ]);
    const engine = new ToolEngine(undefined, permissions);

    await assert.rejects(
      () =>
        engine.execute(registry.get("mock_video_generation_tool"), {
          prompt: "provider-failure",
          duration: 30
        }, { appId: "app_001" }),
      (error: unknown) =>
        error instanceof AppError && error.errorClass === "tool"
    );
  });

  it("classifies timed out tools as timeout errors", async () => {
    const registry = new ToolRegistry();
    const permissions = new PermissionEngine([
      {
        appId: "app_001",
        toolId: "mock_video_generation_tool",
        scope: "external_api.write",
        mode: "auto_allow"
      }
    ]);
    const engine = new ToolEngine(undefined, permissions);

    await assert.rejects(
      () =>
        engine.execute(registry.get("mock_video_generation_tool"), {
          prompt: "timeout",
          duration: 30
        }, { appId: "app_001" }),
      (error: unknown) =>
        error instanceof AppError && error.errorClass === "timeout"
    );
  });

  it("checks permission before provider invocation", async () => {
    let providerCalled = false;
    const registry = new ToolRegistry();
    const permissions = new PermissionEngine();
    const engine = new ToolEngine(
      {
        api: {
          async execute() {
            providerCalled = true;
            return {
              title: "blocked",
              summary: "blocked",
              file_id: "blocked"
            };
          }
        }
      },
      permissions
    );

    await assert.rejects(
      () =>
        engine.execute(
          registry.get("mock_video_generation_tool"),
          {
            prompt: "hello",
            duration: 30
          },
          { appId: "app_001" }
        ),
      (error: unknown) =>
        error instanceof AppError && error.code === "PERMISSION_BLOCKED"
    );

    assert.equal(providerCalled, false);
  });

  it("passes app context through to local providers", async () => {
    const registry = new ToolRegistry();
    let seenAppId: string | undefined;
    const permissions = new PermissionEngine([
      {
        appId: "app_local_ctx",
        toolId: "read_file",
        scope: "filesystem.read",
        mode: "auto_allow"
      }
    ]);
    const engine = new ToolEngine(
      {
        local: {
          async execute(_tool, _input, options) {
            seenAppId = options?.appId;
            return {
              path: "D:/GitHub/Codex-RAGenius-System/README.md",
              content: "ok",
              truncated: false,
              size_bytes: 2
            };
          }
        }
      },
      permissions
    );

    const result = (await engine.execute(
      registry.get("read_file"),
      {
        path: "D:/GitHub/Codex-RAGenius-System/README.md"
      },
      { appId: "app_local_ctx" }
    )) as { content: string };

    assert.equal(seenAppId, "app_local_ctx");
    assert.equal(result.content, "ok");
  });

  it("executes an approved adapter tool through the provider", async () => {
    const registry = new ToolRegistry();
    const permissions = new PermissionEngine([
      {
        appId: "app_adapter",
        toolId: "content_transform_adapter",
        scope: "adapter.execute",
        mode: "auto_allow"
      }
    ]);
    const engine = new ToolEngine(
      {
        adapter: {
          async execute(
            _tool: ToolDefinition,
            input: Record<string, unknown>,
            options?: {
              appId: string;
              sessionId?: string;
              confirmed?: boolean;
              executionId?: string | null;
              skillId?: string;
            }
          ) {
            assert.equal(options?.appId, "app_adapter");
            return {
              output: String(input.content ?? "").toUpperCase()
            };
          }
        }
      } as never,
      permissions
    );

    const result = (await engine.execute(
      registry.get("content_transform_adapter"),
      {
        content: "hello"
      },
      { appId: "app_adapter" }
    )) as { output: string };

    assert.equal(result.output, "HELLO");
  });

  it("executes research paper search against arXiv and maps structured paper results", async () => {
    globalThis.fetch = (async (input: string | URL) => {
      const url = String(input);
      assert.match(url, /export\.arxiv\.org\/api\/query/);
      return new Response(
        `<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <title>DeepSeek Mixture of Experts for Retrieval</title>
    <summary>Research summary one.</summary>
    <published>2024-01-15T00:00:00Z</published>
    <author><name>Alice Doe</name></author>
    <author><name>Bob Roe</name></author>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.00002v1</id>
    <title>DeepSeek Sparse Expert Routing</title>
    <summary>Research summary two.</summary>
    <published>2023-05-20T00:00:00Z</published>
    <author><name>Carol Poe</name></author>
  </entry>
</feed>`,
        { status: 200, headers: { "Content-Type": "application/atom+xml" } }
      );
    }) as typeof fetch;

    const registry = new ToolRegistry();
    const engine = new ToolEngine();

    const result = (await engine.execute(
      registry.get("research_paper_search_tool"),
      {
        topic: "DeepSeek Mixture of Experts Technology",
        limit: 2,
        source: "arxiv"
      },
      { appId: "app_001" }
    )) as PaperSearchResult;

    assert.equal(result.source, "arxiv");
    assert.equal(result.papers.length, 2);
    assert.equal(result.papers[0]?.title, "DeepSeek Mixture of Experts for Retrieval");
    assert.equal(result.papers[0]?.year, 2024);
    assert.deepEqual(result.papers[0]?.authors, ["Alice Doe", "Bob Roe"]);
  });

  it("executes research paper search against Semantic Scholar and maps structured paper results", async () => {
    globalThis.fetch = (async (input: string | URL) => {
      const url = String(input);
      assert.match(url, /api\.semanticscholar\.org\/graph\/v1\/paper\/search/);
      return new Response(
        JSON.stringify({
          total: 1,
          offset: 0,
          data: [
            {
              paperId: "paper-1",
              url: "https://www.semanticscholar.org/paper/paper-1",
              title: "Semantic Scholar DeepSeek Experts",
              abstract: "Semantic Scholar summary.",
              year: 2022,
              authors: [{ name: "Dana Smith" }, { name: "Eli Chen" }]
            }
          ]
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    const registry = new ToolRegistry();
    const engine = new ToolEngine();

    const result = (await engine.execute(
      registry.get("research_paper_search_tool"),
      {
        topic: "DeepSeek Mixture of Experts Technology",
        limit: 1,
        source: "semantic-scholar"
      },
      { appId: "app_001" }
    )) as PaperSearchResult;

    assert.equal(result.source, "semantic-scholar");
    assert.equal(result.papers.length, 1);
    assert.equal(result.papers[0]?.title, "Semantic Scholar DeepSeek Experts");
    assert.deepEqual(result.papers[0]?.authors, ["Dana Smith", "Eli Chen"]);
  });

  it("falls back to arXiv-only and still succeeds when Semantic Scholar is unavailable", async () => {
    let semanticCalls = 0;
    globalThis.fetch = (async (input: string | URL) => {
      const url = String(input);
      if (url.includes("export.arxiv.org/api/query")) {
        return new Response(
          `<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00003v1</id>
    <title>Fallback arXiv Result</title>
    <summary>Fallback summary.</summary>
    <published>2024-02-01T00:00:00Z</published>
    <author><name>Fallback Author</name></author>
  </entry>
</feed>`,
          { status: 200, headers: { "Content-Type": "application/atom+xml" } }
        );
      }
      semanticCalls += 1;
      return new Response(
        JSON.stringify({ error: "rate limited" }),
        { status: 429, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    const registry = new ToolRegistry();
    const engine = new ToolEngine();

    const result = (await engine.execute(
      registry.get("research_paper_search_tool"),
      {
        topic: "DeepSeek Mixture of Experts Technology",
        limit: 2,
        source: "auto"
      },
      { appId: "app_001" }
    )) as PaperSearchResult;

    assert.equal(semanticCalls, 1);
    assert.equal(result.source, "arxiv");
    assert.equal(result.papers.length, 1);
    assert.equal(result.papers[0]?.title, "Fallback arXiv Result");
  });

  it("falls back to Semantic Scholar and still succeeds when arXiv is rate limited in auto mode", async () => {
    let arxivCalls = 0;
    let semanticCalls = 0;
    globalThis.fetch = (async (input: string | URL) => {
      const url = String(input);
      if (url.includes("export.arxiv.org/api/query")) {
        arxivCalls += 1;
        return new Response(
          `rate limited`,
          { status: 429, headers: { "Content-Type": "text/plain" } }
        );
      }
      semanticCalls += 1;
      return new Response(
        JSON.stringify({
          total: 1,
          offset: 0,
          data: [
            {
              paperId: "paper-fallback",
              url: "https://www.semanticscholar.org/paper/paper-fallback",
              title: "Semantic Fallback Result",
              abstract: "Recovered through Semantic Scholar.",
              year: 2021,
              authors: [{ name: "Fallback Researcher" }]
            }
          ]
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    const registry = new ToolRegistry();
    const engine = new ToolEngine();

    const result = (await engine.execute(
      registry.get("research_paper_search_tool"),
      {
        topic: "DeepSeek Mixture of Experts Technology",
        limit: 2,
        source: "auto"
      },
      { appId: "app_001" }
    )) as PaperSearchResult;

    assert.equal(arxivCalls, 2);
    assert.equal(semanticCalls, 1);
    assert.equal(result.source, "semantic-scholar");
    assert.equal(result.papers.length, 1);
    assert.equal(result.papers[0]?.title, "Semantic Fallback Result");
  });

  it("falls back to Semantic Scholar and still succeeds when arXiv hangs in auto mode", async () => {
    let arxivCalls = 0;
    let semanticCalls = 0;
    globalThis.fetch = ((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("export.arxiv.org/api/query")) {
        arxivCalls += 1;
        return new Promise<Response>((_, reject) => {
          init?.signal?.addEventListener(
            "abort",
            () => reject(new DOMException("aborted", "AbortError")),
            { once: true }
          );
        });
      }
      semanticCalls += 1;
      return Promise.resolve(
        new Response(
          JSON.stringify({
            total: 1,
            offset: 0,
            data: [
              {
                paperId: "paper-timeout-fallback",
                url: "https://www.semanticscholar.org/paper/paper-timeout-fallback",
                title: "Semantic Timeout Fallback Result",
                abstract: "Recovered after arXiv timeout.",
                year: 2020,
                authors: [{ name: "Timeout Fallback Author" }]
              }
            ]
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );
    }) as typeof fetch;

    const registry = new ToolRegistry();
    const engine = new ToolEngine();

    const result = (await engine.execute(
      registry.get("research_paper_search_tool"),
      {
        topic: "DeepSeek Mixture of Experts Technology",
        limit: 2,
        source: "auto"
      },
      { appId: "app_001" }
    )) as PaperSearchResult;

    assert.equal(arxivCalls, 1);
    assert.equal(semanticCalls, 1);
    assert.equal(result.source, "semantic-scholar");
    assert.equal(result.papers[0]?.title, "Semantic Timeout Fallback Result");
  });
});
