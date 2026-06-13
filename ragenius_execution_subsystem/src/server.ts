import { buildApp } from "./app.js";
import { getEnv } from "./config/env.js";
import { createPrismaClient } from "./db/prisma.js";
import { PrismaExecutionStore } from "./core/execution/prisma-execution-store.js";
import {
  buildRuntimeConfig,
  inspectRuntimeConfig,
  validateRuntimeConfig
} from "./config/runtime-config.js";

const env = getEnv();
const runtimeConfig = buildRuntimeConfig(env);
validateRuntimeConfig(runtimeConfig);
console.info(
  "[execution-subsystem] runtime config",
  JSON.stringify(inspectRuntimeConfig(runtimeConfig))
);
const prisma = createPrismaClient();
const app = buildApp(
  {
    executionStore: new PrismaExecutionStore(prisma)
  },
  runtimeConfig,
  {
    prismaClient: prisma
  }
);

async function start(): Promise<void> {
  await prisma.$connect();
  app.addHook("onClose", async () => {
    await prisma.$disconnect();
  });
  await app.listen({ port: env.PORT, host: "0.0.0.0" });
}

void start();
