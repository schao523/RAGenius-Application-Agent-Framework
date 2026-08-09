import { createHash } from "node:crypto";

import type { ExecuteAgentRequest } from "../../api/schemas/execution-request.schema.js";

import type { AgentOperationPlanItem } from "./agent-provider-context.js";
import type { AgentPolicyDecision } from "./agent-policy.js";
import type { ResolvedAgentSkillSelection } from "../agent-skills/agent-skill-types.js";

function stableValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(stableValue);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .filter(([, item]) => item !== undefined)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, stableValue(item)])
    );
  }
  return value;
}

function targetHint(query: string): string | undefined {
  const match = query.match(/\b(?:to|in)\s+(?:the\s+)?([^,.]+?)(?:\s+notebook)?(?:,|\.|\bthen\b|$)/i);
  return match?.[1]?.trim() || undefined;
}

function notebookLmPlan(request: ExecuteAgentRequest): AgentOperationPlanItem[] {
  const query = request.agent_query.trim();
  const normalized = query.toLowerCase();
  const target = targetHint(query);
  const operations: AgentOperationPlanItem[] = [];

  if (/\badd\b/.test(normalized) && /\bsource\b/.test(normalized)) {
    operations.push({
      operation_id: "notebooklm_source_add",
      kind: "external_write",
      description: "Add the selected artifact as a NotebookLM source.",
      required: true,
      ...(target ? { target_hint: target } : {}),
      minimum_verification: "independently_verified"
    });
  }

  if (
    /\b(?:create|generate)\b/.test(normalized) &&
    /\b(?:report|study guide|briefing|slide deck|video)\b/.test(normalized)
  ) {
    operations.push({
      operation_id: "notebooklm_report_generate",
      kind: "external_write",
      description: "Start the requested NotebookLM artifact generation.",
      required: true,
      ...(target ? { target_hint: target } : {}),
      minimum_verification: "provider_reported"
    });
  }

  return operations;
}

export function createAgentOperationPlan(
  request: ExecuteAgentRequest,
  policy: AgentPolicyDecision,
  selection?: ResolvedAgentSkillSelection | null
): AgentOperationPlanItem[] {
  let operations: AgentOperationPlanItem[];
  if (request.agent_skill_hint?.trim().toLowerCase() === "notebooklm") {
    const knownPlan = notebookLmPlan(request);
    if (knownPlan.length > 0) {
      operations = knownPlan;
      return bindSelection(operations, selection);
    }
  }

  if (policy.riskClass === "agent_read_only") {
    operations = [{
      operation_id: "agent_read",
      kind: "read",
      description: request.agent_query,
      required: true,
      minimum_verification: "process_observed"
    }];
    return bindSelection(operations, selection);
  }

  if (policy.riskClass === "agent_workspace_write") {
    operations = [{
      operation_id: "agent_workspace_write",
      kind: "workspace_write",
      description: request.agent_query,
      required: true,
      minimum_verification: "process_observed"
    }];
    return bindSelection(operations, selection);
  }

  operations = [{
    operation_id: "agent_external_write",
    kind: "external_write",
    description: request.agent_query,
    required: true,
    minimum_verification: "provider_reported"
  }];
  return bindSelection(operations, selection);
}

function bindSelection(
  operations: AgentOperationPlanItem[],
  selection?: ResolvedAgentSkillSelection | null
): AgentOperationPlanItem[] {
  if (!selection) return operations;
  return operations.map((operation) => ({
    ...operation,
    activation_method: selection.activation_method,
    agent_skill_id: selection.agent_skill_id,
    agent_skill_backend: selection.backend,
    approved_fingerprint: selection.approved_fingerprint,
    observed_fingerprint: selection.observed_fingerprint,
    provider_skill_name: selection.provider_skill_name,
    provider_skill_reference: selection.provider_skill_reference,
    runtime_target_id: selection.runtime_target_id,
    source_id: selection.source_id
  }));
}

export function fingerprintAgentPolicy(snapshot: Record<string, unknown>): string {
  return createHash("sha256")
    .update(JSON.stringify(stableValue(snapshot)), "utf8")
    .digest("hex");
}
