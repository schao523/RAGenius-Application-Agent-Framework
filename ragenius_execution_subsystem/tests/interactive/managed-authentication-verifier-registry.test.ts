import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { ManagedAuthenticationVerifier } from "../../src/core/interactive/codex-managed-auth-targets.js";
import { ManagedAuthenticationVerifierRegistry } from "../../src/core/interactive/managed-authentication-verifier-registry.js";

function verifier(id: string): ManagedAuthenticationVerifier {
  return {
    id,
    async verify() {
      return { verified: true };
    }
  };
}

describe("ManagedAuthenticationVerifierRegistry", () => {
  it("provides immutable lookup for distinct trusted verifiers", () => {
    const gmail = verifier("codex-apps-gmail-auth");
    const registry = new ManagedAuthenticationVerifierRegistry([gmail]);

    assert.equal(registry.has("codex-apps-gmail-auth"), true);
    assert.equal(registry.get("codex-apps-gmail-auth"), gmail);
    assert.equal(registry.has("unknown"), false);
    assert.deepEqual([...registry.asReadonlyMap().keys()], ["codex-apps-gmail-auth"]);
  });

  it("rejects duplicate and blank verifier ids", () => {
    assert.throws(
      () => new ManagedAuthenticationVerifierRegistry([
        verifier("codex-apps-gmail-auth"),
        verifier("codex-apps-gmail-auth")
      ]),
      /duplicate/i
    );
    assert.throws(
      () => new ManagedAuthenticationVerifierRegistry([verifier("  ")]),
      /blank/i
    );
  });

  it("does not change when the constructor input array is mutated", () => {
    const entries = [verifier("codex-apps-gmail-auth")];
    const registry = new ManagedAuthenticationVerifierRegistry(entries);
    entries.push(verifier("later-verifier"));

    assert.equal(registry.has("later-verifier"), false);
    assert.deepEqual([...registry.asReadonlyMap().keys()], ["codex-apps-gmail-auth"]);
  });
});
