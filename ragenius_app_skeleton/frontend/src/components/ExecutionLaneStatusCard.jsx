import React from "react";

function resolveExecutionStatus(executionLaneState) {
  const latestResult = executionLaneState?.latest_execution_result;
  const latestStatus = executionLaneState?.latest_status_result;
  return (
    latestStatus?.status
    || latestResult?.status
    || latestResult?.state
    || ""
  );
}

function resolveLatestExecutionPayload(executionLaneState) {
  return executionLaneState?.latest_status_result || executionLaneState?.latest_execution_result || {};
}

function resolveExecutionPaths(executionPayload) {
  const metadataPaths = Array.isArray(executionPayload?.execution_metadata?.execution_paths)
    ? executionPayload.execution_metadata.execution_paths
    : [];
  if (metadataPaths.length > 0) {
    return [...new Set(metadataPaths.filter(Boolean))];
  }
  const provenancePaths = Array.isArray(executionPayload?.execution_provenance)
    ? executionPayload.execution_provenance
      .map((entry) => entry?.execution_path)
      .filter(Boolean)
    : [];
  return [...new Set(provenancePaths)];
}

function resolveFallbackSummary(executionPayload) {
  const metadata = executionPayload?.execution_metadata || {};
  const provenance = Array.isArray(executionPayload?.execution_provenance)
    ? executionPayload.execution_provenance
    : [];
  const fallbackEntries = provenance.filter((entry) => entry?.fallback_used || entry?.execution_path === "rest_fallback");
  const usedFallback = Boolean(metadata.used_fallback || fallbackEntries.length > 0);
  if (!usedFallback) {
    return "No";
  }

  const fallbackCount = Number.isInteger(metadata.fallback_count)
    ? metadata.fallback_count
    : fallbackEntries.length;
  const firstReason = fallbackEntries
    .map((entry) => entry?.fallback_reason)
    .find(Boolean);

  return firstReason
    ? `Yes (${fallbackCount}; ${firstReason})`
    : `Yes (${fallbackCount})`;
}

export default function ExecutionLaneStatusCard({
  selectedApprovedContent,
  sessionLaneState,
  onRefreshStatus,
  refreshing,
  onLoginNotebookLm,
  loggingInToNotebookLm,
  onRetryExecution,
  onOpenComposer,
  onOpenInspector,
  styles,
}) {
  const contentLane = sessionLaneState?.content_lane || {};
  const executionLane = sessionLaneState?.execution_lane || {};
  const latestExecutionId = executionLane.latest_execution_id || "";
  const latestSkillId = executionLane.latest_execution_request_skill_id || "";
  const latestExecutionMode = executionLane.latest_execution_mode || "";
  const latestExecutionRequestQuery = executionLane.latest_execution_request_query || "";
  const latestAsyncTaskId = executionLane.latest_async_task_id || "";
  const latestAsyncTaskStatus = executionLane.latest_async_task_status || "";
  const loginRequirement =
    executionLane.latest_login_requirement && typeof executionLane.latest_login_requirement === "object"
      ? executionLane.latest_login_requirement
      : null;
  const latestStatus = resolveExecutionStatus(executionLane);
  const latestExecutionPayload = resolveLatestExecutionPayload(executionLane);
  const executionPaths = resolveExecutionPaths(latestExecutionPayload);
  const executionPathLabel = executionPaths.length > 0 ? executionPaths.join(", ") : "Unknown";
  const fallbackSummary = resolveFallbackSummary(latestExecutionPayload);
  const approvedRevisionLabel =
    selectedApprovedContent?.revision_id
    || contentLane.latest_revision_id
    || selectedApprovedContent?.approved_content_id
    || contentLane.latest_approved_content_id
    || "";

  const hasExecutionState = Boolean(
    latestExecutionId
    || latestSkillId
    || latestStatus
    || approvedRevisionLabel
    || executionPaths.length > 0
    || latestExecutionMode
    || latestAsyncTaskId
  );

  return (
    <section style={styles.executionLaneShell}>
      <div style={styles.executionLaneHeader}>
        <div>
          <div style={styles.sidebarSectionTitle}>Execution Lane</div>
          <div style={styles.small}>
            {hasExecutionState
              ? "Selected approved revision and latest execution state"
              : "No execution activity yet."}
          </div>
        </div>
        {latestExecutionId && (
          <div style={styles.row}>
            {onOpenComposer && (
              <button
                style={styles.secondaryButton}
                onClick={onOpenComposer}
                type="button"
              >
                Open Composer
              </button>
            )}
            {onOpenInspector && (
              <button
                style={styles.secondaryButton}
                onClick={onOpenInspector}
                type="button"
              >
                Details
              </button>
            )}
            <button
              style={styles.secondaryButton}
              onClick={onRefreshStatus}
              disabled={refreshing}
            >
              {refreshing ? "Refreshing..." : "Refresh Execution Status"}
            </button>
            {loginRequirement?.auth_required && onLoginNotebookLm && (
              <button
                style={styles.secondaryButton}
                onClick={onLoginNotebookLm}
                disabled={loggingInToNotebookLm}
                type="button"
              >
                {loggingInToNotebookLm ? "Launching Login..." : "Login to NotebookLM"}
              </button>
            )}
            {latestExecutionRequestQuery && onRetryExecution && (
              <button
                style={styles.secondaryButton}
                onClick={onRetryExecution}
                type="button"
              >
                Retry Last @exec
              </button>
            )}
          </div>
        )}
      </div>
      {hasExecutionState ? (
        <>
          <div style={styles.row}>
            <span style={styles.pill}>Revision: {approvedRevisionLabel || "None"}</span>
            <span style={styles.pill}>Last exec: {latestSkillId || "None"}</span>
            <span style={styles.pill}>Status: {latestStatus || "Not submitted"}</span>
            {latestExecutionMode && <span style={styles.pill}>Mode: {latestExecutionMode}</span>}
            {latestExecutionMode === "async" && latestAsyncTaskStatus && (
              <span style={styles.pill}>Task: {latestAsyncTaskStatus}</span>
            )}
            {executionPathLabel !== "Unknown" && <span style={styles.pill}>Path: {executionPathLabel}</span>}
            {fallbackSummary !== "No" && <span style={{ ...styles.pill, ...styles.statusWarn }}>Fallback: {fallbackSummary}</span>}
          </div>
          {latestExecutionMode === "async" && (
            <div style={styles.compactNote}>
              This execution was submitted as a background provider job. The app request may complete before the provider task finishes.
            </div>
          )}
          {loginRequirement?.auth_required && (
            <div style={styles.compactNote}>
              NotebookLM login is required before retrying this execution. Run <code>{loginRequirement.login_command || "python -m notebooklm login"}</code> or use the login action above.
            </div>
          )}
        </>
      ) : (
        <div style={styles.compactNote}>
          Approve a revision, then use the execution composer or run `@exec tool ...` / `@exec skill ...` to start the execution lane.
        </div>
      )}
    </section>
  );
}
