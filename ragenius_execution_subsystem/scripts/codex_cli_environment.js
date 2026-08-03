import path from "node:path";

const PYTHON_TLS_ENV_KEYS = [
  "SSL_CERT_FILE",
  "REQUESTS_CA_BUNDLE",
  "CURL_CA_BUNDLE",
  "PYTHONHTTPSVERIFY"
];

export function buildCodexChildEnv(sourceEnv) {
  const env = { ...sourceEnv };
  for (const key of PYTHON_TLS_ENV_KEYS) {
    delete env[key];
  }
  return env;
}

export function resolveNotebookLmWritableDir(sourceEnv) {
  const storagePath = String(sourceEnv.NOTEBOOKLM_STORAGE_PATH || "").trim();
  if (storagePath) {
    return path.dirname(path.resolve(storagePath));
  }

  const homeDir = String(sourceEnv.USERPROFILE || sourceEnv.HOME || "").trim();
  const profile = String(sourceEnv.NOTEBOOKLM_PROFILE || "default").trim();
  if (!homeDir || !/^[A-Za-z0-9._-]+$/.test(profile)) {
    return undefined;
  }

  return path.join(path.resolve(homeDir), ".notebooklm", "profiles", profile);
}

export function resolveCodexAdditionalWritableDirs(request, sourceEnv) {
  if (String(request?.agent_skill_hint || "").trim().toLowerCase() !== "notebooklm") {
    return [];
  }
  const writableDir = resolveNotebookLmWritableDir(sourceEnv);
  return writableDir ? [writableDir] : [];
}
