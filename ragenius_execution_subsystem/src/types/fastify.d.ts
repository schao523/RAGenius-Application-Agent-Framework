import type { AppServices } from "../app.js";
import type { ExecutionPrincipal } from "../api/auth/service-auth.js";

declare module "fastify" {
  interface FastifyInstance {
    services: AppServices;
  }

  interface FastifyRequest {
    executionPrincipal: ExecutionPrincipal | null;
  }
}
