import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

const SESSION_PREFIX = "agent:main:subagent:ragenius-yield-feasibility-";

function sessionKeyFor(value: unknown): string {
  const suffix = typeof value === "string" ? value : "default";
  if (!/^[a-z0-9-]{1,48}$/.test(suffix)) {
    throw new Error("suffix must contain only lowercase letters, digits, or hyphens");
  }
  return `${SESSION_PREFIX}${suffix}`;
}

export default definePluginEntry({
  id: "ragenius-yield-feasibility",
  name: "RAGenius Yield Feasibility",
  description: "Disposable same-session continuation feasibility probe.",
  register(api) {
    api.registerGatewayMethod("ragenius.yield.start", async ({ params, respond }) => {
      try {
        const sessionKey = sessionKeyFor(params?.suffix);
        const result = await api.runtime.subagent.run({
          sessionKey,
          deliver: false,
          message:
            "Disposable feasibility test. Remember marker RYF-731. Call sessions_yield exactly once now without spawning a child. Do not use exec, files, network, browser, or external services. Do not provide a final answer before the yield call.",
        });
        respond(true, { sessionKey, ...result });
      } catch (error) {
        respond(false, undefined, {
          code: "RAGENIUS_YIELD_START_FAILED",
          message: error instanceof Error ? error.message : String(error),
        });
      }
    });

    api.registerGatewayMethod("ragenius.yield.continue", async ({ params, respond }) => {
      try {
        const sessionKey = sessionKeyFor(params?.suffix);
        const message =
          typeof params?.message === "string" && params.message.length <= 1000
            ? params.message
            : "Continue the feasibility test. Reply exactly CONTINUED: RYF-731.";
        const result = await api.runtime.subagent.run({
          sessionKey,
          deliver: false,
          message,
        });
        respond(true, { sessionKey, ...result });
      } catch (error) {
        respond(false, undefined, {
          code: "RAGENIUS_YIELD_CONTINUE_FAILED",
          message: error instanceof Error ? error.message : String(error),
        });
      }
    });

    api.registerGatewayMethod("ragenius.yield.wait", async ({ params, respond }) => {
      try {
        if (typeof params?.runId !== "string") {
          throw new Error("runId is required");
        }
        const timeoutMs =
          typeof params.timeoutMs === "number" ? Math.min(params.timeoutMs, 30_000) : 10_000;
        const result = await api.runtime.subagent.waitForRun({
          runId: params.runId,
          timeoutMs,
        });
        respond(true, result);
      } catch (error) {
        respond(false, undefined, {
          code: "RAGENIUS_YIELD_WAIT_FAILED",
          message: error instanceof Error ? error.message : String(error),
        });
      }
    });

    api.registerGatewayMethod("ragenius.yield.messages", async ({ params, respond }) => {
      try {
        const sessionKey = sessionKeyFor(params?.suffix);
        const result = await api.runtime.subagent.getSessionMessages({
          sessionKey,
          limit: 20,
        });
        respond(true, { sessionKey, ...result });
      } catch (error) {
        respond(false, undefined, {
          code: "RAGENIUS_YIELD_MESSAGES_FAILED",
          message: error instanceof Error ? error.message : String(error),
        });
      }
    });

    api.registerGatewayMethod("ragenius.yield.cleanup", async ({ params, respond }) => {
      try {
        const sessionKey = sessionKeyFor(params?.suffix);
        await api.runtime.subagent.deleteSession({ sessionKey });
        respond(true, { sessionKey, deleted: true });
      } catch (error) {
        respond(false, undefined, {
          code: "RAGENIUS_YIELD_CLEANUP_FAILED",
          message: error instanceof Error ? error.message : String(error),
        });
      }
    });
  },
});
