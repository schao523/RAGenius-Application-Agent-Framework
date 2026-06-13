import type { FastifyInstance } from "fastify";

import { inspectRuntimeConfig } from "../../config/runtime-config.js";

export async function registerHealthRoutes(app: FastifyInstance): Promise<void> {
  app.get("/healthz", async () => ({ status: "ok" }));
  app.get("/readyz", async () => ({
    status: "ready",
    checks: {
      database: "not_configured",
      runtime_config: inspectRuntimeConfig(app.services.runtimeConfig),
      mcp_discovery: app.services.mcpDiscovery
    }
  }));
}
