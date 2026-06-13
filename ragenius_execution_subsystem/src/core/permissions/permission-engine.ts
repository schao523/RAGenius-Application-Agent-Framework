import { AppError } from "../errors/app-error.js";
import type { ToolDefinition } from "../tools/tool.types.js";

import type {
  PermissionDecision,
  PermissionPolicy
} from "./permission.types.js";

export class PermissionEngine {
  private readonly policies: PermissionPolicy[];

  constructor(policies: PermissionPolicy[] = []) {
    this.policies = policies;
  }

  addPolicy(policy: PermissionPolicy): void {
    this.policies.push(policy);
  }

  evaluate(
    appId: string,
    tool: ToolDefinition,
    input: Record<string, unknown>,
    additionalPolicies: PermissionPolicy[] = []
  ): PermissionDecision[] {
    const effectivePolicies = [...this.policies, ...additionalPolicies];
    return tool.permissionScopes.map((scope) => {
      const matchingPolicies = effectivePolicies.filter(
        (policy) =>
          policy.appId === appId &&
          policy.toolId === tool.id &&
          policy.scope === scope
      );

      if (matchingPolicies.length === 0) {
        if (tool.providerType === "rag_adapter" && scope === "rag.read") {
          return {
            mode: "auto_allow",
            scope,
            toolId: tool.id,
            reason: "Read-only RAG retrieval is auto-allowed in MVP."
          };
        }

        return {
          mode: tool.sideEffecting ? "blocked" : "restricted",
          scope,
          toolId: tool.id,
          reason: tool.sideEffecting
            ? "Side-effecting tools require explicit policy."
            : "No explicit policy found."
        };
      }

      const selected = this.selectMostRestrictivePolicy(matchingPolicies);

      if (
        selected.mode === "restricted" &&
        !this.conditionsPass(selected.conditions, tool, input)
      ) {
        const blockedDecision: PermissionDecision = {
          mode: "blocked",
          scope,
          toolId: tool.id,
          reason: "Restricted policy conditions did not pass."
        };

        if (selected.conditions) {
          blockedDecision.conditions = selected.conditions;
        }

        return blockedDecision;
      }

      const decision: PermissionDecision = {
        mode: selected.mode,
        scope,
        toolId: tool.id,
        reason: "Policy matched."
      };

      if (selected.conditions) {
        decision.conditions = selected.conditions;
      }

      return decision;
    });
  }

  assertAllowed(
    appId: string,
    tool: ToolDefinition,
    input: Record<string, unknown>,
    additionalPolicies: PermissionPolicy[] = []
  ): PermissionDecision[] {
    const decisions = this.evaluate(appId, tool, input, additionalPolicies);

    for (const decision of decisions) {
      if (decision.mode === "require_confirmation") {
        throw new AppError({
          code: "PERMISSION_CONFIRMATION_REQUIRED",
          message: "Tool execution requires confirmation.",
          errorClass: "permission",
          httpStatus: 202,
          details: {
            tool_id: tool.id,
            permission_scope: decision.scope
          },
          recoverable: true,
          suggestedAction: "Collect confirmation and retry execution."
        });
      }

      if (decision.mode === "blocked") {
        throw new AppError({
          code: "PERMISSION_BLOCKED",
          message: "Tool execution is blocked by policy.",
          errorClass: "permission",
          httpStatus: 403,
          details: {
            tool_id: tool.id,
            permission_scope: decision.scope
          },
          recoverable: false,
          suggestedAction: "Update the permission policy or use a different tool."
        });
      }
    }

    return decisions;
  }

  private selectMostRestrictivePolicy(
    policies: PermissionPolicy[]
  ): PermissionPolicy {
    const rank: Record<PermissionPolicy["mode"], number> = {
      blocked: 3,
      require_confirmation: 2,
      restricted: 1,
      auto_allow: 0
    };

    return policies.reduce((current, candidate) =>
      rank[candidate.mode] > rank[current.mode] ? candidate : current
    );
  }

  private conditionsPass(
    conditions: Record<string, unknown> | undefined,
    tool: ToolDefinition,
    input: Record<string, unknown>
  ): boolean {
    if (!conditions) {
      return true;
    }

    if (
      typeof conditions.maxDuration === "number" &&
      typeof input.duration === "number" &&
      input.duration > conditions.maxDuration
    ) {
      return false;
    }

    if (Array.isArray(conditions.allowedProviderTypes)) {
      return conditions.allowedProviderTypes.includes(tool.providerType);
    }

    return true;
  }
}
