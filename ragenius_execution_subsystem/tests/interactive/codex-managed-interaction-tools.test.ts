import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  buildRageniusDynamicToolSpecs,
  buildRageniusManagedInteractionGuidance,
  parseRageniusAuthenticationHandoffToolCall,
  parseRageniusUserActionToolCall,
  rageniusAuthenticationHandoffToolSpec,
  rageniusUserActionToolSpec
} from "../../src/core/interactive/codex-interaction-tool.js";
import type { CodexManagedAuthenticationTarget } from "../../src/core/interactive/codex-managed-auth-targets.js";

const target: CodexManagedAuthenticationTarget = {
  id: "gmail",
  label: "Google sign-in",
  launch: { kind: "https_url", url: "https://accounts.google.com/" },
  allowedHosts: ["accounts.google.com"],
  verifierId: "gmail-auth-check"
};

describe("Codex managed interaction tools", () => {
  it("publishes strict authentication and user-action tool schemas", () => {
    assert.equal(rageniusAuthenticationHandoffToolSpec.name, "ragenius_request_authentication_handoff");
    assert.deepEqual(rageniusAuthenticationHandoffToolSpec.inputSchema.required, [
      "authentication_target_id",
      "instruction"
    ]);
    assert.equal(rageniusAuthenticationHandoffToolSpec.inputSchema.additionalProperties, false);
    assert.equal(rageniusUserActionToolSpec.name, "ragenius_request_user_action");
    assert.deepEqual(rageniusUserActionToolSpec.inputSchema.required, ["instruction"]);
    assert.equal(rageniusUserActionToolSpec.inputSchema.additionalProperties, false);
  });

  it("resolves authentication by approved target id without accepting launch details", () => {
    const parsed = parseRageniusAuthenticationHandoffToolCall({
      authentication_target_id: "gmail",
      instruction: "Complete Google sign-in in the provider window.",
      completion_label: "I signed in"
    }, [target]);

    assert.equal(parsed.type, "authentication_handoff");
    assert.deepEqual(parsed.presentation, {
      completionLabel: "I signed in",
      launchAvailable: true,
      targetHost: "accounts.google.com",
      targetLabel: "Google sign-in"
    });
    assert.deepEqual(parsed.responseBinding, {
      kind: "managed_authentication",
      targetId: "gmail",
      verifierId: "gmail-auth-check"
    });
    assert.deepEqual(parsed.protectedLaunchTarget, target.launch);
  });

  it("rejects unknown targets, extra launch fields, and secret requests", () => {
    assert.throws(() => parseRageniusAuthenticationHandoffToolCall({
      authentication_target_id: "unknown",
      instruction: "Sign in."
    }, [target]), /AUTHENTICATION_TARGET_NOT_APPROVED/);
    assert.throws(() => parseRageniusAuthenticationHandoffToolCall({
      authentication_target_id: "gmail",
      instruction: "Sign in.",
      url: "https://attacker.example/"
    }, [target]));
    assert.throws(() => parseRageniusAuthenticationHandoffToolCall({
      authentication_target_id: "gmail",
      instruction: "Enter your password here."
    }, [target]), /secret/i);
  });

  it("normalizes one bounded non-secret manual action", () => {
    const parsed = parseRageniusUserActionToolCall({
      instruction: "Select the prepared video in the open file chooser.",
      completion_label: "The file is selected"
    });
    assert.deepEqual(parsed, {
      allowsFreeText: false,
      options: [],
      presentation: { completionLabel: "The file is selected" },
      prompt: "Select the prepared video in the open file chooser.",
      responseBinding: { kind: "managed_user_action" },
      type: "user_action_required"
    });
    assert.throws(() => parseRageniusUserActionToolCall({
      instruction: "Approve publishing this video externally."
    }), /authorize|external write/i);
    assert.throws(() => parseRageniusUserActionToolCall({
      instruction: "Paste the OTP."
    }), /secret/i);
  });

  it("exposes tools and trusted guidance only for enabled eligible capabilities", () => {
    assert.deepEqual(buildRageniusDynamicToolSpecs({
      inputEnabled: false,
      authHandoffEnabled: false,
      userActionEnabled: false,
      eligibleTargets: []
    }), []);
    assert.equal(buildRageniusManagedInteractionGuidance({
      authHandoffEnabled: false,
      userActionEnabled: false,
      eligibleTargets: []
    }), "");

    const tools = buildRageniusDynamicToolSpecs({
      inputEnabled: true,
      authHandoffEnabled: true,
      userActionEnabled: true,
      eligibleTargets: [target]
    });
    assert.deepEqual(tools.map((tool) => tool.name), [
      "ragenius_request_input",
      "ragenius_request_authentication_handoff",
      "ragenius_request_user_action"
    ]);
    const guidance = buildRageniusManagedInteractionGuidance({
      authHandoffEnabled: true,
      userActionEnabled: true,
      eligibleTargets: [target]
    });
    assert.match(guidance, /gmail: Google sign-in/);
    assert.equal(guidance.includes("accounts.google.com"), false);
    assert.equal(guidance.includes("https://"), false);
  });
});
