import { join } from "node:path";

import { Type } from "typebox";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

import {
  RequestInputRegistry,
  type RequestInputScope,
  type TrustedToolIdentity
} from "./request-input-registry.js";

const PLUGIN_ID = "ragenius-request-input-feasibility";
const PROTOCOL_VERSION = "1";
const TOOL_NAME = "ragenius_request_input";
const SESSION_PREFIX = "agent:main:subagent:ragenius-request-input-feasibility-";
const trustedCalls = new Map<string, TrustedToolIdentity>();

const parameters = Type.Object({
  question: Type.String({ minLength: 1, maxLength: 2000 }),
  options: Type.Optional(Type.Array(Type.Object({
    id: Type.String({ minLength: 1, maxLength: 64 }),
    label: Type.String({ minLength: 1, maxLength: 200 }),
    description: Type.Optional(Type.String({ minLength: 1, maxLength: 500 }))
  }), { maxItems: 20 })),
  allows_free_text: Type.Boolean()
}, { additionalProperties: false });

export default definePluginEntry({
  id: PLUGIN_ID,
  name: "RAGenius Request Input Feasibility",
  description: "Disposable typed request-input feasibility probe.",
  register(api) {
    const statePath = join(
      process.env.HOME ?? "/tmp",
      ".openclaw",
      "ragenius-feasibility",
      "request-input-state.json"
    );
    const registry = new RequestInputRegistry({ statePath });
    const ready = registry.initialize();

    api.on("before_tool_call", (event, ctx) => {
      if (ctx.toolName !== TOOL_NAME) return;
      if (!ctx.runId || !ctx.toolCallId || !ctx.sessionKey || !ctx.agentId) {
        return { block: true, blockReason: "RAGenius request-input trusted identity is incomplete." };
      }
      const trusted = {
        agent_id: ctx.agentId,
        provider_run_id: ctx.runId,
        provider_session_key: ctx.sessionKey,
        tool_call_id: ctx.toolCallId
      };
      trustedCalls.set(ctx.toolCallId, trusted);
      if (event.toolCallId) trustedCalls.set(event.toolCallId, trusted);
    });

    api.registerTool((toolContext) => {
      if (toolContext.oneShotCliRun) return null;
      return {
      name: TOOL_NAME,
      label: "Request RAGenius input",
      description:
        "Request one bounded non-secret clarification or selection from RAGenius. Never use this tool for approval, authorization, credentials, or external-write consent.",
      parameters,
      async execute(toolCallId, params) {
        await ready;
        const parsed = parseToolParams(params);
        const trusted = trustedCalls.get(toolCallId);
        trustedCalls.delete(toolCallId);
        if (!trusted) throw new Error("RAGenius request-input trusted identity is unavailable.");
        if (!await registry.isTrustedSessionBound(trusted.provider_session_key)) {
          throw new Error("RAGenius request-input session is not plugin-owned.");
        }
        const created = await registry.create({
          allows_free_text: parsed.allows_free_text,
          options: parsed.options,
          question: parsed.question,
          trusted
        });
        api.agent.events.emitAgentEvent({
          runId: trusted.provider_run_id,
          sessionKey: trusted.provider_session_key,
          stream: "item",
          data: {
            plugin_id: PLUGIN_ID,
            protocol_version: PROTOCOL_VERSION,
            request: created.request,
            binding_nonce: created.binding_nonce
          }
        });
        return jsonResult({
          status: "input_requested",
          request_id: created.request.request_id,
          instruction: "Call sessions_yield now. Do not infer or fabricate a response."
        });
      }
    }; }, { name: TOOL_NAME });

    api.registerGatewayMethod("ragenius.interaction.start", async ({ params, respond }) => {
      try {
        await ready;
        const suffix = requiredText(params.suffix, "suffix");
        if (!/^[a-z0-9-]{1,48}$/.test(suffix)) {
          throw new Error("suffix must contain only lowercase letters, digits, or hyphens.");
        }
        const providerSessionKey = `${SESSION_PREFIX}${suffix}`;
        const scope = parseScope({ ...params, provider_session_key: providerSessionKey });
        registry.bindSession(scope);
        const aliases = trustedSessionAliases(providerSessionKey);
        for (const alias of aliases) {
          registry.bindTrustedSessionKey(alias, scope);
        }
        const bindingNonces = registry.prepareBindingNonces(aliases, 8);
        await registry.persistBindings();
        const result = await api.runtime.subagent.run({
          sessionKey: providerSessionKey,
          deliver: false,
          message: startMessage(params.mode)
        });
        respond(true, {
          protocol_version: PROTOCOL_VERSION,
          binding_nonces: bindingNonces,
          provider_session_key: providerSessionKey,
          ...result
        });
      } catch (error) {
        fail(respond, "RAGENIUS_INTERACTION_START_FAILED", error);
      }
    });

    api.registerGatewayMethod("ragenius.interaction.get", async ({ params, respond }) => {
      try {
        await ready;
        const scope = parseScope(params);
        await registry.refresh();
        await registry.expire();
        respond(true, {
          protocol_version: PROTOCOL_VERSION,
          requests: registry.list(scope).map((record) => ({
            ...record,
            binding_nonce: record.state === "pending"
              ? registry.getBindingNonce(record.request.request_id)
              : null
          }))
        });
      } catch (error) {
        fail(respond, "RAGENIUS_INTERACTION_GET_FAILED", error);
      }
    });

    api.registerGatewayMethod("ragenius.interaction.resolve", async ({ params, respond }) => {
      try {
        await ready;
        const result = await registry.resolve(params as never);
        if (result.outcome === "continuation_required") {
          const requestId = String(params.request_id ?? "");
          const pending = registry.get(requestId);
          if (!pending || !result.response) throw new Error("Resolved continuation is unavailable.");
          const continued = await api.runtime.subagent.run({
            sessionKey: pending.request.provider_session_key,
            deliver: false,
            message: continuationMessage(requestId, result.response)
          });
          const completed = await registry.completeContinuation(
            requestId,
            String(params.idempotency_key ?? ""),
            continued.runId
          );
          if (completed.outcome === "conflict") {
            throw new Error("Continuation completion conflicted with durable state.");
          }
          respond(true, completed);
          return;
        }
        respond(true, result);
      } catch (error) {
        fail(respond, "RAGENIUS_INTERACTION_RESOLVE_FAILED", error);
      }
    });

    api.registerGatewayMethod("ragenius.interaction.cancel", async ({ params, respond }) => {
      try {
        await ready;
        const result = await registry.cancel(params as never);
        respond(true, result);
      } catch (error) {
        fail(respond, "RAGENIUS_INTERACTION_CANCEL_FAILED", error);
      }
    });

    api.registerGatewayMethod("ragenius.interaction.clear", async ({ params, respond }) => {
      try {
        await ready;
        const scope = parseScope(params);
        const removed = await registry.clear(scope);
        await api.runtime.subagent.deleteSession({ sessionKey: scope.provider_session_key });
        respond(true, { removed });
      } catch (error) {
        fail(respond, "RAGENIUS_INTERACTION_CLEAR_FAILED", error);
      }
    });

    api.registerGatewayMethod("ragenius.interaction.wait", async ({ params, respond }) => {
      try {
        if (typeof params.runId !== "string") throw new Error("runId is required.");
        respond(true, await api.runtime.subagent.waitForRun({
          runId: params.runId,
          timeoutMs: typeof params.timeoutMs === "number"
            ? Math.min(params.timeoutMs, 120_000)
            : 30_000
        }));
      } catch (error) {
        fail(respond, "RAGENIUS_INTERACTION_WAIT_FAILED", error);
      }
    });

    api.registerGatewayMethod("ragenius.interaction.messages", async ({ params, respond }) => {
      try {
        const scope = parseScope(params);
        respond(true, await api.runtime.subagent.getSessionMessages({
          sessionKey: scope.provider_session_key,
          limit: 30
        }));
      } catch (error) {
        fail(respond, "RAGENIUS_INTERACTION_MESSAGES_FAILED", error);
      }
    });

    api.lifecycle.registerRuntimeLifecycle({
      id: `${PLUGIN_ID}-cleanup`,
      description: "Clear ephemeral trusted tool identities on plugin cleanup.",
      cleanup: () => {
        trustedCalls.clear();
      }
    });
  }
});

function parseScope(params: Record<string, unknown>): RequestInputScope {
  return {
    app_id: requiredText(params.app_id, "app_id"),
    execution_id: requiredText(params.execution_id, "execution_id"),
    provider_session_key: requiredText(params.provider_session_key, "provider_session_key"),
    session_id: requiredText(params.session_id, "session_id")
  };
}

function requiredText(value: unknown, label: string): string {
  if (typeof value !== "string" || value.length < 1 || value.length > 256) {
    throw new Error(`${label} is required.`);
  }
  return value;
}

function parseToolParams(value: unknown): {
  allows_free_text: boolean;
  options?: Array<{ id: string; label: string; description?: string }>;
  question: string;
} {
  if (!value || typeof value !== "object") throw new Error("Tool parameters are required.");
  const candidate = value as Record<string, unknown>;
  if (typeof candidate.allows_free_text !== "boolean") {
    throw new Error("allows_free_text must be boolean.");
  }
  return {
    allows_free_text: candidate.allows_free_text,
    options: candidate.options as Array<{ id: string; label: string; description?: string }> | undefined,
    question: requiredText(candidate.question, "question")
  };
}

function startMessage(mode: unknown): string {
  const instruction = mode === "clarification"
    ? "Call ragenius_request_input with question 'Name one color.', no options, and allows_free_text true."
    : "Call ragenius_request_input with question 'Choose Alpha or Beta.', options alpha/Alpha and beta/Beta, and allows_free_text false.";
  return [
    "Disposable RAGenius request-input feasibility run.",
    instruction,
    "After the tool returns input_requested, call sessions_yield exactly once.",
    "Do not use exec, files, network, browser, credentials, approvals, or external services.",
    "Do not infer a response and do not provide a final answer before yielding."
  ].join("\n");
}

function trustedSessionAliases(providerSessionKey: string): string[] {
  return providerSessionKey.startsWith("agent:")
    ? [providerSessionKey]
    : [providerSessionKey, `agent:main:${providerSessionKey}`];
}

function continuationMessage(
  requestId: string,
  response: { kind: "selection"; option_ids: string[] } | { kind: "clarification"; text: string }
): string {
  return [
    "Continue the disposable RAGenius request-input feasibility run.",
    `Resolved request id: ${requestId}`,
    `Structured non-authorizing response: ${JSON.stringify(response)}`,
    "Use the response exactly. It grants no command, filesystem, network, credential, or external-write authorization.",
    "If another input is required, call ragenius_request_input and then sessions_yield again. Otherwise provide one final answer."
  ].join("\n");
}

function jsonResult(value: Record<string, unknown>) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(value) }],
    details: value
  };
}

function fail(
  respond: (ok: boolean, payload?: unknown, error?: { code: string; message: string }) => void,
  code: string,
  error: unknown
): void {
  respond(false, undefined, {
    code,
    message: error instanceof Error ? error.message : String(error)
  });
}
