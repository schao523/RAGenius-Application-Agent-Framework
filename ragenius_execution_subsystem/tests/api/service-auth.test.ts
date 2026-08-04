import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";

import type { FastifyInstance } from "fastify";

import { hasServiceScope } from "../../src/api/auth/service-auth.js";
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
      scopes: ["execution"],
      type: "service"
    });
  });

  it("assigns caller-specific scopes and denies missing scopes", async () => {
    const runtimeConfig = buildRuntimeConfig(
      getEnv({
        DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
        MCP_SERVERS_JSON: "[]",
        RAGENIUS_EXECUTION_SERVICE_AUTH_REQUIRED: "true",
        RAGENIUS_EXECUTION_SERVICE_CREDENTIALS_JSON: JSON.stringify([
          {
            service_id: "ragenius_app",
            token: "app-token",
            scopes: ["execution", "agent_skills:read"]
          },
          {
            service_id: "ragenius_builder",
            token: "builder-token",
            scopes: ["agent_skills:admin"]
          }
        ])
      })
    );
    app = buildApp({}, runtimeConfig);
    app.get("/v1/test-admin", async (request, reply) => {
      if (!hasServiceScope(request, "agent_skills:admin")) {
        return reply.status(403).send({
          error: { code: "SERVICE_SCOPE_REQUIRED" }
        });
      }
      return { principal: request.executionPrincipal };
    });

    const appResponse = await app.inject({
      method: "GET",
      url: "/v1/test-admin",
      headers: { authorization: "Bearer app-token" }
    });
    const builderResponse = await app.inject({
      method: "GET",
      url: "/v1/test-admin",
      headers: { authorization: "Bearer builder-token" }
    });

    assert.equal(appResponse.statusCode, 403);
    assert.equal(appResponse.json().error.code, "SERVICE_SCOPE_REQUIRED");
    assert.equal(builderResponse.statusCode, 200);
    assert.deepEqual(builderResponse.json().principal, {
      serviceId: "ragenius_builder",
      scopes: ["agent_skills:admin"],
      type: "service"
    });
  });
});
