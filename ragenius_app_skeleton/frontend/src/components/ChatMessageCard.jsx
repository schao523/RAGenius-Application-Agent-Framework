import React from "react";

function resolveRouteHref(baseUrl, routePath) {
  const normalizedBaseUrl = String(baseUrl || "").trim();
  const normalizedRoutePath = String(routePath || "").trim();
  if (!normalizedBaseUrl || !normalizedRoutePath) {
    return "";
  }
  try {
    return new URL(normalizedRoutePath, normalizedBaseUrl).toString();
  } catch {
    return "";
  }
}

function normalizeExecutionArtifacts(message) {
  const retrievalSummary =
    message?.retrievalSummary && typeof message.retrievalSummary === "object"
      ? message.retrievalSummary
      : {};
  const executionResult =
    retrievalSummary.execution_submit_result?.result
    && typeof retrievalSummary.execution_submit_result.result === "object"
      ? retrievalSummary.execution_submit_result.result
      : retrievalSummary.execution_status_result?.result
      && typeof retrievalSummary.execution_status_result.result === "object"
        ? retrievalSummary.execution_status_result.result
        : {};
  const normalized = [];
  const rawArtifacts = Array.isArray(executionResult.artifacts) ? executionResult.artifacts : [];
  for (const item of rawArtifacts) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const artifactId = String(item.artifact_id || "").trim();
    const displayName = String(item.display_name || item.name || artifactId || "Artifact").trim();
    if (!artifactId && !displayName) {
      continue;
    }
    normalized.push({
      artifact_id: artifactId,
      artifact_type: String(item.artifact_type || "").trim(),
      display_name: displayName,
      summary: String(item.summary || "").trim(),
      open_url: String(item.open_url || "").trim(),
      preview_url: String(item.preview_url || "").trim(),
      routes:
        item?.routes && typeof item.routes === "object"
          ? {
              open: String(item.routes.open || "").trim(),
              preview: String(item.routes.preview || "").trim(),
            }
          : { open: "", preview: "" },
      capabilities:
        item?.capabilities && typeof item.capabilities === "object"
          ? {
              can_open: item.capabilities.can_open !== false,
              can_preview: item.capabilities.can_preview === true,
              can_reuse: item.capabilities.can_reuse !== false,
            }
          : {
              can_open: Boolean(
                item.open_url
                || item?.routes?.open
              ),
              can_preview: false,
              can_reuse: Boolean(artifactId),
            },
      created_at: String(item.created_at || "").trim(),
      mime_type: String(item.mime_type || "").trim(),
      status: String(item.status || "").trim(),
      reviewed: item.reviewed === true,
    });
  }

  if (normalized.length === 0 && retrievalSummary.artifact_export) {
    const exportArtifact =
      retrievalSummary.export_artifact && typeof retrievalSummary.export_artifact === "object"
        ? retrievalSummary.export_artifact
        : {};
    const artifactId = String(
      exportArtifact.artifact_id || executionResult.artifact_id || ""
    ).trim();
    const displayName = String(
      exportArtifact.display_name || exportArtifact.name || "Export"
    ).trim();
    normalized.push({
      artifact_id: artifactId,
      artifact_type: String(exportArtifact.artifact_type || executionResult.artifact_type || "chat_export").trim(),
      display_name: displayName,
      summary: String(exportArtifact.summary || "").trim(),
      open_url: String(exportArtifact.open_url || "").trim(),
      preview_url: String(exportArtifact.preview_url || "").trim(),
      routes:
        exportArtifact?.routes && typeof exportArtifact.routes === "object"
          ? {
              open: String(exportArtifact.routes.open || "").trim(),
              preview: String(exportArtifact.routes.preview || "").trim(),
            }
          : { open: "", preview: "" },
      capabilities:
        exportArtifact?.capabilities && typeof exportArtifact.capabilities === "object"
          ? {
              can_open: exportArtifact.capabilities.can_open !== false,
              can_preview: exportArtifact.capabilities.can_preview === true,
              can_reuse: exportArtifact.capabilities.can_reuse !== false,
            }
          : {
              can_open: true,
              can_preview: false,
              can_reuse: true,
            },
      created_at: "",
      mime_type: "",
      status: "ready",
      reviewed: exportArtifact.reviewed === true,
    });
  }

  if (normalized.length === 0 && retrievalSummary.reviewed_artifact) {
    const reviewedArtifact =
      retrievalSummary.reviewed_artifact && typeof retrievalSummary.reviewed_artifact === "object"
        ? retrievalSummary.reviewed_artifact
        : {};
    const artifactId = String(reviewedArtifact.artifact_id || "").trim();
    const displayName = String(
      reviewedArtifact.display_name || reviewedArtifact.name || artifactId || "Reviewed chat artifact"
    ).trim();
    normalized.push({
      artifact_id: artifactId,
      artifact_type: String(reviewedArtifact.artifact_type || "chat_export").trim(),
      display_name: displayName,
      summary: String(reviewedArtifact.summary || "Reviewed chat content saved for reuse.").trim(),
      open_url: String(reviewedArtifact.open_url || "").trim(),
      preview_url: String(reviewedArtifact.preview_url || "").trim(),
      routes:
        reviewedArtifact?.routes && typeof reviewedArtifact.routes === "object"
          ? {
              open: String(reviewedArtifact.routes.open || "").trim(),
              preview: String(reviewedArtifact.routes.preview || "").trim(),
            }
          : { open: "", preview: "" },
      capabilities:
        reviewedArtifact?.capabilities && typeof reviewedArtifact.capabilities === "object"
          ? {
              can_open: reviewedArtifact.capabilities.can_open !== false,
              can_preview: reviewedArtifact.capabilities.can_preview === true,
              can_reuse: reviewedArtifact.capabilities.can_reuse !== false,
            }
          : {
              can_open: true,
              can_preview: false,
              can_reuse: true,
            },
      created_at: String(reviewedArtifact.created_at || "").trim(),
      mime_type: String(reviewedArtifact.mime_type || "").trim(),
      status: String(reviewedArtifact.status || "ready").trim(),
      reviewed: reviewedArtifact.reviewed === true,
    });
  }

  return normalized;
}

function resolveAgentReuseContext(message) {
  const retrievalSummary =
    message?.retrievalSummary && typeof message.retrievalSummary === "object"
      ? message.retrievalSummary
      : {};
  const command = String(retrievalSummary.command || "").trim().toLowerCase();
  const targetId = String(retrievalSummary.target_id || "").trim();
  if (command !== "openclaw" && command !== "codex" && targetId !== "openclaw_cli" && targetId !== "codex_cli") {
    return {};
  }
  return {
    commandKind: "agent",
    agentBackend: targetId === "openclaw_cli" || command === "openclaw" ? "openclaw_cli" : "codex_cli",
  };
}

export default function ChatMessageCard({
  message,
  index,
  styles,
  assistantType,
  turnIntentLabel,
  generationSummary,
  primaryScopeSummary,
  sourceSummary,
  retrievalBypassSummary,
  evidenceNote,
  executionResultPreview,
  onOpenInspector,
  onOpenSources,
  onApproveMessage,
  selectable,
  selectedForExport,
  onToggleSelectedForExport,
  onRefreshExecutionStatus,
  onRetryExecution,
  onConfirmExecution,
  confirmingExecution,
  onLoginNotebookLm,
  loggingInToNotebookLm,
  baseUrl,
  onUseArtifactInComposer,
  onViewArtifactLibrary,
}) {
  const isAssistant = message.role === "assistant";
  const isExecutionTurn = Boolean(message?.retrievalSummary?.execution_override);
  const isApprovalTurn = Boolean(message?.retrievalSummary?.approval_event);
  const exportSelectable = Boolean(selectable && onToggleSelectedForExport);
  const executionArtifacts = normalizeExecutionArtifacts(message);
  const showExportSelectionAction = exportSelectable && (!isExecutionTurn || executionArtifacts.length === 0);
  const agentReuseContext = resolveAgentReuseContext(message);
  const assistantTypeLabel =
    assistantType && typeof assistantType === "object" ? assistantType.label : assistantType;
  const assistantTypeStyle =
    assistantType && typeof assistantType === "object" && assistantType.style
      ? assistantType.style
      : styles.pill;
  const evidenceNoteText =
    evidenceNote && typeof evidenceNote === "object" ? evidenceNote.text : evidenceNote;
  const evidenceNoteStyle =
    evidenceNote && typeof evidenceNote === "object" && evidenceNote.style
      ? evidenceNote.style
      : styles.compactNote;
  const inspectorLabel = isExecutionTurn
    ? "Execution Details"
    : isApprovalTurn
      ? "View Revision"
      : "Inspect";
  const showSourcesAction = !isExecutionTurn && !isApprovalTurn;
  const baseCardStyle = styles.messageCard(message.role, selectedForExport);
  const cardStyle = {
    ...baseCardStyle,
    cursor: exportSelectable ? "pointer" : baseCardStyle.cursor,
  };
  const toggleExportSelection = () => {
    if (!exportSelectable) {
      return;
    }
    onToggleSelectedForExport(message.id);
  };
  const executionPayload =
    message?.retrievalSummary?.execution_submit_result && typeof message.retrievalSummary.execution_submit_result === "object"
      ? message.retrievalSummary.execution_submit_result
      : message?.retrievalSummary?.execution_status_result && typeof message.retrievalSummary.execution_status_result === "object"
        ? message.retrievalSummary.execution_status_result
        : {};
  const pendingConfirmation = String(executionPayload?.status || executionPayload?.state || "").trim().toLowerCase() === "pending_confirmation";
  const handleCardClick = (event) => {
    if (!exportSelectable) {
      return;
    }
    if (event.target instanceof Element && event.target.closest("button, a, input, textarea, select, summary")) {
      return;
    }
    toggleExportSelection();
  };

  return (
    <div
      style={cardStyle}
      onClick={handleCardClick}
      title={exportSelectable ? "Click to select this message for reuse." : undefined}
    >
      <div style={styles.assistantMetaRow}>
        <span style={styles.messageRoleLabel}>{isAssistant ? "Assistant" : "You"}</span>
        {isAssistant && assistantTypeLabel && <span style={assistantTypeStyle}>{assistantTypeLabel}</span>}
        {isAssistant && turnIntentLabel && <span style={styles.pill}>Intent: {turnIntentLabel}</span>}
        {isAssistant && generationSummary && <span style={styles.pill}>{generationSummary}</span>}
        {isAssistant && primaryScopeSummary && <span style={styles.pill}>Scope: {primaryScopeSummary}</span>}
        {isAssistant && sourceSummary && <span style={styles.pill}>{sourceSummary}</span>}
        {isAssistant && retrievalBypassSummary && <span style={{ ...styles.pill, ...styles.statusWarn }}>{retrievalBypassSummary}</span>}
        {showExportSelectionAction && selectedForExport && <span style={{ ...styles.pill, ...styles.statusOk }}>Selected for reuse</span>}
      </div>
      <div style={styles.messageBodyText}>{message.content}</div>
      {isAssistant && (
        <>
          {executionResultPreview && <div style={styles.compactNote}>{executionResultPreview}</div>}
          {evidenceNoteText && <div style={evidenceNoteStyle}>{evidenceNoteText}</div>}
          {executionArtifacts.length > 0 && (
            <div style={{ ...styles.compactNote, display: "grid", gap: 8 }}>
              {executionArtifacts.map((artifact, artifactIndex) => {
                const routeHref = resolveRouteHref(baseUrl, artifact.routes?.open || artifact.open_url);
                const previewHref = resolveRouteHref(baseUrl, artifact.routes?.preview || artifact.preview_url);
                const primaryHref = routeHref;
                const openLabel = "Open Saved File";
                const canReuseArtifact = artifact.capabilities?.can_reuse !== false && artifact.artifact_id;
                const canPreviewArtifact = artifact.capabilities?.can_preview === true && previewHref;
                return (
                  <div
                    key={`${artifact.artifact_id || artifact.display_name || "artifact"}-${artifactIndex}`}
                    style={{
                      border: "1px solid #bfdbfe",
                      borderRadius: 12,
                      padding: 10,
                      background: "#eff6ff",
                    }}
                  >
                    <div style={{ fontWeight: 600, color: "#0f172a" }}>
                      {artifact.display_name || artifact.artifact_id || "Artifact"}
                    </div>
                    <div style={{ fontSize: 12, color: "#475569" }}>
                      {[artifact.artifact_type, artifact.mime_type].filter(Boolean).join(" | ")}
                      {artifact.reviewed ? " | Reviewed" : ""}
                    </div>
                    {artifact.summary && (
                      <div style={{ marginTop: 4, fontSize: 13, color: "#1e293b" }}>{artifact.summary}</div>
                    )}
                    {(primaryHref || canPreviewArtifact || canReuseArtifact || onViewArtifactLibrary) && (
                      <div style={{ ...styles.actionRow, marginTop: 8 }}>
                        {canReuseArtifact && onUseArtifactInComposer && (
                          <button
                            type="button"
                            style={styles.inlineActionButton}
                            onClick={() => onUseArtifactInComposer(artifact, agentReuseContext)}
                          >
                            Reuse In Composer
                          </button>
                        )}
                        {onViewArtifactLibrary && (
                          <button
                            type="button"
                            style={styles.inlineActionButton}
                            onClick={onViewArtifactLibrary}
                          >
                            View In Artifact Library
                          </button>
                        )}
                        {canPreviewArtifact && (
                          <a
                            href={previewHref}
                            style={styles.inlineActionButton}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Preview
                          </a>
                        )}
                        {primaryHref && (
                          <a
                            href={primaryHref}
                            style={styles.inlineActionButton}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {openLabel}
                          </a>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          <div style={styles.actionRow}>
            {showExportSelectionAction && (
              <button type="button" style={styles.inlineActionButton} onClick={toggleExportSelection}>
                {selectedForExport ? "Unselect Reuse" : "Select for Reuse"}
              </button>
            )}
            {!isExecutionTurn && !isApprovalTurn && onApproveMessage && (
              <button type="button" style={styles.inlineActionButton} onClick={() => onApproveMessage(index)}>
                Mark Reviewed
              </button>
            )}
            <button type="button" style={styles.inlineActionButton} onClick={() => onOpenInspector(index)}>
              {inspectorLabel}
            </button>
            {isExecutionTurn ? (
              <>
                {onRefreshExecutionStatus && (
                  <button type="button" style={styles.inlineActionButton} onClick={() => onRefreshExecutionStatus(message)}>
                    Refresh Status
                  </button>
                )}
                {pendingConfirmation && onConfirmExecution && (
                  <button
                    type="button"
                    style={styles.inlineActionButton}
                    onClick={() => onConfirmExecution(message)}
                    disabled={confirmingExecution}
                  >
                    {confirmingExecution ? "Confirming..." : "Confirm"}
                  </button>
                )}
                {onRetryExecution && (
                  <button type="button" style={styles.inlineActionButton} onClick={() => onRetryExecution(message)}>
                    Retry
                  </button>
                )}
                {message?.retrievalSummary?.login_required && onLoginNotebookLm && (
                  <button
                    type="button"
                    style={styles.inlineActionButton}
                    onClick={() => onLoginNotebookLm(message)}
                    disabled={loggingInToNotebookLm}
                  >
                    {loggingInToNotebookLm ? "Launching Login..." : "Login to NotebookLM"}
                  </button>
                )}
              </>
            ) : showSourcesAction ? (
              <button type="button" style={styles.inlineActionButton} onClick={() => onOpenSources(index)}>
                Sources
              </button>
            ) : null}
          </div>
        </>
      )}
      {!isAssistant && exportSelectable && (
        <div style={styles.actionRow}>
          <button type="button" style={styles.inlineActionButton} onClick={toggleExportSelection}>
            {selectedForExport ? "Unselect Reuse" : "Select for Reuse"}
          </button>
        </div>
      )}
    </div>
  );
}
