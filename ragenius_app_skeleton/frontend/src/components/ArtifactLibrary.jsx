import React, { useMemo, useState } from "react";

function formatConsumptionMode(value) {
  return String(value || "").replace(/_/g, " ").trim();
}

function normalizeStringArray(values) {
  return Array.isArray(values) ? values.map((value) => String(value || "").trim()).filter(Boolean) : [];
}

function artifactSupportsConsumptionMode(artifact, requiredMode) {
  const normalizedRequiredMode = String(requiredMode || "").trim();
  if (!normalizedRequiredMode) {
    return true;
  }
  const defaultMode = String(artifact?.consumption?.default_mode || "").trim();
  const supportedModes = normalizeStringArray(artifact?.consumption?.supported_modes);
  if (defaultMode === normalizedRequiredMode) {
    return true;
  }
  return supportedModes.includes(normalizedRequiredMode);
}

function evaluateArtifactCompatibility(artifact, picker) {
  if (!picker || typeof picker !== "object" || picker.enabled !== true) {
    return false;
  }
  const artifactType = String(artifact?.artifact_type || "").trim();
  const mimeType = String(artifact?.mime_type || "").trim();
  const acceptedTypes = normalizeStringArray(
    picker.accepted_artifact_types?.length ? picker.accepted_artifact_types : picker.allowed_artifact_types,
  );
  const acceptedMimeTypes = normalizeStringArray(picker.allowed_mime_types);
  const requiredConsumptionMode = String(picker.required_consumption_mode || "").trim();
  if (acceptedTypes.length > 0 && !acceptedTypes.includes(artifactType)) {
    return false;
  }
  if (acceptedMimeTypes.length > 0 && mimeType && !acceptedMimeTypes.includes(mimeType)) {
    return false;
  }
  return artifactSupportsConsumptionMode(artifact, requiredConsumptionMode);
}

function formatArtifactDate(value) {
  const normalized = String(value || "").trim();
  if (!normalized) {
    return "";
  }
  const parsed = new Date(normalized);
  if (Number.isNaN(parsed.getTime())) {
    return normalized;
  }
  return parsed.toLocaleString();
}

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

function normalizeArtifacts(items) {
  return [...(Array.isArray(items) ? items : [])]
    .filter((item) => item && item.artifact_id)
    .map((item) => ({
      ...item,
      artifact_id: String(item.artifact_id || "").trim(),
      session_id: String(item.session_id || "").trim(),
      app_id: String(item.app_id || "").trim(),
      artifact_type: String(item.artifact_type || "").trim(),
      artifact_type_label: String(item.artifact_type_label || item.artifact_type || "Artifact").trim(),
      display_name: String(item.display_name || item.artifact_id || "Artifact").trim(),
      summary: String(item.summary || "").trim(),
      preview_url: String(item.preview_url || "").trim(),
      open_url: String(item.open_url || "").trim(),
      file_path: String(item.file_path || "").trim(),
      path: String(item.path || "").trim(),
      mime_type: String(item.mime_type || "").trim(),
      created_at: String(item.created_at || "").trim(),
      reviewed: item.reviewed === true || item?.metadata?.reviewed === true,
      reviewed_at: String(item.reviewed_at || item?.metadata?.reviewed_at || "").trim(),
      reviewed_by: String(item.reviewed_by || item?.metadata?.reviewed_by || "").trim(),
      routes:
        item?.routes && typeof item.routes === "object"
          ? {
              open: String(item.routes.open || "").trim(),
              preview: String(item.routes.preview || "").trim(),
              delete: String(item.routes.delete || "").trim(),
            }
          : { open: "", preview: "", delete: "" },
      capabilities:
        item?.capabilities && typeof item.capabilities === "object"
          ? {
              can_open: item.capabilities.can_open === true,
              can_preview: item.capabilities.can_preview === true,
              can_delete: item.capabilities.can_delete !== false,
              can_reuse: item.capabilities.can_reuse !== false,
            }
          : {
              can_open: Boolean(item.open_url),
              can_preview: Boolean(item.preview_url),
              can_delete: true,
              can_reuse: true,
            },
      file_info:
        item?.file_info && typeof item.file_info === "object"
          ? {
              has_file: item.file_info.has_file === true,
              extension: String(item.file_info.extension || "").trim(),
              size_bytes: typeof item.file_info.size_bytes === "number" ? item.file_info.size_bytes : null,
            }
          : {
              has_file: Boolean(item.file_path),
              extension: "",
              size_bytes: null,
            },
      provenance:
        item?.provenance && typeof item.provenance === "object"
          ? {
              source_kind: String(item.provenance.source_kind || "").trim(),
              source_label: String(item.provenance.source_label || "").trim(),
              source_session_id: String(item.provenance.source_session_id || "").trim(),
              source_message_id: String(item.provenance.source_message_id || "").trim(),
              source_execution_id: String(item.provenance.source_execution_id || "").trim(),
            }
          : null,
      debug:
        item?.debug && typeof item.debug === "object"
          ? {
              artifact_id: String(item.debug.artifact_id || item.artifact_id || "").trim(),
              file_path: String(item.debug.file_path || "").trim(),
              metadata_path: String(item.debug.metadata_path || "").trim(),
            }
          : {
              artifact_id: String(item.artifact_id || "").trim(),
              file_path: String(item.file_path || "").trim(),
              metadata_path: String(item.path || "").trim(),
            },
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
    }));
}

export default function ArtifactLibrary({
  artifacts,
  toolInventory,
  loading = false,
  error = "",
  onUseInNextStep,
  onDeleteArtifact,
  baseUrl,
  onClose,
  styles,
}) {
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [selectedArtifactId, setSelectedArtifactId] = useState("");
  const [pendingDeleteArtifactId, setPendingDeleteArtifactId] = useState("");
  const [deletingArtifactId, setDeletingArtifactId] = useState("");
  const [actionErrorByArtifactId, setActionErrorByArtifactId] = useState({});
  const normalizedArtifacts = useMemo(() => normalizeArtifacts(artifacts), [artifacts]);
  const artifactTypes = useMemo(
    () => normalizedArtifacts
      .reduce((acc, item) => {
        if (!item.artifact_type) {
          return acc;
        }
        if (!acc.some((entry) => entry.value === item.artifact_type)) {
          acc.push({
            value: item.artifact_type,
            label: item.artifact_type_label || item.artifact_type,
          });
        }
        return acc;
      }, [])
      .sort((left, right) => left.label.localeCompare(right.label)),
    [normalizedArtifacts],
  );
  const filteredArtifacts = useMemo(() => {
    const loweredQuery = String(query || "").trim().toLowerCase();
    return normalizedArtifacts.filter((artifact) => {
      if (typeFilter && artifact.artifact_type !== typeFilter) {
        return false;
      }
      if (!loweredQuery) {
        return true;
      }
      return [
        artifact.display_name,
        artifact.summary,
        artifact.artifact_type,
        artifact.artifact_type_label,
        artifact.mime_type,
        artifact.provenance?.source_label || "",
      ]
        .join(" ")
        .toLowerCase()
        .includes(loweredQuery);
    });
  }, [normalizedArtifacts, query, typeFilter]);
  const selectedArtifact = filteredArtifacts.find((item) => item.artifact_id === selectedArtifactId)
    || normalizedArtifacts.find((item) => item.artifact_id === selectedArtifactId)
    || null;

  const clearArtifactActionError = (artifactId) => {
    const normalizedArtifactId = String(artifactId || "").trim();
    if (!normalizedArtifactId) {
      return;
    }
    setActionErrorByArtifactId((prev) => {
      if (!prev[normalizedArtifactId]) {
        return prev;
      }
      const next = { ...prev };
      delete next[normalizedArtifactId];
      return next;
    });
  };

  const confirmDeleteArtifact = async (artifact) => {
    const artifactId = String(artifact?.artifact_id || "").trim();
    if (!artifactId || typeof onDeleteArtifact !== "function") {
      return;
    }
    clearArtifactActionError(artifactId);
    setDeletingArtifactId(artifactId);
    try {
      await onDeleteArtifact(artifact);
      setPendingDeleteArtifactId((current) => (current === artifactId ? "" : current));
      setSelectedArtifactId((current) => (current === artifactId ? "" : current));
    } catch (error) {
      const message = String(error?.message || error || "Unable to delete the artifact.");
      setActionErrorByArtifactId((prev) => ({ ...prev, [artifactId]: message }));
    } finally {
      setDeletingArtifactId("");
    }
  };

  return (
    <section style={styles.card}>
      <div style={styles.executionLaneHeader}>
        <div>
          <h3 style={styles.sectionTitle}>Artifact Library</h3>
          <div style={styles.small}>
            Reusable artifacts for this session. Use them in the next execution step instead of copying ids manually.
          </div>
        </div>
        <div style={styles.actionRow}>
          <div style={styles.small}>{`${filteredArtifacts.length} item${filteredArtifacts.length === 1 ? "" : "s"}`}</div>
          {onClose ? (
            <button
              type="button"
              style={styles.secondaryButton}
              onClick={onClose}
            >
              Close
            </button>
          ) : null}
        </div>
      </div>

      <div style={{ ...styles.formGrid, marginTop: 12 }}>
        <label>
          <div style={styles.label}>Search</div>
          <input
            aria-label="Artifact Search"
            style={styles.input}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search artifacts"
          />
        </label>
        <label>
          <div style={styles.label}>Type</div>
          <select
            aria-label="Artifact Type Filter"
            style={styles.select}
            value={typeFilter}
            onChange={(event) => setTypeFilter(event.target.value)}
          >
            <option value="">All types</option>
            {artifactTypes.map((artifactType) => (
              <option key={artifactType.value} value={artifactType.value}>
                {artifactType.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading ? (
        <div style={{ ...styles.compactNote, marginTop: 12 }}>
          Loading session artifacts...
        </div>
      ) : error ? (
        <div style={{ ...styles.compactNote, marginTop: 12, color: "#b91c1c" }}>
          {`Unable to load artifacts: ${error}`}
        </div>
      ) : filteredArtifacts.length === 0 ? (
        <div style={{ ...styles.compactNote, marginTop: 12 }}>
          {normalizedArtifacts.length === 0
            ? "No artifacts have been saved in this session yet."
            : "No artifacts match the current filters."}
        </div>
      ) : (
        <div style={{ display: "grid", gap: 10, marginTop: 14 }}>
              {filteredArtifacts.map((artifact) => {
            const isSelected = selectedArtifactId === artifact.artifact_id;
            const isPendingDelete = pendingDeleteArtifactId === artifact.artifact_id;
            const isDeleting = deletingArtifactId === artifact.artifact_id;
            const actionError = String(actionErrorByArtifactId[artifact.artifact_id] || "").trim();
            const compatibleTools = Array.isArray(toolInventory)
              ? toolInventory.filter((tool) => evaluateArtifactCompatibility(artifact, tool?.artifact_picker))
              : [];
            const openHref = resolveRouteHref(baseUrl, artifact.routes?.open || artifact.open_url);
            const previewHref = resolveRouteHref(baseUrl, artifact.routes?.preview || artifact.preview_url);
            const metaParts = [
              artifact.artifact_type_label,
              artifact.mime_type,
              artifact.provenance?.source_label || "",
              artifact.created_at ? `Created ${formatArtifactDate(artifact.created_at)}` : "",
              artifact.consumption?.default_mode
                ? `used as ${formatConsumptionMode(artifact.consumption.default_mode)}`
                : "",
            ].filter(Boolean);
            return (
              <div
                key={artifact.artifact_id}
                style={{
                  border: `1px solid ${isSelected ? "#0ea5e9" : "#dbeafe"}`,
                  borderRadius: 14,
                  padding: 12,
                  background: isSelected ? "#f0f9ff" : "#ffffff",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "flex-start" }}>
                  <div>
                    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                      <div style={{ fontWeight: 700, color: "#0f172a" }}>{artifact.display_name}</div>
                      {artifact.reviewed ? <span style={{ ...styles.pill, ...styles.statusOk }}>Reviewed</span> : null}
                      {artifact.consumption?.default_mode ? (
                        <span style={styles.pill}>{formatConsumptionMode(artifact.consumption.default_mode)}</span>
                      ) : null}
                    </div>
                    <div style={styles.small}>{metaParts.join(" | ")}</div>
                    {artifact.summary ? <div style={{ marginTop: 4 }}>{artifact.summary}</div> : null}
                  </div>
                  <div style={styles.actionRow}>
                    <button
                      type="button"
                      style={styles.secondaryButton}
                      disabled={isDeleting}
                      onClick={(event) => {
                        event.stopPropagation();
                        clearArtifactActionError(artifact.artifact_id);
                        setSelectedArtifactId(isSelected ? "" : artifact.artifact_id);
                      }}
                    >
                      {isSelected ? "Hide Details" : "Inspect Details"}
                    </button>
                    {artifact.capabilities?.can_preview && previewHref ? (
                      <a
                        href={previewHref}
                        style={styles.inlineActionButton}
                        title={artifact.debug?.file_path || artifact.debug?.metadata_path || ""}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(event) => event.stopPropagation()}
                      >
                        Preview Artifact
                      </a>
                    ) : (
                      <span
                        aria-disabled="true"
                        style={{ ...styles.inlineActionButton, opacity: 0.5, cursor: "not-allowed" }}
                      >
                        Preview Unavailable
                      </span>
                    )}
                    {artifact.capabilities?.can_open && openHref ? (
                      <a
                        href={openHref}
                        style={styles.inlineActionButton}
                        title={artifact.debug?.file_path || artifact.debug?.metadata_path || ""}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(event) => event.stopPropagation()}
                      >
                        Open Saved File
                      </a>
                    ) : (
                      <span
                        aria-disabled="true"
                        style={{ ...styles.inlineActionButton, opacity: 0.5, cursor: "not-allowed" }}
                      >
                        Open Unavailable
                      </span>
                    )}
                    {artifact.capabilities?.can_reuse ? (
                      <button
                        type="button"
                        style={styles.inlineActionButton}
                        disabled={isDeleting}
                        onClick={(event) => {
                          event.stopPropagation();
                          clearArtifactActionError(artifact.artifact_id);
                          onUseInNextStep?.(artifact, {});
                        }}
                      >
                        Reuse In Composer
                      </button>
                    ) : (
                      <span
                        aria-disabled="true"
                        style={{ ...styles.inlineActionButton, opacity: 0.5, cursor: "not-allowed" }}
                      >
                        Reuse Unavailable
                      </span>
                    )}
                    {artifact.capabilities?.can_delete ? (
                      <button
                        type="button"
                        style={styles.inlineActionButton}
                        disabled={isDeleting}
                        onClick={(event) => {
                          event.stopPropagation();
                          clearArtifactActionError(artifact.artifact_id);
                          setPendingDeleteArtifactId((current) => (current === artifact.artifact_id ? "" : artifact.artifact_id));
                        }}
                      >
                        {isDeleting ? "Deleting..." : "Delete Artifact"}
                      </button>
                    ) : (
                      <span
                        aria-disabled="true"
                        style={{ ...styles.inlineActionButton, opacity: 0.5, cursor: "not-allowed" }}
                      >
                        Delete Unavailable
                      </span>
                    )}
                  </div>
                </div>
                {isPendingDelete ? (
                  <div style={{ ...styles.compactNote, marginTop: 10, display: "grid", gap: 8 }}>
                    <div>Delete this artifact from the current session? This removes the saved file and metadata.</div>
                    <div style={styles.actionRow}>
                      <button
                        type="button"
                        style={styles.inlineActionButton}
                        disabled={isDeleting}
                        onClick={(event) => {
                          event.stopPropagation();
                          confirmDeleteArtifact(artifact);
                        }}
                      >
                        Confirm Delete
                      </button>
                      <button
                        type="button"
                        style={styles.secondaryButton}
                        disabled={isDeleting}
                        onClick={(event) => {
                          event.stopPropagation();
                          clearArtifactActionError(artifact.artifact_id);
                          setPendingDeleteArtifactId((current) => (current === artifact.artifact_id ? "" : current));
                        }}
                      >
                        Cancel Delete
                      </button>
                    </div>
                    {actionError ? <div style={{ color: "#b91c1c" }}>{actionError}</div> : null}
                  </div>
                ) : null}
                {!isPendingDelete && actionError ? (
                  <div style={{ ...styles.compactNote, marginTop: 10, color: "#b91c1c" }}>{actionError}</div>
                ) : null}
                {compatibleTools.length > 0 ? (
                  <div style={{ ...styles.compactNote, marginTop: 10, display: "grid", gap: 6 }}>
                    <div style={{ fontWeight: 700, color: "#334155" }}>Suggested next steps</div>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      {compatibleTools.slice(0, 4).map((tool) => (
                        <button
                          key={String(tool.tool_id || tool.name || "")}
                          type="button"
                          style={styles.inlineActionButton}
                          disabled={isDeleting}
                          onClick={(event) => {
                            event.stopPropagation();
                            clearArtifactActionError(artifact.artifact_id);
                            onUseInNextStep?.(artifact, {
                              preferredTargetId: String(tool.tool_id || "").trim(),
                            });
                          }}
                        >
                          {`Use with ${String(tool.name || tool.tool_id || "tool").trim()}`}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}
                {isSelected ? (
                  <div style={{ ...styles.compactNote, marginTop: 10, display: "grid", gap: 4 }}>
                    {artifact.consumption?.default_mode ? (
                      <div>{`Default reuse mode: ${formatConsumptionMode(artifact.consumption.default_mode)}`}</div>
                    ) : null}
                    {artifact.consumption?.supported_modes?.length ? (
                      <div>{`Supported reuse modes: ${artifact.consumption.supported_modes.map(formatConsumptionMode).join(", ")}`}</div>
                    ) : null}
                    {artifact.eligible_consumers.length ? (
                      <div>{`Eligible consumers: ${artifact.eligible_consumers.join(", ")}`}</div>
                    ) : null}
                    {artifact.provenance?.source_session_id ? (
                      <div>{`Source session: ${artifact.provenance.source_session_id}`}</div>
                    ) : null}
                    {artifact.file_info?.extension ? (
                      <div>{`File type: ${artifact.file_info.extension}`}</div>
                    ) : null}
                    {artifact.file_info?.size_bytes !== null && artifact.file_info?.size_bytes !== undefined ? (
                      <div>{`File size: ${artifact.file_info.size_bytes} bytes`}</div>
                    ) : null}
                    {(artifact.debug?.file_path || artifact.debug?.metadata_path || artifact.debug?.artifact_id) ? (
                      <div style={{ marginTop: 6 }}>
                        <div style={{ fontWeight: 700, color: "#334155" }}>Debug Details</div>
                        {artifact.debug?.file_path ? <div>{`Saved file: ${artifact.debug.file_path}`}</div> : null}
                        {!artifact.debug?.file_path && artifact.debug?.metadata_path ? (
                          <div>{`Metadata: ${artifact.debug.metadata_path}`}</div>
                        ) : null}
                        {artifact.debug?.artifact_id || artifact.artifact_id ? (
                          <div>{`Artifact id: ${artifact.debug?.artifact_id || artifact.artifact_id}`}</div>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}

      {selectedArtifact && (
        <div style={{ ...styles.small, marginTop: 12 }}>
          {`Selected artifact for next step: ${selectedArtifact.display_name}`}
        </div>
      )}
    </section>
  );
}
