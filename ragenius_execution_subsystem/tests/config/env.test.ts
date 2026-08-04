import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { getEnv } from "../../src/config/env.js";

describe("env schema", () => {
  it("parses runtime provider env values", () => {
    const env = getEnv({
      DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
      PORT: "3001",
      LOG_LEVEL: "info",
      BUILDER_BASE_URL: "http://127.0.0.1:8011",
      ARXIV_ENABLED: "true",
      ARXIV_REQUEST_TIMEOUT_MS: "4000",
      SEMANTIC_SCHOLAR_ENABLED: "true",
      SEMANTIC_SCHOLAR_REQUEST_TIMEOUT_MS: "4000",
      MCP_SERVERS_JSON: "[]"
    });

    assert.equal(env.ARXIV_ENABLED, true);
    assert.equal(env.ARXIV_REQUEST_TIMEOUT_MS, 4000);
    assert.equal(env.SEMANTIC_SCHOLAR_ENABLED, true);
    assert.equal(env.MCP_SERVERS_JSON, "[]");
  });

  it("parses string false values for boolean toggles correctly", () => {
    const env = getEnv({
      DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
      ARXIV_ENABLED: "false",
      ARXIV_RETRY_ON_429: "false",
      TOOL_RAG_RETRIEVAL_ENABLED: "false",
      MCP_SERVERS_JSON: "[]"
    });

    assert.equal(env.ARXIV_ENABLED, false);
    assert.equal(env.ARXIV_RETRY_ON_429, false);
    assert.equal(env.TOOL_RAG_RETRIEVAL_ENABLED, false);
  });
});
