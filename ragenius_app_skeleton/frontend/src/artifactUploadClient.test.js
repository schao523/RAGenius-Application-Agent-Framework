import { describe, expect, it, vi } from "vitest";

import { createUploadOperationId, uploadArtifact } from "./artifactUploadClient";

class FakeXhr {
  static instances = [];
  upload = {};
  headers = {};
  status = 0;
  responseText = "";

  constructor() {
    FakeXhr.instances.push(this);
  }

  open(method, url) {
    this.method = method;
    this.url = url;
  }

  setRequestHeader(name, value) {
    this.headers[name] = value;
  }

  send(body) {
    this.body = body;
  }

  succeed(payload, status = 201) {
    this.status = status;
    this.responseText = JSON.stringify(payload);
    this.onload();
  }

  abort() {
    this.aborted = true;
    this.onabort?.();
  }
}

describe("artifact upload client", () => {
  it("creates an opaque stable operation id", () => {
    const randomUUID = vi.spyOn(crypto, "randomUUID").mockReturnValue("uuid-1");
    expect(createUploadOperationId()).toBe("upload_op_uuid-1");
    randomUUID.mockRestore();
  });

  it("posts the unified multipart request and reports byte progress", async () => {
    const previous = globalThis.XMLHttpRequest;
    globalThis.XMLHttpRequest = FakeXhr;
    const progress = vi.fn();
    const promise = uploadArtifact({
      baseUrl: "http://localhost:8000",
      sessionId: "session-1",
      appId: "app-1",
      userId: "user-1",
      file: new File(["notes"], "notes.txt", { type: "text/plain" }),
      operationId: "upload-op-1",
      analysisMode: "none",
      onProgress: progress,
    });
    const xhr = FakeXhr.instances.at(-1);
    xhr.upload.onprogress({ lengthComputable: true, loaded: 3, total: 5 });
    xhr.succeed({ status: "ready", artifact: { artifact_id: "artifact-1" } });

    await expect(promise).resolves.toMatchObject({ status: "ready" });
    expect(xhr.method).toBe("POST");
    expect(xhr.url).toContain("/sessions/session-1/artifacts/uploads");
    expect(progress).toHaveBeenCalledWith({ loaded: 3, total: 5, percent: 60 });
    globalThis.XMLHttpRequest = previous;
  });

  it("aborts the byte transfer when its signal is cancelled", async () => {
    const previous = globalThis.XMLHttpRequest;
    globalThis.XMLHttpRequest = FakeXhr;
    const controller = new AbortController();
    const promise = uploadArtifact({
      baseUrl: "http://localhost:8000", sessionId: "session-1",
      appId: "app-1", userId: "user-1", operationId: "upload-op-cancel",
      file: new File(["notes"], "notes.txt"), signal: controller.signal,
    });
    const xhr = FakeXhr.instances.at(-1);

    controller.abort();

    await expect(promise).rejects.toMatchObject({ name: "AbortError" });
    expect(xhr.aborted).toBe(true);
    globalThis.XMLHttpRequest = previous;
  });
});
