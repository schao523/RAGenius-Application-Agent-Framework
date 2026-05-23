import React from "react";

function renderNamedList(title, items) {
  if (!Array.isArray(items) || items.length === 0) {
    return null;
  }
  return (
    <div style={{ marginTop: 8 }}>
      <strong>{title}:</strong> {items.join(", ")}
    </div>
  );
}

export default function RuntimeInspector({
  open,
  tab,
  onChangeTab,
  onClose,
  message,
  workflowStatus,
  styles,
  humanizeActionType,
  humanizePresentationMode,
  summarizePrimaryScope,
}) {
  if (!open) {
    return null;
  }

  const retrievalSummary = message?.retrievalSummary || {};
  const citations = Array.isArray(message?.citations) ? message.citations : [];
  const turnExecutionPlan = message?.turnExecutionPlan || retrievalSummary.turn_execution_plan || {};
  const resourceRequests = Array.isArray(turnExecutionPlan.resource_requests) ? turnExecutionPlan.resource_requests : [];
  const actions = Array.isArray(turnExecutionPlan.actions) ? turnExecutionPlan.actions : [];

  const detailsTab = (
    <div style={styles.inspectorSection}>
      <div style={styles.inspectorGroup}>
        <div style={styles.inspectorGroupTitle}>Turn summary</div>
        <div style={styles.inspectorKeyValue}>
          <div><strong>Intent:</strong> {humanizeActionType(retrievalSummary.turn_intent)}</div>
          <div><strong>Generation:</strong> {retrievalSummary.is_generation_request ? (retrievalSummary.generation_subtype || "yes") : "no"}</div>
          <div><strong>Out of scope:</strong> {retrievalSummary.is_out_of_scope ? "yes" : "no"}</div>
          <div><strong>Scope:</strong> {summarizePrimaryScope(retrievalSummary)}</div>
          <div><strong>Presentation:</strong> {humanizePresentationMode(retrievalSummary.presentation_mode)}</div>
          <div><strong>Answer source:</strong> {humanizeActionType(retrievalSummary.answer_source)}</div>
          <div><strong>Primary action:</strong> {humanizeActionType(retrievalSummary.primary_action_type || retrievalSummary.action_type)}</div>
          <div><strong>Retrieval bypassed:</strong> {retrievalSummary.retrieval_bypassed ? (retrievalSummary.retrieval_bypass_reason || "yes") : "no"}</div>
        </div>
      </div>
      {actions.length > 0 && (
        <div style={styles.inspectorGroup}>
          <div style={styles.inspectorGroupTitle}>Execution actions</div>
          <ul style={styles.sourceList}>
            {actions.map((action, index) => (
              <li key={`${action.action_id || action.action_type || "action"}-${index}`}>
                <strong>{humanizeActionType(action.action_type || "unknown")}</strong>
                <div>
                  {action.target || action.output_key || action.visibility || "No action details"}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
      {resourceRequests.length > 0 && (
        <div style={styles.inspectorGroup}>
          <div style={styles.inspectorGroupTitle}>Resource requests</div>
          <ul style={styles.sourceList}>
            {resourceRequests.map((request, index) => (
              <li key={`${request.resource_id || request.filename || "request"}-${index}`}>
                <strong>{request.filename || request.resource_id || "Unnamed resource"}</strong>
                <div>
                  {request.purpose || request.resource_role || "No purpose"}
                  {request.load_strategy_hint ? ` | ${request.load_strategy_hint}` : ""}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );

  const sourcesTab = (
    <div style={styles.inspectorSection}>
      <div style={styles.inspectorGroup}>
        <div style={styles.inspectorGroupTitle}>Citations</div>
        {citations.length > 0 ? (
          <ul style={styles.sourceList}>
            {citations.map((citation, index) => (
              <li key={`${citation.title || "citation"}-${index}`}>
                <strong>{citation.title || "Reference"}</strong>
                <div>{citation.snippet || "No snippet"}</div>
              </li>
            ))}
          </ul>
        ) : (
          <div>No grounded citations on this turn.</div>
        )}
      </div>
      <div style={styles.inspectorGroup}>
        <div style={styles.inspectorGroupTitle}>Loaded sources</div>
        {renderNamedList("Instruction", retrievalSummary.instruction_titles)}
        {renderNamedList("Knowledge", retrievalSummary.knowledge_titles)}
        {renderNamedList("Template", retrievalSummary.template_titles)}
        {renderNamedList("Uploads", retrievalSummary.session_upload_titles)}
      </div>
    </div>
  );

  const stateTab = (
    <div style={styles.inspectorSection}>
      <div style={styles.inspectorGroup}>
        <div style={styles.inspectorGroupTitle}>Workflow state</div>
        <div style={styles.inspectorKeyValue}>
          {workflowStatus?.workflow_title && (
            <div><strong>Workflow:</strong> {workflowStatus.workflow_title}</div>
          )}
          {workflowStatus?.current_step?.title && (
            <div><strong>Current step:</strong> {workflowStatus.current_step.title}</div>
          )}
          {message?.sessionExecutionState?.execution_status && (
            <div><strong>Execution status:</strong> {humanizeActionType(message.sessionExecutionState.execution_status)}</div>
          )}
        </div>
      </div>
      <div style={styles.inspectorGroup}>
        <div style={styles.inspectorGroupTitle}>Execution artifacts</div>
        <div style={styles.inspectorKeyValue}>
          <div><strong>Visible outputs:</strong> {retrievalSummary.visible_output_count ?? 0}</div>
          <div><strong>Hidden outputs:</strong> {retrievalSummary.hidden_output_count ?? 0}</div>
          <div><strong>Artifacts:</strong> {retrievalSummary.execution_artifact_count ?? 0}</div>
          <div><strong>Tool results:</strong> {retrievalSummary.tool_result_count ?? 0}</div>
          {renderNamedList("Output targets", retrievalSummary.output_artifact_targets)}
          {renderNamedList("Visible outputs", Array.isArray(retrievalSummary.visible_outputs) ? retrievalSummary.visible_outputs.map((item) => item.output_id || item.output_type || "output") : [])}
        </div>
      </div>
    </div>
  );

  const rawTab = (
    <div style={{ ...styles.debugCode, maxHeight: 520 }}>
      {JSON.stringify(retrievalSummary, null, 2)}
    </div>
  );

  return (
    <aside style={styles.inspectorPane}>
      <section style={styles.card}>
        <div style={styles.inspectorHeader}>
          <div>
            <h3 style={{ margin: 0, fontSize: 18, color: "#0f172a" }}>Inspect Turn</h3>
            <div style={styles.small}>Runtime and source details for the selected assistant turn.</div>
          </div>
          <button style={styles.secondaryButton} onClick={onClose}>Close</button>
        </div>
        <div style={{ ...styles.inspectorTabRow, marginTop: 14 }}>
          {["details", "sources", "state", "raw"].map((item) => (
            <button key={item} style={styles.inspectorTab(tab === item)} onClick={() => onChangeTab(item)}>
              {humanizeActionType(item)}
            </button>
          ))}
        </div>
        <div style={{ marginTop: 14 }}>
          {tab === "details" && detailsTab}
          {tab === "sources" && sourcesTab}
          {tab === "state" && stateTab}
          {tab === "raw" && rawTab}
        </div>
      </section>
    </aside>
  );
}
