import { useRef, useState } from "react";

import { createUploadOperationId } from "../artifactUploadClient";

export default function ArtifactUploadControl({ onUpload, onReady, disabled = false }) {
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState("idle");
  const [progress, setProgress] = useState(null);
  const operationId = useRef("");

  const run = async (selectedFile, reuseOperation = false) => {
    if (!selectedFile || !onUpload) return;
    if (!reuseOperation || !operationId.current) {
      operationId.current = createUploadOperationId();
    }
    setStatus("uploading");
    setProgress(null);
    try {
      const result = await onUpload(selectedFile, operationId.current, (value) => {
        setProgress(value?.percent ?? null);
      });
      if (result?.status === "failed" || !result?.artifact) {
        setStatus("failed");
        return;
      }
      setStatus("ready");
      onReady?.(result.artifact);
    } catch {
      setStatus("failed");
    }
  };

  return (
    <div className="artifact-upload-control">
      <label>
        <span>Upload artifact</span>
        <input
          aria-label="Upload artifact"
          type="file"
          disabled={disabled || status === "uploading"}
          onChange={(event) => {
            const selected = event.target.files?.[0] || null;
            setFile(selected);
            void run(selected);
          }}
        />
      </label>
      {file && <div>{file.name} | {file.type || "application/octet-stream"} | {file.size} bytes</div>}
      <div aria-live="polite">
        {status === "uploading" && (progress == null ? "Uploading" : `Uploading ${progress}%`)}
        {status === "ready" && "Ready"}
        {status === "failed" && "Upload failed. Retry this file."}
      </div>
      {status === "failed" && (
        <button type="button" onClick={() => void run(file, true)}>Retry upload</button>
      )}
    </div>
  );
}
