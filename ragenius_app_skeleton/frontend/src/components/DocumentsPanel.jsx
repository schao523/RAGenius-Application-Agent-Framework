import React, { useState } from "react";

export default function DocumentsPanel({
  baseUrl,
  builderBaseUrl,
  builderAvailable,
  appId,
  onDocumentsLoaded,
  styles,
  fetchJson,
  formatStatusPill,
}) {
  const [documents, setDocuments] = useState([]);
  const [runId, setRunId] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [activeDocId, setActiveDocId] = useState("");

  const loadDocuments = async () => {
    if (!appId) return;
    setError("");
    try {
      const data = await fetchJson(`${baseUrl}/apps/${appId}/documents`, {
        headers: { "x-role": "admin" },
      });
      const nextDocs = data.documents || [];
      setDocuments(nextDocs);
      onDocumentsLoaded(nextDocs);
    } catch (e) {
      setError(String(e.message || e));
    }
  };

  const ingest = async () => {
    if (!appId) return;
    setLoading(true);
    setError("");
    try {
      const data = await fetchJson(`${baseUrl}/apps/${appId}/documents/ingest`, {
        method: "POST",
        headers: { "x-role": "admin", "Content-Type": "application/json" },
        body: JSON.stringify({ document_ids: documents.filter((doc) => doc.file_path).map((doc) => doc.id) }),
      });
      setRunId(data.run_id || "");
      setStatus(data.status || "");
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setLoading(false);
    }
  };

  const ingestDocument = async (docId) => {
    if (!appId || !docId) return;
    setActiveDocId(docId);
    setError("");
    try {
      const data = await fetchJson(`${baseUrl}/apps/${appId}/documents/ingest`, {
        method: "POST",
        headers: { "x-role": "admin", "Content-Type": "application/json" },
        body: JSON.stringify({ document_ids: [docId] }),
      });
      setRunId(data.run_id || "");
      setStatus(data.status || "");
      await loadDocuments();
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setActiveDocId("");
    }
  };

  const refresh = async () => {
    if (!runId || !appId) return;
    setError("");
    try {
      const data = await fetchJson(`${baseUrl}/apps/${appId}/ingestion_runs/${runId}`, {
        headers: { "x-role": "admin" },
      });
      setStatus(data.status || "");
      await loadDocuments();
    } catch (e) {
      setError(String(e.message || e));
    }
  };

  return (
    <section style={styles.card}>
      <h2 style={styles.sectionTitle}>Documents</h2>
      <p style={styles.muted}>
        Builder owns upload storage. This tab shows the runtime view of those documents and
        their ingestion state inside `rag_subsystem`.
      </p>
      <div style={styles.row}>
        <button style={styles.button} onClick={loadDocuments} disabled={!appId}>Load Documents</button>
        <button style={styles.secondaryButton} onClick={ingest} disabled={loading || documents.length === 0 || !appId}>
          {loading ? "Starting..." : "Ingest Builder Docs"}
        </button>
        <button style={styles.secondaryButton} onClick={refresh} disabled={!runId}>Refresh Progress</button>
        {appId && (
          builderAvailable ? (
            <a
              href={`${builderBaseUrl.replace(/\/$/, "")}/apps/${appId}/upload`}
              target="_blank"
              rel="noreferrer"
              style={styles.linkButton}
            >
              Manage In Builder
            </a>
          ) : (
            <span style={styles.disabledLinkButton}>Builder offline</span>
          )
        )}
      </div>
      {runId && (
        <div style={{ ...styles.row, marginTop: 14 }}>
          <span style={styles.pill}>Run ID: {runId}</span>
          {status && <span style={formatStatusPill(status).style}>{formatStatusPill(status).label}</span>}
        </div>
      )}
      <div style={styles.tableLike}>
        {documents.map((doc) => {
          const pill = formatStatusPill(doc.status);
          return (
            <div key={doc.id} style={styles.docRow}>
              <div>
                <div style={{ fontWeight: 800 }}>{doc.filename}</div>
                <div style={styles.small}>{doc.id}</div>
              </div>
              <div>
                <div style={styles.small}>Status</div>
                <span style={pill.style}>{pill.label}</span>
              </div>
              <div>
                <div style={styles.small}>Language</div>
                <div>{doc.language || "n/a"}</div>
              </div>
              <div>
                <div style={styles.small}>Uploaded</div>
                <div>{doc.uploaded_at || "n/a"}</div>
                {doc.error_message && <div style={styles.docError}>{doc.error_message}</div>}
              </div>
              <div>
                <div style={styles.small}>Actions</div>
                <div style={styles.row}>
                  <button
                    style={styles.tinyButton}
                    onClick={() => ingestDocument(doc.id)}
                    disabled={!doc.file_path || activeDocId === doc.id}
                  >
                    {activeDocId === doc.id ? "Starting..." : (doc.status === "ready" ? "Reingest" : "Ingest")}
                  </button>
                  {builderAvailable ? (
                    <a
                      href={`${builderBaseUrl.replace(/\/$/, "")}/apps/${appId}/docs/${doc.id}`}
                      target="_blank"
                      rel="noreferrer"
                      style={{ ...styles.tinyButton, textDecoration: "none", display: "inline-flex", alignItems: "center" }}
                    >
                      Open in Builder
                    </a>
                  ) : (
                    <span style={styles.disabledTinyButton}>Builder offline</span>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {documents.length === 0 && <div style={styles.note}>No document list loaded yet.</div>}
      {error && <div style={styles.error}>{error}</div>}
    </section>
  );
}
