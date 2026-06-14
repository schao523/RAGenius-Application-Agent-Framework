import { createAppServices } from "../src/app.js";
import { getEnv } from "../src/config/env.js";
import { buildRuntimeConfig } from "../src/config/runtime-config.js";

async function main(): Promise<void> {
  if (process.env.OPENCLAW_REAL_SMOKE !== "1") {
    console.error("Set OPENCLAW_REAL_SMOKE=1 to run the real OpenClaw smoke test.");
    process.exitCode = 2;
    return;
  }

  const runtimeConfig = buildRuntimeConfig(getEnv());
  const services = createAppServices({}, runtimeConfig);
  const result = await services.executionEngine.execute({
    request_type: "execute_agent",
    app_id: "smoke_app",
    session_id: "smoke_session",
    agent_backend: "openclaw_cli",
    agent_query: "Reply with exactly: OK."
  });

  console.log(
    JSON.stringify(
      {
        status: result.status,
        execution_id: result.execution_id,
        logs_summary: result.logs_summary,
        result: result.result
      },
      null,
      2
    )
  );

  if (result.status !== "completed") {
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
