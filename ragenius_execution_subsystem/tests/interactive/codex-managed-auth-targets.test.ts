import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  eligibleManagedAuthenticationTargets,
  parseCodexManagedAuthenticationTargets,
  parseExactAuthenticationHosts,
  type ManagedAuthenticationVerifier
} from "../../src/core/interactive/codex-managed-auth-targets.js";

const verifier: ManagedAuthenticationVerifier = {
  id: "gmail-auth-check",
  async verify() {
    return { verified: true };
  }
};

describe("Codex managed authentication targets", () => {
  it("parses exact lowercase ASCII authentication hosts", () => {
    const hosts = parseExactAuthenticationHosts(
      '["accounts.google.com","login.microsoftonline.com"]'
    );
    assert.deepEqual(
      hosts,
      ["accounts.google.com", "login.microsoftonline.com"]
    );
    assert.equal(Object.isFrozen(hosts), true);
  });

  it("rejects malformed host and target JSON", () => {
    assert.throws(() => parseExactAuthenticationHosts("not-json"));
    assert.throws(() => parseCodexManagedAuthenticationTargets("not-json"));
  });

  it("rejects wildcard, uppercase, non-ASCII, and URL-shaped host entries", () => {
    for (const value of [
      '["*.google.com"]',
      '["Accounts.Google.com"]',
      '["登入.example.com"]',
      '["https://accounts.google.com/path"]'
    ]) {
      assert.throws(() => parseExactAuthenticationHosts(value));
    }
  });

  it("parses a valid HTTPS target and preserves administrator fields", () => {
    const targets = parseCodexManagedAuthenticationTargets(JSON.stringify([{
      id: "gmail",
      label: "Google sign-in",
      launch: { kind: "https_url", url: "https://accounts.google.com/" },
      allowedHosts: ["accounts.google.com"],
      verifierId: "gmail-auth-check"
    }]));

    assert.deepEqual(targets, [{
      id: "gmail",
      label: "Google sign-in",
      launch: { kind: "https_url", url: "https://accounts.google.com/" },
      allowedHosts: ["accounts.google.com"],
      verifierId: "gmail-auth-check"
    }]);
    assert.equal(Object.isFrozen(targets), true);
    assert.equal(Object.isFrozen(targets[0]), true);
  });

  it("rejects duplicate ids and unsafe HTTPS target shapes", () => {
    const target = {
      id: "gmail",
      label: "Google sign-in",
      launch: { kind: "https_url", url: "https://accounts.google.com/" },
      allowedHosts: ["accounts.google.com"],
      verifierId: "gmail-auth-check"
    };
    assert.throws(() => parseCodexManagedAuthenticationTargets(JSON.stringify([target, target])));

    for (const launch of [
      { kind: "https_url", url: "http://accounts.google.com/" },
      { kind: "https_url", url: "https://user@accounts.google.com/" },
      { kind: "https_url", url: "https://accounts.google.com/#fragment" }
    ]) {
      assert.throws(() => parseCodexManagedAuthenticationTargets(JSON.stringify([{
        ...target,
        launch
      }])));
    }
    assert.throws(() => parseCodexManagedAuthenticationTargets(JSON.stringify([{
      ...target,
      allowedHosts: ["login.google.com"]
    }])));
  });

  it("keeps targets ineligible until their trusted verifier is installed", () => {
    const targets = parseCodexManagedAuthenticationTargets(JSON.stringify([{
      id: "gmail",
      label: "Google sign-in",
      launch: { kind: "https_url", url: "https://accounts.google.com/" },
      allowedHosts: ["accounts.google.com"],
      verifierId: "gmail-auth-check"
    }]));

    assert.deepEqual(eligibleManagedAuthenticationTargets(targets, new Map()), []);
    assert.deepEqual(
      eligibleManagedAuthenticationTargets(targets, new Map([[verifier.id, verifier]])),
      targets
    );
  });
});
