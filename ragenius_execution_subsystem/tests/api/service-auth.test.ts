import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";

import type { FastifyInstance } from "fastify";

import { buildApp } from "../../src/app.js";
import { getEnv } from "../../src/config/env.js";
import { buildRuntimeConfig } from "../../src/config/runtime-config.js";

describe("execution service authentication", () => {
  let app: FastifyInstance | undefined;

  afterEach(async () => {
    await app?.close();
    app = undefined;
  });

  it("protects v1 routes while leaving health checks available", async () => {
    const runtimeConfig = buildRuntimeConfig(
      getEnv({
        DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
        MCP_SERVERS_JSON: "[]",
        RAGENIUS_EXECUTION_SERVICE_AUTH_REQUIRED: "true",
        RAGENIUS_EXECUTION_SERVICE_ID: "ragenius_app_backend",
        RAGENIUS_EXECUTION_SERVICE_TOKEN: "service-secret"
      })
    );
    app = buildApp({}, runtimeConfig);
    app.get("/v1/test-principal", async (request) => ({
      principal: request.executionPrincipal
    }));

    const healthResponse = await app.inject({
      method: "GET",
      url: "/healthz"
    });
    const missingTokenResponse = await app.inject({
      method: "GET",
      url: "/v1/tools/inventory"
    });
    const wrongTokenResponse = await app.inject({
      method: "GET",
      url: "/v1/tools/inventory",
      headers: { authorization: "Bearer wrong-secret" }
    });
    const authenticatedResponse = await app.inject({
      method: "GET",
      url: "/v1/test-principal",
      headers: { authorization: "Bearer service-secret" }
    });

    assert.equal(healthResponse.statusCode, 200);
    assert.equal(missingTokenResponse.statusCode, 401);
    assert.equal(
      missingTokenResponse.json().error.code,
      "SERVICE_AUTH_REQUIRED"
    );
    assert.equal(wrongTokenResponse.statusCode, 401);
    assert.equal(authenticatedResponse.statusCode, 200);
    assert.deepEqual(authenticatedResponse.json().principal, {
      serviceId: "ragenius_app_backend",
      type: "service"
    });
  });
});
