import React from "react";

function renderKeyValue(title, value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  return (
    <div>
      <strong>{title}:</strong> {String(value)}
    </div>
  );
}

function resolveExecutionPayload(message, sessionLaneState) {
  const retrievalSummary = message?.retrievalSummary || {};
  const hasMessageScopedExecutionPayload =
    Boolean(retrievalSummary.execution_submit_result)
    || Boolean(retrievalSummary.execution_status_result);
  if (hasMessageScopedExecutionPayload) {
    return (
      retrievalSummary.execution_submit_result
      || retrievalSummary.execution_status_result
      || {}
    );
  }
  if (retrievalSummary.execution_override) {
    return {};
  }
  return (
    sessionLaneState?.execution_lane?.latest_status_result
    || sessionLaneState?.execution_lane?.latest_execution_result
    || {}
  );
}

function renderList(items, emptyText, styles, renderItem) {
  if (!Array.isArray(items) || items.length === 0) {
    return <div>{emptyText}</div>;
  }
  return <ul style={styles.sourceList}>{items.map(renderItem)}</ul>;
}

function normalizeExecutionArtifacts(executionPayload) {
  const result =
    executionPayload?.result && typeof executionPayload.result === "object"
      ? executionPayload.result
      : {};
  const items = Array.isArray(result.artifacts) ? result.artifacts : [];
  return items
    .filter((item) => item && typeof item === "object")
    .map((item) => ({
      artifact_id: String(item.artifact_id || "").trim(),
      artifact_type: String(item.artifact_type || "").trim(),
      display_name: String(item.display_name || item.name || item.artifact_id || "Artifact").trim(),
      summary: String(item.summary || "").trim(),
      path: String(item.path || "").trim(),
      file_path: String(item.file_path || "").trim(),
      created_at: String(item.created_at || "").trim(),
      mime_type: String(item.mime_type || "").trim(),
      status: String(item.status || "").trim(),
      consumption:
        item?.consumption && typeof item.consumption === "object"
          ? {
              default_mode: String(item.consumption.default_mode || "").trim(),
              supported_modes: Array.isArray(item.consumption.supported_modes)
                ? item.consumption.supported_modes.map((value) => String(value || "").trim()).filter(Boolean)
                : [],
            }
          : null,
      eligible_consumers: Array.isArray(item.eligible_consumers)
        ? item.eligible_consumers.map((value) => String(value || "").trim()).filter(Boolean)
        : [],
    }))
    .filter((item) => item.artifact_id || item.display_name);
}

function formatConsumptionMode(value) {
  return String(value || "").replace(/_/g, " ").trim();
}

function normalizeArtifactReuseSummary(mappedInput, executionArtifacts) {
  if (!mappedInput || typeof mappedInput !== "object") {
    return [];
  }
  const requestArtifactRefs = Array.isArray(mappedInput.artifactRefs) ? mappedInput.artifactRefs : [];
  const requestRows = requestArtifactRefs
    .filter((item) => item && typeof item === "object")
    .map((item) => ({
      field_name: String(item.field_name || "artifactIds").trim() || "artifactIds",
      artifact_id: String(item.artifact_id || "").trim(),
      display_name: String(item.display_name || item.artifact_id || "Artifact").trim(),
      resolved_mode: String(
        item?.consumption?.resolved_mode
          || item?.consumption?.default_mode
          || "",
      ).trim(),
    }))
    .filter((item) => item.artifact_id);
  if (requestRows.length > 0) {
    return requestRows;
  }
  const artifactsById = new Map(
    executionArtifacts
      .filter((item) => item?.artifact_id)
      .map((item) => [String(item.artifact_id).trim(), item]),
  );
  const rows = [];
  Object.entries(mappedInput).forEach(([fieldName, value]) => {
    if (fieldName === "artifactRefs" || fieldName === "artifact_reuse") {
      return;
    }
    if (Array.isArray(value)) {
      value
        .map((item) => String(item || "").trim())
        .filter(Boolean)
        .forEach((artifactId) => {
          const artifact = artifactsById.get(artifactId);
          if (!artifact) {
            return;
          }
          rows.push({
            field_name: fieldName,
            artifact_id: artifactId,
            display_name: artifact.display_name || artifactId,
            resolved_mode: artifact?.consumption?.default_mode || "",
          });
        });
      return;
    }
    const scalarValue = String(value || "").trim();
    if (!scalarValue) {
      return;
    }
    const artifact = artifactsById.get(scalarValue);
    if (!artifact) {
      return;
    }
    rows.push({
      field_name: fieldName,
      artifact_id: scalarValue,
      display_name: artifact.display_name || scalarValue,
      resolved_mode: artifact?.consumption?.default_mode || "",
    });
  });
  return rows;
}

export default function ExecutionInspector({
  open,
  tab,
  onChangeTab,
  onClose,
  message,
  sessionLaneState,
  styles,
}) {
  if (!open) {
    return null;
  }

  const retrievalSummary = message?.retrievalSummary || {};
  const executionLane = sessionLaneState?.execution_lane || {};
  const executionPayload = resolveExecutionPayload(message, sessionLaneState);
  const hasMessageScopedExecutionPayload = Boolean(
    retrievalSummary.execution_submit_result || retrievalSummary.execution_status_result,
  );
  const executionMetadata = executionPayload?.execution_metadata || {};
  const executionProvenance = Array.isArray(executionPayload?.execution_provenance)
    ? executionPayload.execution_provenance
    : [];
  const errors = Array.isArray(executionPayload?.errors)
    ? executionPayload.errors
    : executionPayload?.error
      ? [executionPayload.error]
      : [];
  const mappedInput = retrievalSummary.execution_intent?.mapped_input || {};
  const command = String(retrievalSummary.command || "").trim().toLowerCase();
  const isCodexAgent = command === "codex";
  const isOpenClawAgent = command === "openclaw" || String(retrievalSummary.agent_backend || "").trim() === "openclaw_cli";
  const isAgentExecution = isCodexAgent || isOpenClawAgent;
  const agentResult = executionPayload?.result && typeof executionPayload.result === "object"
    ? executionPayload.result
    : {};
  const providerMetadata =
    agentResult.provider_metadata && typeof agentResult.provider_metadata === "object"
      ? agentResult.provider_metadata
      : {};
  const verificationResults = Array.isArray(agentResult.verification_results)
    ? agentResult.verification_results
    : [];
  const stagedInputs = Array.isArray(agentResult.staged_inputs)
    ? agentResult.staged_inputs
    : [];
  const operationVerification = Array.isArray(agentResult.operation_verification)
    ? agentResult.operation_verification
    : [];
  const agentDiagnostics =
    agentResult.diagnostics && typeof agentResult.diagnostics === "object"
      ? agentResult.diagnostics
      : {};
  const executionArtifacts = normalizeExecutionArtifacts(executionPayload);
  const artifactReuseSummary = normalizeArtifactReuseSummary(mappedInput, executionArtifacts);
  const selectedExecutionId = String(
    executionPayload?.execution_id
      || (hasMessageScopedExecutionPayload ? "" : executionLane.latest_execution_id)
      || "",
  ).trim();
  const selectedProviderTaskId = String(
    executionPayload?.task_id
      || (hasMessageScopedExecutionPayload ? "" : executionLane.latest_async_task_id)
      || "",
  ).trim();
  const selectedProviderTaskStatus = String(
    executionPayload?.result?.status
      || executionPayload?.result?.state
      || executionPayload?.status
      || executionPayload?.state
      || (hasMessageScopedExecutionPayload ? "" : executionLane.latest_async_task_status)
      || "",
  ).trim();

  const summaryTab = (
    <div style={styles.inspectorSection}>
      <div style={styles.inspectorGroup}>
        <div style={styles.inspectorGroupTitle}>Execution summary</div>
        <div style={styles.inspectorKeyValue}>
          {renderKeyValue("Command", retrievalSummary.command)}
          {renderKeyValue("Target", retrievalSummary.target_id || retrievalSummary.skill_id)}
          {renderKeyValue("Skill hint", isCodexAgent ? retrievalSummary.agent_skill_hint : "")}
          {renderKeyValue("Execution ID", selectedExecutionId)}
          {renderKeyValue("Status", executionPayload.status || executionPayload.state)}
          {renderKeyValue("Approved Revision", retrievalSummary.approved_revision_id)}
          {renderKeyValue("Approved Content", retrievalSummary.approved_content_id)}
          {renderKeyValue("Provider Task ID", selectedProviderTaskId)}
          {renderKeyValue("Provider Task Status", selectedProviderTaskStatus)}
          {renderKeyValue("Policy class", agentResult.policy_class)}
          {renderKeyValue("Workspace access", agentResult.workspace_access)}
          {renderKeyValue("Network access", agentResult.network_access)}
        </div>
      </div>
      {isCodexAgent && (
        <>
          <div style={styles.inspectorGroup}>
            <div style={styles.inspectorGroupTitle}>Authorization and policy</div>
            <div style={styles.inspectorKeyValue}>
              {renderKeyValue("Confirmation state", providerMetadata.confirmation_state)}
              {renderKeyValue("Permission scope", providerMetadata.permission_scope)}
              {renderKeyValue(
                "Policy fingerprint",
                providerMetadata.policy_fingerprint
                  ? String(providerMetadata.policy_fingerprint).slice(0, 12)
                  : "",
              )}
            </div>
          </div>
          <div style={styles.inspectorGroup}>
            <div style={styles.inspectorGroupTitle}>Staged inputs</div>
            {renderList(
              stagedInputs,
              "No staged Codex inputs.",
              styles,
              (item, index) => (
                <li key={`${String(item?.artifact_id || "input")}-${index}`}>
                  <strong>{String(item?.artifact_id || "Artifact")}</strong>
                  <div>{[item?.role, item?.reuse_mode].filter(Boolean).join(" | ")}</div>
                  <div>{String(item?.workspace_relative_path || "Metadata only")}</div>
                  {item?.sha256 ? <div>{`SHA-256: ${String(item.sha256).slice(0, 12)}`}</div> : null}
                </li>
              ),
            )}
          </div>
          <div style={styles.inspectorGroup}>
            <div style={styles.inspectorGroupTitle}>Operation verification</div>
            {renderList(
              operationVerification,
              "No Codex operation evidence.",
              styles,
              (item, index) => (
                <li key={`${String(item?.operation_id || "operation")}-${index}`}>
                  <strong>{String(item?.operation_id || item?.operation || "Operation")}</strong>
                  <div>{[item?.status, item?.level].filter(Boolean).join(" | ")}</div>
                  {item?.external_id ? <div>{`External ID: ${String(item.external_id)}`}</div> : null}
                  {item?.evidence ? <div>{String(item.evidence)}</div> : null}
                </li>
              ),
            )}
          </div>
          <div style={styles.inspectorGroup}>
            <div style={styles.inspectorGroupTitle}>Codex diagnostics</div>
            <div style={styles.inspectorKeyValue}>
              {renderKeyValue("Turn status", providerMetadata.turn_status)}
              {renderKeyValue("Commands", providerMetadata.command_count)}
              {renderKeyValue("Successful commands", providerMetadata.successful_command_count)}
              {renderKeyValue("Final JSON", providerMetadata.final_json_status)}
              {renderKeyValue("Failure code", agentDiagnostics.failure_code)}
            </div>
          </div>
        </>
      )}
      {executionPayload?.logs_summary && (
        <div style={styles.inspectorGroup}>
          <div style={styles.inspectorGroupTitle}>Logs summary</div>
          <div>{executionPayload.logs_summary}</div>
        </div>
      )}
      {isOpenClawAgent && (
        <div style={styles.inspectorGroup}>
          <div style={styles.inspectorGroupTitle}>OpenClaw result</div>
          <div style={styles.inspectorKeyValue}>
            {renderKeyValue("Provider", providerMetadata.provider_name || "OpenClaw")}
            {renderKeyValue("Backend", agentResult.backend || retrievalSummary.agent_backend || retrievalSummary.target_id)}
            {renderKeyValue("Execution mode", providerMetadata.execution_mode)}
            {renderKeyValue("Summary", agentResult.summary)}
            {renderKeyValue("Verified outputs", `${providerMetadata.verified_output_count ?? 0} / ${providerMetadata.required_output_count ?? 0}`)}
            {renderKeyValue("Expected outputs", providerMetadata.expected_output_count)}
            {renderKeyValue("Output text", agentResult.output_text)}
          </div>
          {verificationResults.length > 0 ? (
            <ul style={styles.sourceList}>
              {verificationResults.map((item, index) => (
                <li key={`${item?.output_id || "openclaw-output"}-${index}`}>
                  <strong>{String(item?.output_id || "OpenClaw output")}</strong>
                  <div>{String(item?.workspace_relative_path || item?.workspace_absolute_path || "")}</div>
                  <div>{item?.verified ? "Verified" : item?.exists ? "Exists but not verified" : "Missing"}</div>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      )}
      {!isCodexAgent && (
        <div style={styles.inspectorGroup}>
          <div style={styles.inspectorGroupTitle}>Latest status</div>
          <div style={styles.inspectorKeyValue}>
            {renderKeyValue("Execution path", Array.isArray(executionMetadata.execution_paths) ? executionMetadata.execution_paths.join(", ") : "")}
            {renderKeyValue("Used fallback", executionMetadata.used_fallback ? "yes" : "no")}
            {renderKeyValue("Fallback count", executionMetadata.fallback_count)}
          </div>
        </div>
      )}
      {errors.length > 0 && (
        <div style={styles.inspectorGroup}>
          <div style={styles.inspectorGroupTitle}>Errors</div>
          <ul style={styles.sourceList}>
            {errors.map((item, index) => (
              <li key={`${item?.code || "error"}-${index}`}>
                <strong>{item?.code || "Execution Error"}</strong>
                <div>{item?.message || "No message provided."}</div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );

  const requestTab = (
    <div style={styles.inspectorSection}>
      <div style={styles.inspectorGroup}>
        <div style={styles.inspectorGroupTitle}>{isAgentExecution ? "Agent request" : "Execution request"}</div>
        {isAgentExecution ? (
          <div style={styles.inspectorKeyValue}>
            {renderKeyValue("Backend", retrievalSummary.agent_backend || retrievalSummary.target_id || (isCodexAgent ? "codex_cli" : "openclaw_cli"))}
            {renderKeyValue("Skill hint", isCodexAgent ? retrievalSummary.agent_skill_hint : "")}
            {renderKeyValue("Approved Revision", retrievalSummary.approved_revision_id)}
            {renderKeyValue("Approved Content", retrievalSummary.approved_content_id)}
            {renderKeyValue("Agent query", retrievalSummary.agent_query)}
          </div>
        ) : null}
        <div style={{ ...styles.debugCode, maxHeight: 420 }}>
          {JSON.stringify(
            isAgentExecution
              ? {
                  command: retrievalSummary.command,
                  target_id: retrievalSummary.target_id,
                  skill_id: retrievalSummary.skill_id,
                  agent_backend: retrievalSummary.agent_backend,
                  agent_query: retrievalSummary.agent_query,
                  agent_skill_hint: isCodexAgent ? retrievalSummary.agent_skill_hint : undefined,
                  approved_content_id: retrievalSummary.approved_content_id,
                  approved_revision_id: retrievalSummary.approved_revision_id,
                }
              : {
                  command: retrievalSummary.command,
                  target_id: retrievalSummary.target_id,
                  skill_id: retrievalSummary.skill_id,
                  approved_content_id: retrievalSummary.approved_content_id,
                  approved_revision_id: retrievalSummary.approved_revision_id,
                  mapped_input: mappedInput,
                },
            null,
            2,
          )}
        </div>
      </div>
      {artifactReuseSummary.length > 0 ? (
        <div style={styles.inspectorGroup}>
          <div style={styles.inspectorGroupTitle}>Submitted artifact inputs</div>
          <ul style={styles.sourceList}>
            {artifactReuseSummary.map((item, index) => (
              <li key={`${item.field_name}-${item.artifact_id}-${index}`}>
                <strong>{`${item.field_name} -> ${item.display_name}`}</strong>
                {item.resolved_mode ? (
                  <div>{`Resolved mode: ${formatConsumptionMode(item.resolved_mode)}`}</div>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );

  const provenanceTab = (
    <div style={styles.inspectorSection}>
      <div style={styles.inspectorGroup}>
        <div style={styles.inspectorGroupTitle}>Provenance</div>
        {renderList(
          executionProvenance,
          "No execution provenance recorded for this turn.",
          styles,
          (entry, index) => (
            <li key={`${entry?.tool_id || "tool"}-${index}`}>
              <strong>{entry?.tool_id || "Unknown tool"}</strong>
              <div>
                {entry?.execution_path || "unknown"}
                {entry?.provider_id ? ` | ${entry.provider_id}` : ""}
                {entry?.fallback_reason ? ` | ${entry.fallback_reason}` : ""}
              </div>
            </li>
          ),
        )}
      </div>
    </div>
  );

  const artifactsTab = (
    <div style={styles.inspectorSection}>
      <div style={styles.inspectorGroup}>
        <div style={styles.inspectorGroupTitle}>Produced artifacts</div>
        {renderList(
          executionArtifacts,
          "No artifacts reported for this turn.",
          styles,
          (item, index) => (
            <li key={`${String(item.artifact_id || item.display_name || "artifact")}-${index}`}>
              <strong>{String(item.display_name || item.artifact_id || "Artifact")}</strong>
              <div>{[item.artifact_type, item.mime_type].filter(Boolean).join(" | ")}</div>
              {item.consumption?.default_mode ? (
                <div>{`Default reuse mode: ${formatConsumptionMode(item.consumption.default_mode)}`}</div>
              ) : null}
              {item.consumption?.supported_modes?.length ? (
                <div>{`Supported reuse modes: ${item.consumption.supported_modes.map(formatConsumptionMode).join(", ")}`}</div>
              ) : null}
              {item.eligible_consumers.length ? (
                <div>{`Eligible consumers: ${item.eligible_consumers.join(", ")}`}</div>
              ) : null}
              {item.summary ? <div>{item.summary}</div> : null}
              {item.file_path ? <div>{item.file_path}</div> : item.path ? <div>{item.path}</div> : null}
            </li>
          ),
        )}
      </div>
    </div>
  );

  const agentSkillsTab = (
    <div style={styles.inspectorSection}>
      <div style={styles.inspectorGroup}>
        <div style={styles.inspectorGroupTitle}>Activated skills</div>
        {renderList(
          agentResult.activated_skills,
          "No activated skills reported for this turn.",
          styles,
          (item, index) => <li key={`${String(item)}-${index}`}>{String(item)}</li>,
        )}
      </div>
    </div>
  );

  const agentToolsTab = (
    <div style={styles.inspectorSection}>
      <div style={styles.inspectorGroup}>
        <div style={styles.inspectorGroupTitle}>Tool summary</div>
        {renderList(
          agentResult.tool_summary,
          "No tool summary reported for this turn.",
          styles,
          (item, index) => <li key={`${String(item)}-${index}`}>{String(item)}</li>,
        )}
      </div>
    </div>
  );

  const agentArtifactsTab = (
    <div style={styles.inspectorSection}>
      <div style={styles.inspectorGroup}>
        <div style={styles.inspectorGroupTitle}>Artifacts</div>
        {renderList(
          agentResult.artifacts,
          "No artifacts reported for this turn.",
          styles,
          (item, index) => (
            <li key={`${String(item?.artifact_id || item?.name || "artifact")}-${index}`}>
              <strong>{String(item?.name || item?.artifact_id || "Artifact")}</strong>
              <div>{[item?.artifact_type, item?.path].filter(Boolean).join(" | ")}</div>
            </li>
          ),
        )}
      </div>
    </div>
  );

  const rawTab = (
    <div style={{ ...styles.debugCode, maxHeight: 520 }}>
      {JSON.stringify(
        {
          retrievalSummary,
          executionLane,
          executionPayload,
        },
        null,
        2,
      )}
    </div>
  );

  const tabs = isCodexAgent
    ? ["summary", "request", "skills", "tools", "artifacts", "raw"]
    : ["summary", "request", "provenance", ...(executionArtifacts.length > 0 ? ["artifacts"] : []), "raw"];

  return (
    <aside style={styles.inspectorPane}>
      <section style={styles.card}>
        <div style={styles.inspectorHeader}>
          <div>
            <h3 style={{ margin: 0, fontSize: 18, color: "#0f172a" }}>Execution Details</h3>
            <div style={styles.small}>
              {isCodexAgent
                ? "Codex agent request, activated skills, tool summary, and artifacts for the selected turn."
                : "Execution-specific request, status, and provenance for the selected turn."}
            </div>
          </div>
          <button style={styles.secondaryButton} onClick={onClose}>Close</button>
        </div>
        <div style={{ ...styles.inspectorTabRow, marginTop: 14 }}>
          {tabs.map((item) => (
            <button key={item} style={styles.inspectorTab(tab === item)} onClick={() => onChangeTab(item)}>
              {item[0].toUpperCase() + item.slice(1)}
            </button>
          ))}
        </div>
        <div style={{ marginTop: 14 }}>
          {tab === "summary" && summaryTab}
          {tab === "request" && requestTab}
          {tab === "provenance" && provenanceTab}
          {tab === "skills" && agentSkillsTab}
          {tab === "tools" && agentToolsTab}
          {tab === "artifacts" && (isCodexAgent ? agentArtifactsTab : artifactsTab)}
          {tab === "raw" && rawTab}
        </div>
      </section>
    </aside>
  );
}
