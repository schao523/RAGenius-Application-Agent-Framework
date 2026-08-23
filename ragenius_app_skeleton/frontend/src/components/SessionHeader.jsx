import React from "react";

export default function SessionHeader({
  appName,
  phaseLabel,
  workflowStatus,
  styles,
  loading,
  appId,
  onAdvanceWorkflow,
  onOpenInspector,
  hasAssistantTurn,
}) {
  return (
    <div role="group" aria-label="Session context" style={styles.sessionHeaderGroup}>
      <div style={styles.sessionHeader}>
        <div>
          <div style={styles.sessionHeaderTitle}>{appName || "Chat"}</div>
          <div style={styles.sessionHeaderMeta}>
            {phaseLabel || "Conversation active"}
            {workflowStatus?.workflow_title ? ` | ${workflowStatus.workflow_title}` : ""}
          </div>
        </div>
        <div style={styles.row}>
          {workflowStatus?.next_step && onAdvanceWorkflow && (
            <button
              style={styles.secondaryButton}
              onClick={onAdvanceWorkflow}
              disabled={loading || !appId}
            >
              Mark Step Complete
            </button>
          )}
          <button
            style={styles.secondaryButton}
            onClick={onOpenInspector}
            disabled={!hasAssistantTurn}
          >
            Inspect Latest Turn
          </button>
        </div>
      </div>
      {workflowStatus?.current_step && (
        <div style={styles.workflowStrip}>
          <span style={styles.workflowBadge("current")}>
            Current: {workflowStatus.current_step.title || `Step ${workflowStatus.current_step.order || "?"}`}
          </span>
          {workflowStatus?.next_step && (
            <span style={styles.workflowBadge("next")}>
              Next: {workflowStatus.next_step.title || `Step ${workflowStatus.next_step.order || "?"}`}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
