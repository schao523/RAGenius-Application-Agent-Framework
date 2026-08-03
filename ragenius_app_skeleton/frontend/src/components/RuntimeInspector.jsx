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

function formatTokenCount(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString("en-US") : "Unavailable";
}

function formatSaving(accounting) {
  const tokens = formatTokenCount(accounting.turn_estimated_tokens_saved);
  const percent = Number(accounting.turn_estimated_saving_percent);
  return `${tokens} tokens${Number.isFinite(percent) ? ` (${percent.toLocaleString("en-US")}%)` : ""}`;
}

function taskLabel(task) {
  const labels = {
    planner: "Planning",
    planner_hybrid: "Hybrid planning",
    evidence_analysis: "Evidence analysis",
    answer_generation: "Answer generation",
    safe_answer: "Safe answer generation",
  };
  return labels[task] || String(task || "DeepSeek call");
}

function resolveMessageWorkflowStatus(message) {
  const storedStatus =
    message?.workflowStatus && typeof message.workflowStatus === "object"
      ? message.workflowStatus
      : {};
  if (Object.keys(storedStatus).length > 0) {
    return storedStatus;
  }

  const progress =
    message?.workflowProgress && typeof message.workflowProgress === "object"
      ? message.workflowProgress
      : {};
  const executionState =
    message?.sessionExecutionState && typeof message.sessionExecutionState === "object"
      ? message.sessionExecutionState
      : {};
  const workflowTitle = progress.workflow_title || executionState.primary_scope_title || null;
  const currentStepTitle = progress.step_title || executionState.active_step_title || null;
  const currentStepOrder = progress.step_order ?? executionState.active_step_order ?? null;
  if (!workflowTitle && !currentStepTitle && currentStepOrder === null) {
    return {};
  }
  return {
    workflow_id: progress.workflow_id || null,
    workflow_title: workflowTitle,
    current_step:
      currentStepTitle || currentStepOrder !== null
        ? { order: currentStepOrder, title: currentStepTitle }
        : null,
  };
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

  const storedRetrievalSummary = message?.retrievalSummary || {};
  const fallbackTaskModelDiagnostics =
    message?.taskModelDiagnostics || message?.task_model_diagnostics || {};
  const retrievalSummary =
    (!storedRetrievalSummary.task_model_diagnostics
      || Object.keys(storedRetrievalSummary.task_model_diagnostics).length === 0)
    && fallbackTaskModelDiagnostics
    && typeof fallbackTaskModelDiagnostics === "object"
    && Object.keys(fallbackTaskModelDiagnostics).length > 0
      ? { ...storedRetrievalSummary, task_model_diagnostics: fallbackTaskModelDiagnostics }
      : storedRetrievalSummary;
  const citations = Array.isArray(message?.citations) ? message.citations : [];
  const turnExecutionPlan = message?.turnExecutionPlan || retrievalSummary.turn_execution_plan || {};
  const resourceRequests = Array.isArray(turnExecutionPlan.resource_requests) ? turnExecutionPlan.resource_requests : [];
  const actions = Array.isArray(turnExecutionPlan.actions) ? turnExecutionPlan.actions : [];
  const messageWorkflowStatus = resolveMessageWorkflowStatus(message);
  const selectedWorkflowStatus =
    Object.keys(messageWorkflowStatus).length > 0 ? messageWorkflowStatus : (workflowStatus || {});
  const taskModelDiagnostics =
    retrievalSummary.task_model_diagnostics && typeof retrievalSummary.task_model_diagnostics === "object"
      ? retrievalSummary.task_model_diagnostics
      : {};
  const contextOptimization =
    taskModelDiagnostics.context_optimization && typeof taskModelDiagnostics.context_optimization === "object"
      ? taskModelDiagnostics.context_optimization
      : {};
  const tokenAccounting =
    taskModelDiagnostics.turn_token_accounting && typeof taskModelDiagnostics.turn_token_accounting === "object"
      ? taskModelDiagnostics.turn_token_accounting
      : {};
  const tokenCalls = Array.isArray(tokenAccounting.calls)
    ? tokenAccounting.calls
    : (Array.isArray(contextOptimization.calls) ? contextOptimization.calls : []);
  const hasTokenDiagnostics =
    Object.keys(contextOptimization).length > 0 || Object.keys(tokenAccounting).length > 0;
  const optimizationMode = String(contextOptimization.mode || "off").toLowerCase();
  const optimizationEligible = contextOptimization.eligible !== false;

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
      <div style={styles.inspectorGroup}>
        <div style={styles.inspectorGroupTitle}>Token Optimization</div>
        <div style={styles.inspectorKeyValue}>
          {!hasTokenDiagnostics && (
            <div>Token optimization diagnostics were not recorded for this turn.</div>
          )}
          {hasTokenDiagnostics && (
            <>
            <div><strong>Mode:</strong> {optimizationMode.charAt(0).toUpperCase() + optimizationMode.slice(1)}</div>
            <div><strong>DeepSeek calls:</strong> {tokenAccounting.call_count ?? tokenCalls.length}</div>
            {!optimizationEligible && <div>This turn was not eligible for context optimization.</div>}
            {optimizationEligible && optimizationMode === "diagnostic" && (
              <>
                <div><strong>Actually sent:</strong> {formatTokenCount(tokenAccounting.turn_estimated_outbound_tokens)} tokens</div>
                <div><strong>Compact candidate:</strong> {formatTokenCount(tokenAccounting.turn_compact_candidate_tokens)} tokens</div>
                <div><strong>Potential saving:</strong> {formatSaving(tokenAccounting)}</div>
              </>
            )}
            {optimizationEligible && optimizationMode === "compact" && (
              <>
                <div><strong>Estimated outbound:</strong> {formatTokenCount(tokenAccounting.turn_estimated_outbound_tokens)} tokens</div>
                <div><strong>Estimated saved:</strong> {formatSaving(tokenAccounting)}</div>
              </>
            )}
            {optimizationEligible && optimizationMode === "off" && (
              <div>Context optimization was disabled for this turn.</div>
            )}
            {tokenAccounting.budget_limit_tokens != null && (
              <div>
                <strong>Turn budget:</strong> {formatTokenCount(tokenAccounting.budget_limit_tokens)} tokens
                {tokenAccounting.budget_exceeded ? " (exceeded)" : ""}
              </div>
            )}
            </>
          )}
        </div>
        {tokenCalls.length > 0 && (
          <details style={{ marginTop: 10 }}>
            <summary>Call breakdown</summary>
            <ul style={styles.sourceList}>
              {tokenCalls.map((call, index) => (
                <li key={`${call.task || "call"}-${index}`}>
                  <strong>{taskLabel(call.task)}</strong>
                  <div>
                    Sent {formatTokenCount(call.actual_outbound_tokens)} tokens
                    {call.estimated_tokens_saved != null
                      ? ` | Candidate saving ${formatTokenCount(call.estimated_tokens_saved)} tokens`
                      : ""}
                  </div>
                </li>
              ))}
            </ul>
          </details>
        )}
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
          {selectedWorkflowStatus?.workflow_title && (
            <div><strong>Workflow:</strong> {selectedWorkflowStatus.workflow_title}</div>
          )}
          {selectedWorkflowStatus?.current_step?.title && (
            <div><strong>Current step:</strong> {selectedWorkflowStatus.current_step.title}</div>
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
