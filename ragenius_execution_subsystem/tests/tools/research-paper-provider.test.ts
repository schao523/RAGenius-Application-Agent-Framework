import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";

import type { ResearchPaperProviderConfig } from "../../src/config/provider-config.js";
import { ResearchPaperProvider } from "../../src/core/tools/providers/research-paper-provider.js";

const originalFetch = globalThis.fetch;

const defaultConfig: ResearchPaperProviderConfig = {
  arxiv: {
    enabled: true,
    requestTimeoutMs: 4000,
    retryOn429: true,
    maxRetries: 1
  },
  semanticScholar: {
    enabled: true,
    requestTimeoutMs: 4000,
    maxResultsDefault: 5
  }
};

describe("research paper provider", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("uses the configured Semantic Scholar API key instead of process env", async () => {
    let observedApiKey = "";
    globalThis.fetch = (async (_input: string | URL, init?: RequestInit) => {
      observedApiKey = String(
        new Headers(init?.headers).get("x-api-key") ?? ""
      );
      return new Response(
        JSON.stringify({
          total: 1,
          offset: 0,
          data: [
            {
              paperId: "paper-1",
              url: "https://www.semanticscholar.org/paper/paper-1",
              title: "Configured API Key Result",
              abstract: "Configured API key summary.",
              year: 2024,
              authors: [{ name: "Config Tester" }]
            }
          ]
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    const provider = new ResearchPaperProvider({
      ...defaultConfig,
      semanticScholar: {
        ...defaultConfig.semanticScholar,
        apiKey: "configured-semantic-key"
      }
    });

    const result = await provider.search({
      topic: "DeepSeek Mixture of Experts Technology",
      limit: 1,
      source: "semantic-scholar"
    });

    assert.equal(observedApiKey, "configured-semantic-key");
    assert.equal(result.source, "semantic-scholar");
    assert.equal(result.papers[0]?.title, "Configured API Key Result");
  });

  it("falls back to Semantic Scholar in auto mode when arXiv is disabled by config", async () => {
    let arxivCalls = 0;
    let semanticCalls = 0;
    globalThis.fetch = (async (input: string | URL) => {
      const url = String(input);
      if (url.includes("export.arxiv.org/api/query")) {
        arxivCalls += 1;
      }
      semanticCalls += 1;
      return new Response(
        JSON.stringify({
          total: 1,
          offset: 0,
          data: [
            {
              paperId: "paper-semantic-only",
              url: "https://www.semanticscholar.org/paper/paper-semantic-only",
              title: "Semantic-Only Result",
              abstract: "Semantic Scholar only result.",
              year: 2025,
              authors: [{ name: "Semantic Only Author" }]
            }
          ]
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as typeof fetch;

    const provider = new ResearchPaperProvider({
      ...defaultConfig,
      arxiv: {
        ...defaultConfig.arxiv,
        enabled: false
      }
    });

    const result = await provider.search({
      topic: "DeepSeek Mixture of Experts Technology",
      limit: 1,
      source: "auto"
    });

    assert.equal(arxivCalls, 0);
    assert.equal(semanticCalls, 1);
    assert.equal(result.source, "semantic-scholar");
    assert.equal(result.papers[0]?.title, "Semantic-Only Result");
  });
});
