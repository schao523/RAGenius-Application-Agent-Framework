import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { afterEach, describe, it } from "node:test";

import { buildApp } from "../../src/app.js";
import { getEnv } from "../../src/config/env.js";
import { buildRuntimeConfig } from "../../src/config/runtime-config.js";

const apps: Array<ReturnType<typeof buildApp>> = [];
const roots = new Set<string>();
const boundary = "ragenius-fixed-boundary";

function sha256(content: Buffer): string {
  return `sha256:${createHash("sha256").update(content).digest("hex")}`;
}

function createApp(input: { scopes?: string[]; maxBytes?: number } = {}) {
  const root = path.resolve(".test_tmp", `artifact-import-route-${randomUUID()}`);
  roots.add(root);
  const runtimeConfig = buildRuntimeConfig(getEnv({
    ARTIFACT_STORAGE_ROOT: root,
    AGENT_INPUT_MAX_BYTES: String(input.maxBytes ?? 1024),
    RAGENIUS_EXECUTION_SERVICE_AUTH_REQUIRED: "true",
    RAGENIUS_EXECUTION_SERVICE_CREDENTIALS_JSON: JSON.stringify([{
      service_id: "ragenius_app",
      token: "test-token",
      scopes: input.scopes ?? ["artifacts:write"]
    }])
  }));
  const app = buildApp({}, runtimeConfig);
  apps.push(app);
  return app;
}

function multipartBody(input: {
  content?: Buffer;
  declaredSizeBytes?: number;
  declaredSha256?: string;
  omitField?: string;
  sourceUploadId?: string;
} = {}): Buffer {
  const content = input.content ?? Buffer.from("video-bytes");
  const fields: Record<string, string> = {
    app_id: "app_1",
    session_id: "session_1",
    source_upload_id: input.sourceUploadId ?? "upload_1",
    display_name: "video.mp4",
    mime_type: "video/mp4",
    declared_size_bytes: String(input.declaredSizeBytes ?? content.byteLength),
    declared_sha256: input.declaredSha256 ?? sha256(content)
  };
  if (input.omitField) {
    delete fields[input.omitField];
  }
  const chunks: Buffer[] = [];
  for (const [name, value] of Object.entries(fields)) {
    chunks.push(Buffer.from(
      `--${boundary}\r\nContent-Disposition: form-data; name="${name}"\r\n\r\n${value}\r\n`
    ));
  }
  chunks.push(Buffer.from(
    `--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="video.mp4"\r\nContent-Type: video/mp4\r\n\r\n`
  ));
  chunks.push(content);
  chunks.push(Buffer.from(`\r\n--${boundary}--\r\n`));
  return Buffer.concat(chunks);
}

async function inject(app: ReturnType<typeof buildApp>, body = multipartBody(), token = "test-token") {
  return app.inject({
    method: "POST",
    url: "/v1/artifact-imports/session-upload",
    headers: {
      ...(token ? { authorization: `Bearer ${token}` } : {}),
      "content-type": `multipart/form-data; boundary=${boundary}`
    },
    payload: body
  });
}

describe("session upload artifact import route", () => {
  afterEach(async () => {
    await Promise.all(apps.splice(0).map((app) => app.close()));
    await Promise.all([...roots].map(async (root) => {
      await fs.rm(root, { recursive: true, force: true });
      roots.delete(root);
    }));
  });

  it("requires a valid service credential", async () => {
    const response = await inject(createApp(), multipartBody(), "");
    assert.equal(response.statusCode, 401);
    assert.equal(response.json().error.code, "SERVICE_AUTH_REQUIRED");
  });

  it("requires the artifacts:write service scope", async () => {
    const response = await inject(createApp({ scopes: ["execution"] }));
    assert.equal(response.statusCode, 403);
    assert.equal(response.json().error.code, "SERVICE_SCOPE_REQUIRED");
  });

  it("rejects malformed multipart fields", async () => {
    const response = await inject(createApp(), multipartBody({ omitField: "declared_sha256" }));
    assert.equal(response.statusCode, 400);
    assert.equal(response.json().error.code, "INVALID_EXECUTION_INPUT_IMPORT");
  });

  it("rejects a file over the multipart limit", async () => {
    const response = await inject(
      createApp({ maxBytes: 5 }),
      multipartBody({
        content: Buffer.from("video-bytes"),
        declaredSizeBytes: 5,
        declaredSha256: sha256(Buffer.from("video"))
      })
    );
    assert.equal(response.statusCode, 413);
    assert.equal(response.json().error.code, "EXECUTION_INPUT_TOO_LARGE");
  });

  it("imports once and returns the same artifact for an exact retry", async () => {
    const app = createApp();
    const first = await inject(app);
    const second = await inject(app);

    assert.equal(first.statusCode, 201);
    assert.equal(second.statusCode, 200);
    const firstBody = first.json();
    const secondBody = second.json();
    assert.equal(firstBody.preparation_status, "ready");
    assert.equal(firstBody.reused_existing_artifact, false);
    assert.equal(firstBody.artifact.artifact_type, "session_upload");
    assert.equal(firstBody.artifact.display_name, "video.mp4");
    assert.equal(firstBody.artifact.path, undefined);
    assert.equal(firstBody.artifact.file_path, undefined);
    assert.equal(secondBody.reused_existing_artifact, true);
    assert.equal(secondBody.artifact.artifact_id, firstBody.artifact.artifact_id);
  });
});
