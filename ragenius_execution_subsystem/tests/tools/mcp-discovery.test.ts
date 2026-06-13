import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { ToolEngine } from "../../src/core/tools/tool-engine.js";
import { ToolRegistry } from "../../src/core/tools/tool-registry.js";

describe("mcp discovery placeholder", () => {
  it("maps discovered MCP tools into the internal registry", async () => {
    const engine = new ToolEngine({
      mcp: {
        async discover(providerId: string) {
          return [
            {
              id: `mcp.${providerId}.search_pages`,
              name: "Search Pages",
              providerType: "mcp",
              inputSchema: { safeParse: (value: unknown) => ({ success: true, data: value }) } as never,
              outputSchema: { safeParse: (value: unknown) => ({ success: true, data: value }) } as never,
              permissionScopes: ["external_api.read"],
              sideEffecting: false
            },
            {
              id: `mcp.${providerId}.create_page`,
              name: "Create Page",
              providerType: "mcp",
              inputSchema: { safeParse: (value: unknown) => ({ success: true, data: value }) } as never,
              outputSchema: { safeParse: (value: unknown) => ({ success: true, data: value }) } as never,
              permissionScopes: ["external_api.write"],
              sideEffecting: true
            }
          ];
        }
      } as never
    });
    const registry = new ToolRegistry();
    const discovered = await engine.discoverMcpTools("mcp_mock_001");

    for (const tool of discovered) {
      registry.register(tool);
    }

    const readTool = registry.get("mcp.mcp_mock_001.search_pages");
    const writeTool = registry.get("mcp.mcp_mock_001.create_page");

    assert.equal(readTool.providerType, "mcp");
    assert.equal(writeTool.sideEffecting, true);
  });
});
