import React, { useState } from "react";

export default function RuntimePanel({ baseUrl, builderBaseUrl, builderAvailable, appId, styles, fetchJson }) {
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState("");

  const loadRuntime = async () => {
    if (!appId) return;
    setError("");
    try {
      const data = await fetchJson(`${baseUrl}/apps/${appId}/runtime`, {
        headers: { "x-role": "admin" },
      });
      setPayload(data);
    } catch (e) {
      setError(String(e.message || e));
    }
  };

  const preview = payload?.instruction_understanding_preview || {};
  const compiledId = preview.compiled_id;
  const compiledStatus = preview.compiled_status;
  const reviewId = preview.review_id;
  const reviewStatus = preview.review_status;
  const cacheStatus = preview.cache_status;
  const staleReasons = Array.isArray(preview.stale_reasons) ? preview.stale_reasons : [];

  return (
    <section style={styles.card}>
      <h2 style={styles.sectionTitle}>Runtime</h2>
      <p style={styles.muted}>
        This is the operational summary for the builder-backed runtime: which models are active,
        what domain adapter is in effect, and what structure was derived from builder settings.
      </p>
      <div style={styles.row}>
        <button style={styles.button} onClick={loadRuntime} disabled={!appId}>Load Runtime Summary</button>
        {appId && (
          builderAvailable ? (
            <a
              href={`${builderBaseUrl.replace(/\/$/, "")}/apps/${appId}/config?tab=settings`}
              target="_blank"
              rel="noreferrer"
              style={styles.linkButton}
            >
              Open Builder Settings
            </a>
          ) : (
            <span style={styles.disabledLinkButton}>Builder offline</span>
          )
        )}
      </div>
      {payload && (
        <>
          <div style={styles.metricGrid}>
            <div style={styles.metric}>
              <div style={styles.metricLabel}>Provider</div>
              <div style={{ ...styles.metricValue, fontSize: 20 }}>{payload.provider || "n/a"}</div>
            </div>
            <div style={styles.metric}>
              <div style={styles.metricLabel}>Domain</div>
              <div style={{ ...styles.metricValue, fontSize: 20 }}>{payload.domain || "n/a"}</div>
            </div>
            <div style={styles.metric}>
              <div style={styles.metricLabel}>Goals</div>
              <div style={styles.metricValue}>{payload.config_summary?.goal_count ?? 0}</div>
            </div>
            <div style={styles.metric}>
              <div style={styles.metricLabel}>Guardrails</div>
              <div style={styles.metricValue}>{payload.adapter_summary?.guardrail_count ?? 0}</div>
            </div>
          </div>
          <div style={{ marginTop: 16 }}>
            <div style={styles.label}>Task Models</div>
            <div style={styles.code}>{JSON.stringify(payload.models || {}, null, 2)}</div>
          </div>
          {(compiledStatus || reviewStatus || cacheStatus) && (
            <div style={{ marginTop: 16 }}>
              <div style={styles.label}>Instruction Understanding</div>
              <div style={{ ...styles.row, marginTop: 8 }}>
                <span style={styles.pill}>Compiled: {compiledStatus || "n/a"}</span>
                <span style={styles.pill}>Review: {reviewStatus || "n/a"}</span>
                <span style={styles.pill}>Cache: {cacheStatus || "n/a"}</span>
              </div>
              {(compiledId || reviewId || staleReasons.length > 0) && (
                <div style={{ marginTop: 10 }}>
                  {compiledId && <div>Compiled ID: {compiledId}</div>}
                  {reviewId && <div>Review ID: {reviewId}</div>}
                  {staleReasons.length > 0 && (
                    <div>Stale Reasons: {staleReasons.join(", ")}</div>
                  )}
                </div>
              )}
            </div>
          )}
        </>
      )}
      {error && <div style={styles.error}>{error}</div>}
    </section>
  );
}
