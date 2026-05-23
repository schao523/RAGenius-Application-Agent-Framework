import React, { useState } from "react";

export default function InstructionsPanel({ baseUrl, builderBaseUrl, builderAvailable, appId, styles, fetchJson }) {
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState("");
  const [understandingDetail, setUnderstandingDetail] = useState(null);
  const [understandingLoading, setUnderstandingLoading] = useState(false);
  const [understandingError, setUnderstandingError] = useState("");
  const [understandingAction, setUnderstandingAction] = useState("");
  const [showRawFindings, setShowRawFindings] = useState(false);

  const adminHeaders = { "x-role": "admin" };

  const loadInstructions = async () => {
    if (!appId) return;
    setError("");
    try {
      const data = await fetchJson(`${baseUrl}/apps/${appId}/instructions`, {
        headers: adminHeaders,
      });
      setPayload(data);
    } catch (e) {
      setError(String(e.message || e));
    }
  };

  const loadUnderstanding = async (endpoint = "", options = {}, actionLabel = "load") => {
    if (!appId) return null;
    setUnderstandingError("");
    setUnderstandingLoading(actionLabel === "load");
    setUnderstandingAction(actionLabel !== "load" ? actionLabel : "");
    try {
      const data = await fetchJson(`${baseUrl}/apps/${appId}/instruction-understanding${endpoint}`, {
        headers: adminHeaders,
        ...options,
      });
      setUnderstandingDetail(data);
      setShowRawFindings(false);
      return data;
    } catch (e) {
      setUnderstandingError(String(e.message || e));
      throw e;
    } finally {
      setUnderstandingLoading(false);
      setUnderstandingAction("");
    }
  };

  const previewStatus = payload?.instruction_understanding_preview || {};
  const detailStatus = understandingDetail?.status || {};
  const previewSemanticAttached = Boolean(payload?.instruction_understanding_preview?.semantic_compile_attached);
  const previewSemanticValid = Boolean(payload?.instruction_understanding_preview?.semantic_compile_valid);
  const detailSemanticAttached = Boolean(understandingDetail?.compiled?.metadata?.semantic_compile_attached);
  const detailSemanticValid = Boolean(understandingDetail?.compiled?.metadata?.semantic_compile_valid);
  const semanticCompileAttached = detailSemanticAttached || previewSemanticAttached;
  const semanticCompileValid = detailSemanticValid || previewSemanticValid;
  const compiledStatus = detailStatus.compiled_status || previewStatus.compiled_status;
  const reviewStatus = detailStatus.review_status || previewStatus.review_status;
  const cacheStatus = detailStatus.cache_status || understandingDetail?.cache_status || previewStatus.cache_status;
  const latestAttempt =
    understandingDetail?.latest_attempt && typeof understandingDetail.latest_attempt === "object"
      ? understandingDetail.latest_attempt
      : previewStatus.latest_attempt_id
        ? {
            id: previewStatus.latest_attempt_id,
            semantic_compile_valid: previewStatus.latest_attempt_semantic_compile_valid,
            validation_errors: Array.isArray(previewStatus.latest_attempt_validation_errors)
              ? previewStatus.latest_attempt_validation_errors
              : [],
          }
        : null;
  const latestAttemptSemanticValid =
    latestAttempt?.semantic_compile_valid ??
    latestAttempt?.metadata?.semantic_compile_valid ??
    null;
  const latestAttemptErrors = Array.isArray(latestAttempt?.validation_errors)
    ? latestAttempt.validation_errors
    : Array.isArray(
        latestAttempt?.compiled_contract?.semantic_compile?.validation?.errors,
      )
      ? latestAttempt.compiled_contract.semantic_compile.validation.errors
      : [];
  const reviewSummary = understandingDetail?.review?.review_summary_md || "";
  const reviewFindings = understandingDetail?.review?.review_findings;
  const defaultWorkflowId =
    understandingDetail?.compiled?.compiled_contract?.hybrid_instruction_runtime_model?.default_workflow_id || "";

  const renderStructuredValue = (value, path = "root") => {
    if (Array.isArray(value)) {
      return (
        <ul style={{ margin: "8px 0 0 18px" }}>
          {value.map((entry, index) => (
            <li key={`${path}-${index}`}>{renderStructuredValue(entry, `${path}-${index}`)}</li>
          ))}
        </ul>
      );
    }
    if (value && typeof value === "object") {
      return (
        <div>
          {Object.entries(value).map(([key, entry]) => (
            <div key={`${path}-${key}`} style={{ marginTop: 8 }}>
              <div style={styles.label}>{key}</div>
              {entry && typeof entry === "object" ? (
                <div style={{ marginTop: 4 }}>{renderStructuredValue(entry, `${path}-${key}`)}</div>
              ) : (
                <div>{String(entry)}</div>
              )}
            </div>
          ))}
        </div>
      );
    }
    return <span>{String(value)}</span>;
  };

  const shouldShowFindingsJsonFallback =
    reviewFindings &&
    typeof reviewFindings === "object" &&
    !Array.isArray(reviewFindings) &&
    Object.values(reviewFindings).some((entry) => entry && typeof entry === "object");

  return (
    <section style={styles.card}>
      <h2 style={styles.sectionTitle}>Instructions</h2>
      <p style={styles.muted}>
        Builder `instructions.md` is the canonical instruction source. This tab keeps it
        visible so you can compare what the runtime derives against what the application
        was authored to do.
      </p>
      <div style={styles.row}>
        <button style={styles.button} onClick={loadInstructions} disabled={!appId}>Load Instructions</button>
        <button
          style={styles.button}
          onClick={() => loadUnderstanding()}
          disabled={!appId || understandingLoading}
        >
          {understandingLoading ? "Loading Understanding..." : "Load Understanding"}
        </button>
        <button
          style={styles.button}
          onClick={() => loadUnderstanding("/recompile", { method: "POST" }, "recompile")}
          disabled={!appId || understandingLoading || Boolean(understandingAction)}
        >
          {understandingAction === "recompile" ? "Recompiling..." : "Recompile"}
        </button>
        <button
          style={styles.button}
          onClick={() => loadUnderstanding("/review", { method: "POST" }, "review")}
          disabled={!appId || understandingLoading || Boolean(understandingAction)}
        >
          {understandingAction === "review" ? "Running Review..." : "Run Review"}
        </button>
        {appId && (
          builderAvailable ? (
            <a
              href={`${builderBaseUrl.replace(/\/$/, "")}/apps/${appId}/config?tab=instructions`}
              target="_blank"
              rel="noreferrer"
              style={styles.linkButton}
            >
              Edit In Builder
            </a>
          ) : (
            <span style={styles.small}>Builder status: offline</span>
          )
        )}
      </div>
      {payload && (
        <>
          <div style={{ ...styles.row, marginTop: 14 }}>
            <span style={styles.pill}>Version: {payload.instructions?.version || "n/a"}</span>
            <span style={styles.pill}>Checksum: {(payload.instructions?.checksum || "").slice(0, 12) || "n/a"}</span>
          </div>
          <div style={{ marginTop: 16 }}>
            <div style={styles.label}>Instructions Markdown</div>
            <div style={styles.code}>{payload.instructions?.content || ""}</div>
          </div>
        </>
      )}
      {(compiledStatus || reviewStatus || cacheStatus) && (
        <div style={{ marginTop: 16 }}>
          <div style={styles.label}>Understanding Status</div>
          <div style={{ ...styles.row, marginTop: 8 }}>
            <span style={styles.pill}>Compiled: {compiledStatus || "n/a"}</span>
            <span style={styles.pill}>Review: {reviewStatus || "n/a"}</span>
            <span style={styles.pill}>Cache: {cacheStatus || "n/a"}</span>
            <span style={styles.pill}>Semantic Compile: {semanticCompileAttached ? "attached" : "not attached"}</span>
            <span style={styles.pill}>Semantic Valid: {semanticCompileValid ? "yes" : "no"}</span>
          </div>
          {defaultWorkflowId && (
            <div style={{ marginTop: 10 }}>
              <div style={styles.label}>Default Workflow</div>
              <div>{defaultWorkflowId}</div>
            </div>
          )}
          {latestAttempt && (
            <div style={{ marginTop: 12 }}>
              <div style={styles.label}>Latest Failed Attempt</div>
              <div style={{ marginTop: 8 }}>
                <span style={styles.pill}>Attempt: {latestAttempt.id || "n/a"}</span>
                <span style={styles.pill}>
                  Semantic Valid: {latestAttemptSemanticValid === false ? "no" : latestAttemptSemanticValid === true ? "yes" : "unknown"}
                </span>
              </div>
              {latestAttemptErrors.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <div style={styles.label}>Validation Errors</div>
                  <ul style={{ margin: "8px 0 0 18px" }}>
                    {latestAttemptErrors.map((entry, index) => (
                      <li key={`latest-attempt-error-${index}`}>{String(entry)}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}
      {understandingDetail && (
        <div style={{ marginTop: 16 }}>
          <div style={styles.label}>Instruction Understanding</div>
          {reviewSummary ? (
            <div style={{ marginTop: 8 }}>
              <div style={styles.label}>Review Summary</div>
              <div style={styles.code}>{reviewSummary}</div>
            </div>
          ) : (
            <div style={{ marginTop: 8 }}>No review has been run yet.</div>
          )}
          <div style={{ marginTop: 12 }}>
            <div style={styles.label}>Review Findings</div>
            {reviewFindings ? (
              <div style={{ marginTop: 8 }}>
                {renderStructuredValue(reviewFindings)}
                {shouldShowFindingsJsonFallback && (
                  <div style={{ marginTop: 10 }}>
                    <button
                      type="button"
                      style={styles.button}
                      onClick={() => setShowRawFindings((current) => !current)}
                    >
                      {showRawFindings ? "Hide Raw Findings JSON" : "Show Raw Findings JSON"}
                    </button>
                    {showRawFindings && (
                      <pre style={{ ...styles.code, marginTop: 8 }}>{JSON.stringify(reviewFindings, null, 2)}</pre>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div style={{ marginTop: 8 }}>No findings available.</div>
            )}
          </div>
        </div>
      )}
      {error && <div style={styles.error}>{error}</div>}
      {understandingError && <div style={styles.error}>{understandingError}</div>}
    </section>
  );
}
