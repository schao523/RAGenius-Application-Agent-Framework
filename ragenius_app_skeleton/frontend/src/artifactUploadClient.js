export function createUploadOperationId() {
  const value = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `upload_op_${value}`;
}

function parseResponse(xhr) {
  let payload;
  try {
    payload = JSON.parse(xhr.responseText || "{}");
  } catch {
    throw new Error("Execution storage returned an invalid response.");
  }
  if (xhr.status < 200 || xhr.status >= 300) {
    const error = new Error("Execution storage is unavailable. Retry this upload.");
    error.code = payload?.detail?.code || payload?.error?.code || "ARTIFACT_UPLOAD_FAILED";
    throw error;
  }
  return payload;
}

export function uploadArtifact({
  baseUrl, sessionId, appId, userId, file, operationId,
  analysisMode = "none", onProgress, signal,
}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append("app_id", appId);
    form.append("user_id", userId);
    form.append("upload_operation_id", operationId);
    form.append("analysis_mode", analysisMode);
    form.append("file", file);
    xhr.open("POST", `${String(baseUrl || "").replace(/\/$/, "")}/sessions/${encodeURIComponent(sessionId)}/artifacts/uploads`);
    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable || !onProgress) return;
      onProgress({
        loaded: event.loaded,
        total: event.total,
        percent: Math.round((event.loaded / event.total) * 100),
      });
    };
    const abort = () => xhr.abort();
    if (signal?.aborted) {
      reject(Object.assign(new Error("Upload cancelled."), { name: "AbortError" }));
      return;
    }
    signal?.addEventListener("abort", abort, { once: true });
    xhr.onerror = () => reject(new Error("Execution storage is unavailable. Retry this upload."));
    xhr.onabort = () => reject(Object.assign(new Error("Upload cancelled."), { name: "AbortError" }));
    xhr.onload = () => {
      signal?.removeEventListener("abort", abort);
      try {
        resolve(parseResponse(xhr));
      } catch (error) {
        reject(error);
      }
    };
    xhr.send(form);
  });
}

export async function retryArtifactUpload({ baseUrl, sessionId, appId, userId, operationId }) {
  const response = await fetch(
    `${String(baseUrl || "").replace(/\/$/, "")}/sessions/${encodeURIComponent(sessionId)}/artifacts/uploads/${encodeURIComponent(operationId)}/retry?app_id=${encodeURIComponent(appId)}&user_id=${encodeURIComponent(userId)}`,
    { method: "POST" },
  );
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error("Execution storage is unavailable. Retry this upload.");
  }
  return payload;
}
