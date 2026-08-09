import { timingSafeEqual } from "node:crypto";

import type { FastifyInstance, FastifyRequest } from "fastify";

import type { ServiceAuthRuntimeConfig } from "../../config/runtime-config.js";

export interface ExecutionPrincipal {
  serviceId: string;
  scopes: string[];
  type: "service";
}

function tokenMatches(authorization: string | undefined, token: string): boolean {
  const expected = Buffer.from(`Bearer ${token}`, "utf8");
  const actual = Buffer.from(authorization ?? "", "utf8");
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}

export function registerServiceAuth(
  app: FastifyInstance,
  config: ServiceAuthRuntimeConfig
): void {
  app.decorateRequest("executionPrincipal", null);

  if (!config.required && config.credentials.length === 0) {
    return;
  }

  app.addHook("onRequest", async (request, reply) => {
    if (!request.url.startsWith("/v1/")) {
      return;
    }

    const credential = config.credentials.find((candidate) =>
      tokenMatches(request.headers.authorization, candidate.token)
    );
    if (!credential) {
      return reply.status(401).send({
        error: {
          code: "SERVICE_AUTH_REQUIRED",
          message: "A valid execution service credential is required.",
          recoverable: true,
          suggested_action: "Call through an authenticated RAGenius service."
        }
      });
    }

    request.executionPrincipal = {
      serviceId: credential.serviceId,
      scopes: credential.scopes,
      type: "service"
    };
  });
}

export function hasServiceScope(
  request: FastifyRequest,
  scope: string
): boolean {
  return request.executionPrincipal?.scopes.includes(scope) === true;
}
