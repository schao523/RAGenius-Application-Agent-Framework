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
    <>
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
            Inspect
          </button>
        </div>
      </div>
      {workflowStatus?.current_step && (
        <div style={{ ...styles.note, marginBottom: 12 }}>
          <div>
            <strong>Current step:</strong> {workflowStatus.current_step.title || `Step ${workflowStatus.current_step.order || "?"}`}
          </div>
          {workflowStatus?.next_step && (
            <div style={{ marginTop: 8 }}>
              <strong>Next:</strong> {workflowStatus.next_step.title || `Step ${workflowStatus.next_step.order || "?"}`}
            </div>
          )}
        </div>
      )}
    </>
  );
}
