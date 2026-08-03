import assert from "node:assert/strict";
import test from "node:test";

import {
  buildCodexChildEnv,
  resolveCodexAdditionalWritableDirs,
  resolveNotebookLmWritableDir
} from "../../scripts/codex_cli_environment.js";

test("buildCodexChildEnv removes Python TLS overrides from the Codex child", () => {
  const childEnv = buildCodexChildEnv({
    SSL_CERT_FILE: "C:/python/certifi/cacert.pem",
    REQUESTS_CA_BUNDLE: "C:/python/certifi/cacert.pem",
    CURL_CA_BUNDLE: "C:/python/certifi/cacert.pem",
    PYTHONHTTPSVERIFY: "1",
    CODEX_HOME: "C:/Users/User/.codex",
    PATH: "C:/Windows/System32"
  });

  assert.equal(childEnv.SSL_CERT_FILE, undefined);
  assert.equal(childEnv.REQUESTS_CA_BUNDLE, undefined);
  assert.equal(childEnv.CURL_CA_BUNDLE, undefined);
  assert.equal(childEnv.PYTHONHTTPSVERIFY, undefined);
  assert.equal(childEnv.CODEX_HOME, "C:/Users/User/.codex");
  assert.equal(childEnv.PATH, "C:/Windows/System32");
});

test("resolves the NotebookLM profile directory from trusted environment settings", () => {
  assert.equal(
    resolveNotebookLmWritableDir({
      USERPROFILE: "C:\\Users\\User",
      NOTEBOOKLM_PROFILE: "default"
    }),
    "C:\\Users\\User\\.notebooklm\\profiles\\default"
  );

  assert.equal(
    resolveNotebookLmWritableDir({
      USERPROFILE: "C:\\Users\\User",
      NOTEBOOKLM_STORAGE_PATH: "D:\\auth\\storage_state.json"
    }),
    "D:\\auth"
  );
});

test("rejects unsafe NotebookLM profile names", () => {
  assert.equal(
    resolveNotebookLmWritableDir({
      USERPROFILE: "C:\\Users\\User",
      NOTEBOOKLM_PROFILE: "..\\other"
    }),
    undefined
  );
});

test("grants the NotebookLM profile only to NotebookLM-hinted runs", () => {
  const environment = {
    USERPROFILE: "C:\\Users\\User",
    NOTEBOOKLM_PROFILE: "default"
  };

  assert.deepEqual(
    resolveCodexAdditionalWritableDirs(
      { agent_skill_hint: "notebooklm" },
      environment
    ),
    ["C:\\Users\\User\\.notebooklm\\profiles\\default"]
  );
  assert.deepEqual(
    resolveCodexAdditionalWritableDirs({ agent_skill_hint: "auto" }, environment),
    []
  );
  assert.deepEqual(
    resolveCodexAdditionalWritableDirs({}, environment),
    []
  );
});
