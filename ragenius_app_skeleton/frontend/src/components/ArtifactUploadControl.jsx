import { useRef, useState } from "react";

import { createUploadOperationId } from "../artifactUploadClient";

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} bytes`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ArtifactUploadControl({ onUpload, onReady, onStatusChange, disabled = false }) {
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState("idle");
  const [progress, setProgress] = useState(null);
  const operationId = useRef("");
  const abortController = useRef(null);
  const inputRef = useRef(null);

  const updateStatus = (nextStatus) => {
    setStatus(nextStatus);
    onStatusChange?.(nextStatus);
  };

  const run = async (selectedFile, reuseOperation = false) => {
    if (!selectedFile || !onUpload) return;
    if (!reuseOperation || !operationId.current) {
      operationId.current = createUploadOperationId();
    }
    updateStatus("uploading");
    setProgress(null);
    abortController.current = new AbortController();
    try {
      const result = await onUpload(
        selectedFile,
        operationId.current,
        (value) => {
          const percent = value?.percent ?? null;
          setProgress(percent);
          if (percent === 100) updateStatus("preparing");
        },
        abortController.current.signal,
      );
      if (result?.status === "failed" || !result?.artifact) {
        updateStatus("failed");
        return;
      }
      updateStatus("ready");
      onReady?.(result.artifact);
    } catch (error) {
      if (error?.name === "AbortError") {
        setFile(null);
        setProgress(null);
        operationId.current = "";
        updateStatus("cancelled");
        if (inputRef.current) inputRef.current.value = "";
        return;
      }
      updateStatus("failed");
    } finally {
      abortController.current = null;
    }
  };

  const removeLocalUpload = () => {
    setFile(null);
    setProgress(null);
    operationId.current = "";
    updateStatus("idle");
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div className="artifact-upload-control">
      <label>
        <span>Upload artifact</span>
        <input
          ref={inputRef}
          aria-label="Upload artifact"
          type="file"
          disabled={disabled || status === "uploading" || status === "preparing"}
          onChange={(event) => {
            const selected = event.target.files?.[0] || null;
            setFile(selected);
            void run(selected);
          }}
        />
      </label>
      {file && <div>{file.name} | {file.type || "application/octet-stream"} | {formatBytes(file.size)}</div>}
      <div aria-live="polite">
        {status === "uploading" && (progress == null ? "Uploading" : `Uploading ${progress}%`)}
        {status === "preparing" && "Preparing artifact"}
        {status === "ready" && "Ready"}
        {status === "failed" && "Upload failed. Retry this file."}
        {status === "cancelled" && "Upload cancelled."}
      </div>
      {status === "uploading" && (
        <button type="button" onClick={() => abortController.current?.abort()}>Cancel upload</button>
      )}
      {status === "failed" && (
        <button type="button" onClick={() => void run(file, true)}>Retry upload</button>
      )}
      {file && status !== "uploading" && status !== "preparing" && (
        <button type="button" onClick={removeLocalUpload}>Remove upload</button>
      )}
    </div>
  );
}
