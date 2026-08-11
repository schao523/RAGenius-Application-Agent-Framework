import React, { useEffect, useMemo, useState } from "react";
import ArtifactUploadControl from "./ArtifactUploadControl";

function normalizeObjectSchema(schema) {
  if (!schema || typeof schema !== "object") {
    return { properties: {}, required: [], anyOf: [] };
  }
  const baseProperties =
    schema.properties && typeof schema.properties === "object" ? { ...schema.properties } : {};
  const baseRequired = Array.isArray(schema.required) ? [...schema.required] : [];
  const baseAnyOf = Array.isArray(schema.anyOf) ? [...schema.anyOf] : [];
  const allOf = Array.isArray(schema.allOf) ? schema.allOf : [];

  return allOf.reduce(
    (acc, branch) => {
      const normalizedBranch = normalizeObjectSchema(branch);
      return {
        properties: { ...acc.properties, ...normalizedBranch.properties },
        required: Array.from(new Set([...acc.required, ...normalizedBranch.required])),
        anyOf: [...acc.anyOf, ...normalizedBranch.anyOf],
      };
    },
    {
      properties: baseProperties,
      required: Array.from(new Set(baseRequired)),
      anyOf: baseAnyOf,
    },
  );
}

function defaultValueForField(fieldSchema) {
  if (fieldSchema && typeof fieldSchema === "object" && fieldSchema.default !== undefined) {
    return fieldSchema.default;
  }
  if (fieldSchema?.type === "boolean") {
    return false;
  }
  return "";
}

function humanizeFieldName(name) {
  return String(name || "")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function normalizeInventory(items) {
  return [...(Array.isArray(items) ? items : [])]
    .filter((item) => item && item.exec_capable !== false && item.enabled !== false)
    .sort((a, b) => {
      const left = String(a.name || a.skill_id || a.tool_id || "");
      const right = String(b.name || b.skill_id || b.tool_id || "");
      return left.localeCompare(right);
    });
}

function normalizeArtifactInventory(items) {
  return [...(Array.isArray(items) ? items : [])]
    .filter((item) => item && item.artifact_id)
    .map((item) => ({
      ...item,
      consumption:
        item?.consumption && typeof item.consumption === "object"
          ? {
              default_mode: item.consumption.default_mode || "",
              supported_modes: Array.isArray(item.consumption.supported_modes)
                ? item.consumption.supported_modes
                : [],
            }
          : null,
    }))
    .sort((a, b) => {
      const left = String(a.display_name || a.artifact_id || "");
      const right = String(b.display_name || b.artifact_id || "");
      return left.localeCompare(right);
    });
}

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
    return {
      eligible: false,
      reasons: ["This tool does not accept reusable artifacts."],
    };
  }
  const reasons = [];
  const artifactType = String(artifact?.artifact_type || "").trim();
  const mimeType = String(artifact?.mime_type || "").trim();
  const acceptedTypes = normalizeStringArray(
    picker.accepted_artifact_types?.length ? picker.accepted_artifact_types : picker.allowed_artifact_types,
  );
  const acceptedMimeTypes = normalizeStringArray(picker.allowed_mime_types);
  const requiredConsumptionMode = String(picker.required_consumption_mode || "").trim();

  if (acceptedTypes.length > 0 && !acceptedTypes.includes(artifactType)) {
    reasons.push(`Accepted artifact types: ${acceptedTypes.join(", ")}`);
  }
  if (acceptedMimeTypes.length > 0 && mimeType && !acceptedMimeTypes.includes(mimeType)) {
    reasons.push(`Accepted MIME types: ${acceptedMimeTypes.join(", ")}`);
  }
  if (!artifactSupportsConsumptionMode(artifact, requiredConsumptionMode)) {
    reasons.push(`Required consumption mode: ${formatConsumptionMode(requiredConsumptionMode)}`);
  }

  return {
    eligible: reasons.length === 0,
    reasons,
  };
}

function toolGroupLabel(item) {
  const toolId = String(item?.tool_id || "").trim().toLowerCase();
  if (toolId.startsWith("adapter.notebooklm.")) {
    return "NotebookLM Tools";
  }
  if (toolId.startsWith("mcp.gmail.")) {
    return "Gmail Tools";
  }
  if (toolId.startsWith("mcp.gdrive.")) {
    return "Google Drive Tools";
  }
  if (toolId.startsWith("mcp.gdocs.")) {
    return "Google Docs Tools";
  }
  if (toolId.startsWith("mcp.cms.")) {
    return "CMS Tools";
  }
  if (toolId.startsWith("adapter.") || toolId.includes("artifact") || toolId.includes("file")) {
    return "Runtime Tools";
  }
  return "Other Tools";
}

function classifySkillInventoryItem(item) {
  if (!item || typeof item !== "object") {
    return "skill";
  }
  if (item.inventory_source === "builder_bound") {
    return "app_skill";
  }
  if (item.workflow_kind === "multi_step_workflow") {
    return "workflow";
  }
  return "skill";
}

function targetOptionLabel(item, commandKind) {
  const baseLabel = String(item?.name || item?.tool_id || item?.skill_id || "").trim();
  if (commandKind !== "skill") {
    return baseLabel;
  }
  const kind = classifySkillInventoryItem(item);
  if (kind === "app_skill") {
    return `${baseLabel} [App Skill]`;
  }
  if (kind === "workflow") {
    return `${baseLabel} [Workflow]`;
  }
  return baseLabel;
}

function selectedMetaLines(selected, commandKind) {
  if (!selected || typeof selected !== "object") {
    return [];
  }
  if (commandKind === "tool") {
    const lines = [`Runtime tool | ${selected.tool_id || ""}`];
    if (selected.exec_binding_skill_id) {
      lines.push(`Execution contract | ${selected.exec_binding_skill_id}`);
    }
    return lines;
  }
  const kind = classifySkillInventoryItem(selected);
  const skillId = selected.skill_id || "";
  if (kind === "app_skill") {
    return [
      "App skill | Builder-bound published skill",
      `Skill id | ${skillId}`,
    ];
  }
  if (kind === "workflow") {
    return [
      "Runtime workflow | Multi-step workflow",
      `Skill id | ${skillId}`,
    ];
  }
  return [`Skill id | ${skillId}`];
}

function helperCopyForMode(commandKind) {
  if (commandKind === "agent") {
    return "Describe the task in natural language and optionally select an approved Agent Skill.";
  }
  if (commandKind === "tool") {
    return "Choose a runtime tool and fill the required arguments.";
  }
  return "Choose an app skill or runtime workflow and fill the required arguments.";
}

function classifyAgentRisk(requestText) {
  const text = String(requestText || "").trim().toLowerCase();
  if (!text) {
    return {
      riskClass: "agent_read_only",
      label: "Read only",
      help: "Read-only requests usually run without confirmation.",
    };
  }
  if (/\b(delete|remove|destroy|erase|wipe|purge|drop|truncate)\b/.test(text)) {
    return {
      riskClass: "agent_destructive",
      label: "Blocked",
      help: "Destructive requests are blocked by policy.",
    };
  }
  if (
    /\b(file|files|workspace|repo|repository|patch|code|branch|commit|pull request|pr)\b/.test(text) &&
    /\b(write|edit|modify|update|refactor|patch|create|save|rename)\b/.test(text)
  ) {
    return {
      riskClass: "agent_workspace_write",
      label: "Needs confirmation",
      help: "Workspace-writing requests require confirmation.",
    };
  }
  if (/\b(generate|create|draft|send|publish|post|upload|add|import|export|build)\b/.test(text)) {
    return {
      riskClass: "agent_external_write",
      label: "Needs confirmation",
      help: "External write requests require confirmation.",
    };
  }
  return {
    riskClass: "agent_read_only",
    label: "Read only",
    help: "Read-only requests usually run without confirmation.",
  };
}

function groupInventoryItems(items, commandKind) {
  const groups = new Map();
  items.forEach((item) => {
    let label = "Other";
    if (commandKind === "tool") {
      label = toolGroupLabel(item);
    } else {
      const kind = classifySkillInventoryItem(item);
      if (kind === "app_skill") {
        label = "App Skills";
      } else if (kind === "workflow") {
        label = "Runtime Workflows";
      } else {
        label = "Other Skills";
      }
    }
    if (!groups.has(label)) {
      groups.set(label, []);
    }
    groups.get(label).push(item);
  });
  return Array.from(groups.entries());
}

function serializeFieldValue(fieldSchema, value) {
  if (fieldSchema?.type === "array") {
    return Array.isArray(value) ? value.join(", ") : "";
  }
  if (fieldSchema?.type === "object") {
    return value && typeof value === "object" ? JSON.stringify(value, null, 2) : "";
  }
  return value ?? "";
}

function parseFieldValue(fieldSchema, rawValue) {
  if (fieldSchema?.type === "number" || fieldSchema?.type === "integer") {
    return rawValue === "" ? "" : Number(rawValue);
  }
  if (fieldSchema?.type === "array") {
    if (Array.isArray(rawValue)) {
      return rawValue.map((item) => String(item || "").trim()).filter(Boolean);
    }
    return String(rawValue || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }
  if (fieldSchema?.type === "object") {
    if (rawValue && typeof rawValue === "object") {
      return rawValue;
    }
    const trimmed = String(rawValue || "").trim();
    if (!trimmed) {
      return "";
    }
    return JSON.parse(trimmed);
  }
  return rawValue;
}

function resolveArtifactModeForField(artifact, requiredMode) {
  const normalizedRequiredMode = String(requiredMode || "").trim();
  if (normalizedRequiredMode && artifactSupportsConsumptionMode(artifact, normalizedRequiredMode)) {
    return normalizedRequiredMode;
  }
  return String(artifact?.consumption?.default_mode || "").trim();
}

function buildAgentArtifactRef(artifact) {
  const artifactId = String(artifact?.artifact_id || "").trim();
  if (!artifactId) {
    return null;
  }
  return {
    artifact_id: artifactId,
    role: artifact?.artifact_type === "session_upload" ? "attachment" : "source",
    reuse_mode: String(artifact?.consumption?.default_mode || "inline_text").trim() || "inline_text",
  };
}

function buildDefaultAgentExpectedOutputs(enabled) {
  if (!enabled) {
    return [];
  }
  return [
    {
      output_id: "agent_output",
      artifact_type: "agent_output",
      media_type: "text/markdown",
      persist_as_artifact: true,
      required: false,
    },
  ];
}

function pickerFieldExistsInSchema(picker, properties) {
  const fieldName = String(picker?.field_name || "artifactIds").trim();
  return Boolean(fieldName && properties && Object.prototype.hasOwnProperty.call(properties, fieldName));
}

function resolveArtifactPickerForTarget(selected, commandKind, toolInventory, properties) {
  const ownPicker =
    selected?.artifact_picker && typeof selected.artifact_picker === "object" && selected.artifact_picker.enabled
      ? selected.artifact_picker
      : null;
  if (ownPicker && pickerFieldExistsInSchema(ownPicker, properties)) {
    return ownPicker;
  }
  if (commandKind !== "skill") {
    return null;
  }
  const requiredTools = Array.isArray(selected?.required_tools)
    ? selected.required_tools.map((toolId) => String(toolId || "").trim()).filter(Boolean)
    : [];
  if (requiredTools.length === 0 || !Array.isArray(toolInventory)) {
    return null;
  }
  const inheritedTool = toolInventory.find((tool) => {
    const toolId = String(tool?.tool_id || "").trim();
    const picker = tool?.artifact_picker;
    return (
      requiredTools.includes(toolId) &&
      picker &&
      typeof picker === "object" &&
      picker.enabled === true &&
      pickerFieldExistsInSchema(picker, properties)
    );
  });
  return inheritedTool?.artifact_picker || null;
}

export default function ExecutionComposer({
  toolInventory,
  skillInventory,
  agentSkillInventory = [],
  agentSkillInventoryLoading = false,
  agentSkillInventoryError = "",
  agentSkillProjectionStatusByBackend = {},
  artifactInventory,
  initialArtifactSuggestion,
  initialArtifactSuggestions,
  initialTargetId,
  initialCommandKind,
  initialAgentBackend,
  selectedApprovedContent,
  onUploadExecutionInput,
  onRetryArtifactUpload,
  onRefreshAgentSkills,
  onSubmit,
  onClose,
  styles,
}) {
  const normalizedInitialCommandKind = ["tool", "skill", "agent"].includes(String(initialCommandKind || "").trim())
    ? String(initialCommandKind || "").trim()
    : "tool";
  const normalizedInitialAgentBackend = String(initialAgentBackend || "").trim() === "openclaw_cli"
    ? "openclaw_cli"
    : "codex_cli";
  const initialSuggestedArtifacts = useMemo(
    () => [
      ...(Array.isArray(initialArtifactSuggestions) ? initialArtifactSuggestions : []),
      ...(initialArtifactSuggestion ? [initialArtifactSuggestion] : []),
    ].filter(Boolean),
    [initialArtifactSuggestion, initialArtifactSuggestions],
  );
  const initialAgentArtifactIds = Array.from(
    new Set(initialSuggestedArtifacts.map((artifact) => String(artifact?.artifact_id || "").trim()).filter(Boolean)),
  );
  const [commandKind, setCommandKind] = useState(normalizedInitialCommandKind);
  const [targetId, setTargetId] = useState("");
  const [executionMode, setExecutionMode] = useState("sync");
  const [formState, setFormState] = useState({});
  const [agentRequest, setAgentRequest] = useState("");
  const [agentBackend, setAgentBackend] = useState(normalizedInitialAgentBackend);
  const [selectedAgentSkillId, setSelectedAgentSkillId] = useState("");
  const [agentArtifactIds, setAgentArtifactIds] = useState(
    normalizedInitialCommandKind === "agent" ? initialAgentArtifactIds : [],
  );
  const [persistAgentOutput, setPersistAgentOutput] = useState(true);
  const [preparedArtifactsByUploadId, setPreparedArtifactsByUploadId] = useState({});
  const [uploadBusy, setUploadBusy] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [showOptionalFields, setShowOptionalFields] = useState(false);
  const agentRisk = useMemo(() => classifyAgentRisk(agentRequest), [agentRequest]);
  const availableAgentSkills = useMemo(
    () => [...(Array.isArray(agentSkillInventory) ? agentSkillInventory : [])]
      .filter((item) => (
        item
        && item.backend === agentBackend
        && String(item.agent_skill_id || "").trim()
        && String(item.approved_fingerprint || "").trim()
      ))
      .sort((left, right) => String(left.display_name || left.agent_skill_id || "")
        .localeCompare(String(right.display_name || right.agent_skill_id || ""))),
    [agentBackend, agentSkillInventory],
  );
  const selectedAgentSkill = useMemo(
    () => availableAgentSkills.find((item) => item.agent_skill_id === selectedAgentSkillId) || null,
    [availableAgentSkills, selectedAgentSkillId],
  );

  const requestAgentSkillRefresh = (force) => {
    Promise.resolve(onRefreshAgentSkills?.({ backend: agentBackend, force })).catch((refreshError) => {
      setError(String(refreshError?.message || refreshError || "Unable to refresh Agent Skills."));
    });
  };

  useEffect(() => {
    const handleWindowFocus = () => requestAgentSkillRefresh(false);
    window.addEventListener("focus", handleWindowFocus);
    return () => window.removeEventListener("focus", handleWindowFocus);
  }, [agentBackend, onRefreshAgentSkills]);

  useEffect(() => {
    if (selectedAgentSkillId && !selectedAgentSkill) {
      setSelectedAgentSkillId("");
    }
  }, [selectedAgentSkill, selectedAgentSkillId]);

  const items = useMemo(
    () =>
      normalizeInventory(
        commandKind === "tool" ? toolInventory : commandKind === "skill" ? skillInventory : [],
      ),
    [commandKind, skillInventory, toolInventory],
  );
  const inventoryArtifacts = useMemo(() => normalizeArtifactInventory(artifactInventory), [artifactInventory]);
  const suggestedArtifact =
    initialArtifactSuggestion && typeof initialArtifactSuggestion === "object"
      ? initialArtifactSuggestion
      : null;
  const artifacts = useMemo(() => {
    const rows = [...inventoryArtifacts];
    for (const artifact of Object.values(preparedArtifactsByUploadId)) {
      if (artifact?.artifact_id && !rows.some((item) => item.artifact_id === artifact.artifact_id)) {
        rows.push(artifact);
      }
    }
    for (const initialArtifact of initialSuggestedArtifacts) {
      const suggestedArtifactId = String(initialArtifact?.artifact_id || "").trim();
      if (suggestedArtifactId && !rows.some((item) => String(item.artifact_id || "").trim() === suggestedArtifactId)) {
        rows.push(...normalizeArtifactInventory([initialArtifact]));
      }
    }
    return rows;
  }, [inventoryArtifacts, initialSuggestedArtifacts, preparedArtifactsByUploadId]);
  const resolvedSuggestedArtifact = useMemo(() => {
    const suggestedArtifactId = String(suggestedArtifact?.artifact_id || "").trim();
    if (!suggestedArtifactId) {
      return suggestedArtifact;
    }
    const matchingArtifact = artifacts.find((item) => String(item.artifact_id || "").trim() === suggestedArtifactId);
    return matchingArtifact ? { ...matchingArtifact, ...suggestedArtifact } : suggestedArtifact;
  }, [artifacts, suggestedArtifact]);
  const normalizedSuggestedArtifactId = String(suggestedArtifact?.artifact_id || "").trim();
  const compatibleToolTargetIds = useMemo(() => {
    if (commandKind !== "tool" || !normalizedSuggestedArtifactId) {
      return [];
    }
    return normalizeInventory(toolInventory)
      .filter((item) => {
        const picker = item?.artifact_picker;
        if (!picker || typeof picker !== "object" || picker.enabled !== true) {
          return false;
        }
        return evaluateArtifactCompatibility(resolvedSuggestedArtifact, picker).eligible;
      })
      .map((item) => String(item.tool_id || "").trim())
      .filter(Boolean);
  }, [
    commandKind,
    normalizedSuggestedArtifactId,
    resolvedSuggestedArtifact,
    toolInventory,
  ]);
  const selected = useMemo(
    () => items.find((item) => (item.tool_id || item.skill_id) === targetId) || null,
    [items, targetId],
  );
  const groupedItems = useMemo(() => groupInventoryItems(items, commandKind), [commandKind, items]);
  const schema = selected?.input_schema || {};
  const normalizedSchema = useMemo(() => normalizeObjectSchema(schema), [schema]);
  const properties = normalizedSchema.properties;
  const requiredFields = normalizedSchema.required;
  const anyOf = normalizedSchema.anyOf;
  const propertyEntries = Object.entries(properties);
  const requiredFieldSet = new Set(requiredFields);
  const requiredEntries = propertyEntries.filter(([key]) => requiredFieldSet.has(key));
  const optionalEntries = propertyEntries.filter(([key]) => !requiredFieldSet.has(key));
  const artifactPicker = useMemo(
    () => resolveArtifactPickerForTarget(selected, commandKind, toolInventory, properties),
    [selected, commandKind, toolInventory, properties],
  );
  const artifactPickerFieldName = artifactPicker?.field_name || "artifactIds";
  const pickerSelectionMode = artifactPicker?.selection_mode || "multiple";
  const pickerAllowedTypes = Array.isArray(artifactPicker?.allowed_artifact_types)
    ? new Set(artifactPicker.allowed_artifact_types.map((value) => String(value || "").trim()).filter(Boolean))
    : null;
  const pickerAllowedMimeTypes = Array.isArray(artifactPicker?.allowed_mime_types)
    ? new Set(artifactPicker.allowed_mime_types.map((value) => String(value || "").trim()).filter(Boolean))
    : null;
  const requiredConsumptionMode = String(artifactPicker?.required_consumption_mode || "").trim();
  const acceptedArtifactTypes = Array.isArray(artifactPicker?.accepted_artifact_types)
    ? artifactPicker.accepted_artifact_types.map((value) => String(value || "").trim()).filter(Boolean)
    : [];
  const pickerArtifactEvaluations = useMemo(() => {
    if (!artifactPicker) {
      return [];
    }
    return artifacts.map((item) => ({
      artifact: item,
      compatibility: evaluateArtifactCompatibility(item, artifactPicker),
    }));
  }, [artifactPicker, artifacts]);
  const pickerArtifacts = useMemo(
    () => pickerArtifactEvaluations.filter((entry) => entry.compatibility.eligible).map((entry) => entry.artifact),
    [pickerArtifactEvaluations],
  );
  const hiddenIncompatibleArtifactCount = useMemo(
    () => pickerArtifactEvaluations.filter((entry) => !entry.compatibility.eligible).length,
    [pickerArtifactEvaluations],
  );
  const incompatibleArtifactEvaluations = useMemo(
    () => pickerArtifactEvaluations.filter((entry) => !entry.compatibility.eligible),
    [pickerArtifactEvaluations],
  );
  const artifactReuseSummary = useMemo(() => {
    if (!artifactPicker) {
      return [];
    }
    const rawValue = formState[artifactPickerFieldName];
    const selectedIds = pickerSelectionMode === "single"
      ? (rawValue ? [String(rawValue)] : [])
      : (Array.isArray(rawValue) ? rawValue.map((item) => String(item || "").trim()).filter(Boolean) : []);
    return selectedIds
      .map((artifactId) => artifacts.find((item) => String(item.artifact_id || "").trim() === artifactId))
      .filter(Boolean)
      .map((artifact) => ({
        artifact_id: String(artifact.artifact_id || "").trim(),
        display_name: String(artifact.display_name || artifact.artifact_id || "Artifact").trim(),
        field_name: artifactPickerFieldName,
        resolved_mode: resolveArtifactModeForField(artifact, requiredConsumptionMode),
      }));
  }, [
    artifactPicker,
    artifactPickerFieldName,
    artifacts,
    formState,
    pickerSelectionMode,
    requiredConsumptionMode,
  ]);
  const suggestedArtifactCompatibility = useMemo(() => {
    if (!artifactPicker || !normalizedSuggestedArtifactId) {
      return null;
    }
    return evaluateArtifactCompatibility(resolvedSuggestedArtifact, artifactPicker);
  }, [artifactPicker, normalizedSuggestedArtifactId, resolvedSuggestedArtifact]);
  const selectedAgentArtifacts = useMemo(() => {
    const selectedIds = new Set(agentArtifactIds.map((artifactId) => String(artifactId || "").trim()).filter(Boolean));
    return artifacts.filter((artifact) => selectedIds.has(String(artifact.artifact_id || "").trim()));
  }, [agentArtifactIds, artifacts]);
  const agentArtifactRefs = useMemo(
    () => selectedAgentArtifacts.map(buildAgentArtifactRef).filter(Boolean),
    [selectedAgentArtifacts],
  );
  useEffect(() => {
    if (commandKind === "agent") {
      setTargetId("");
      setFormState({});
      setError("");
      setShowOptionalFields(false);
      return;
    }
    setAgentArtifactIds([]);
    const preferredTargetId =
      commandKind === "tool" && initialTargetId && items.some((item) => String(item.tool_id || item.skill_id || "").trim() === String(initialTargetId).trim())
        ? String(initialTargetId).trim()
        : commandKind === "tool" && compatibleToolTargetIds.length > 0
          ? compatibleToolTargetIds[0]
        : items[0]
          ? (items[0].tool_id || items[0].skill_id || "")
          : "";
    const nextTargetId = preferredTargetId;
    setTargetId(nextTargetId);
  }, [commandKind, compatibleToolTargetIds, initialTargetId, toolInventory, skillInventory, items]);

  useEffect(() => {
    if (commandKind === "agent") {
      return;
    }
    const nextState = {};
    Object.entries(properties).forEach(([key, fieldSchema]) => {
      if (artifactPicker && key === artifactPickerFieldName) {
        if (
          normalizedSuggestedArtifactId
          && compatibleToolTargetIds.includes(String(targetId || "").trim())
        ) {
          nextState[key] = pickerSelectionMode === "single" ? normalizedSuggestedArtifactId : [normalizedSuggestedArtifactId];
        } else {
          nextState[key] = pickerSelectionMode === "single" ? "" : [];
        }
      } else {
        nextState[key] = serializeFieldValue(fieldSchema, defaultValueForField(fieldSchema));
      }
    });
    if (executionMode === "async") {
      nextState.execution_mode = "async";
    }
    setFormState(nextState);
    setError("");
    setShowOptionalFields(false);
  }, [
    targetId,
    artifactPicker,
    artifactPickerFieldName,
    pickerSelectionMode,
    normalizedSuggestedArtifactId,
    compatibleToolTargetIds,
  ]);

  useEffect(() => {
    setFormState((prev) => {
      const next = { ...prev };
      if (executionMode === "async") {
        next.execution_mode = "async";
      } else {
        delete next.execution_mode;
      }
      return next;
    });
  }, [executionMode]);

  const setFieldValue = (key, value) => {
    setFormState((prev) => ({ ...prev, [key]: value }));
  };

  const toggleAgentArtifactSelection = (artifactId) => {
    const normalizedId = String(artifactId || "").trim();
    if (!normalizedId) {
      return;
    }
    setAgentArtifactIds((prev) => {
      const current = new Set(prev.map((item) => String(item || "").trim()).filter(Boolean));
      if (current.has(normalizedId)) {
        current.delete(normalizedId);
      } else {
        current.add(normalizedId);
      }
      return [...current];
    });
  };

  const removeAgentArtifactSelection = (artifactId) => {
    const normalizedId = String(artifactId || "").trim();
    if (!normalizedId) {
      return;
    }
    setAgentArtifactIds((prev) => prev.filter((item) => String(item || "").trim() !== normalizedId));
  };

  const acceptUploadedArtifact = (rawArtifact) => {
    if (!rawArtifact?.artifact_id) return;
    const artifact = {
      ...rawArtifact,
      artifact_type: rawArtifact.artifact_type || "session_upload",
      display_name: rawArtifact.display_name || rawArtifact.artifact_id,
      consumption: rawArtifact.consumption || {
        default_mode: "file_backed",
        supported_modes: ["file_backed", "binary_payload", "metadata_only"],
      },
    };
    setPreparedArtifactsByUploadId((previous) => ({
      ...previous,
      [artifact.artifact_id]: artifact,
    }));
    setAgentArtifactIds((previous) => [...new Set([...previous, artifact.artifact_id])]);
  };

  const renderAgentArtifactSelector = () => {
    const selectedIds = new Set(agentArtifactIds.map((artifactId) => String(artifactId || "").trim()).filter(Boolean));
    return (
      <div style={{ ...styles.compactNote, marginTop: 12, display: "grid", gap: 10 }}>
        <div style={{ fontWeight: 700, color: "#334155" }}>Agent artifacts</div>
        <div style={styles.small}>
          Selected artifacts are sent as structured artifact refs. OpenClaw stages file-backed artifacts before invoking the agent.
        </div>
        <ArtifactUploadControl
          onUpload={(file, operationId, onProgress, signal) => onUploadExecutionInput(file, operationId, onProgress, signal)}
          onRetry={onRetryArtifactUpload}
          onReady={acceptUploadedArtifact}
          onStatusChange={(status) => setUploadBusy(["uploading", "preparing"].includes(status))}
        />
        {selectedAgentArtifacts.length > 0 ? (
          <div style={{ display: "grid", gap: 6 }}>
            <div style={{ fontWeight: 700, color: "#334155" }}>Selected artifacts ({selectedAgentArtifacts.length})</div>
            {selectedAgentArtifacts.map((artifact) => {
              const labelText = String(artifact.display_name || artifact.artifact_id || "Artifact");
              return (
                <div
                  key={String(artifact.artifact_id)}
                  style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}
                >
                  <span>
                    {labelText}
                    {artifact?.consumption?.default_mode
                      ? ` (${formatConsumptionMode(artifact.consumption.default_mode)})`
                      : ""}
                  </span>
                  <button
                    type="button"
                    style={styles.inlineActionButton || styles.secondaryButton}
                    onClick={() => removeAgentArtifactSelection(artifact.artifact_id)}
                  >
                    {`Remove ${labelText}`}
                  </button>
                </div>
              );
            })}
          </div>
        ) : (
          <div style={styles.small}>No artifact selected.</div>
        )}
        {artifacts.length > 0 ? (
          <div style={{ display: "grid", gap: 8 }}>
            <div style={{ fontWeight: 700, color: "#334155" }}>Available artifacts</div>
            {artifacts.map((artifact) => {
              const artifactId = String(artifact.artifact_id || "").trim();
              const labelText = String(artifact.display_name || artifactId || "Artifact");
              const selectedForAgent = selectedIds.has(artifactId);
              const metaParts = [
                artifact.artifact_type ? String(artifact.artifact_type) : "",
                artifact.mime_type ? String(artifact.mime_type) : "",
                artifact?.consumption?.default_mode
                  ? `used as ${formatConsumptionMode(artifact.consumption.default_mode)}`
                  : "",
              ].filter(Boolean);
              return (
                <label
                  key={artifactId || labelText}
                  style={{
                    display: "flex",
                    gap: 8,
                    alignItems: "center",
                    border: selectedForAgent ? "1px solid #0f8f9a" : "1px solid #bfd0e4",
                    borderRadius: 999,
                    padding: "10px 14px",
                    background: selectedForAgent ? "#e8fbf7" : "#fff",
                    cursor: "pointer",
                  }}
                >
                  <input
                    type="checkbox"
                    checked={selectedForAgent}
                    onChange={() => toggleAgentArtifactSelection(artifactId)}
                  />
                  <span style={{ fontWeight: selectedForAgent ? 700 : 600 }}>
                    {labelText}
                    {metaParts.length > 0 ? ` (${metaParts.join(" | ")})` : ""}
                  </span>
                </label>
              );
            })}
          </div>
        ) : (
          <div style={styles.small}>No reusable artifacts are loaded for this session.</div>
        )}
        <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            type="checkbox"
            checked={persistAgentOutput}
            onChange={(event) => setPersistAgentOutput(event.target.checked)}
          />
          <span>Save agent output as reusable artifact</span>
        </label>
      </div>
    );
  };

  const renderField = ([key, fieldSchema]) => {
    const schemaType = fieldSchema?.type || "string";
    const required = requiredFields.includes(key);
    const enumValues = Array.isArray(fieldSchema?.enum) ? fieldSchema.enum : [];
    const fieldLabel = required ? `${humanizeFieldName(key)} *` : humanizeFieldName(key);
    const description = typeof fieldSchema?.description === "string" ? fieldSchema.description.trim() : "";
    const defaultValue = fieldSchema && typeof fieldSchema === "object" ? fieldSchema.default : undefined;
    if (artifactPicker && key === artifactPickerFieldName) {
      const selectedIds = pickerSelectionMode === "single"
        ? (formState[key] ? [String(formState[key])] : [])
        : (Array.isArray(formState[key]) ? formState[key] : []);
      const selectedArtifacts = selectedIds.map((artifactId) => {
        const matchingArtifact = artifacts.find((item) => String(item.artifact_id || "").trim() === String(artifactId || "").trim());
        return matchingArtifact || {
          artifact_id: String(artifactId || "").trim(),
          display_name: String(artifactId || "Selected artifact").trim(),
          consumption: null,
        };
      }).filter((artifact) => artifact.artifact_id);
      const normalizedSelectionMode = String(pickerSelectionMode || "").trim().toLowerCase();
      const isSingleArtifactSelection = normalizedSelectionMode === "single";
      const maxArtifactCount = Number.parseInt(String(artifactPicker?.max_artifact_count || ""), 10);
      const effectiveMaxArtifactCount = Number.isFinite(maxArtifactCount) && maxArtifactCount > 0
        ? maxArtifactCount
        : isSingleArtifactSelection
          ? 1
          : 0;
      const removeArtifactSelection = (artifactId) => {
        const normalizedId = String(artifactId || "").trim();
        if (!normalizedId) {
          return;
        }
        if (isSingleArtifactSelection) {
          if (selectedIds[0] === normalizedId) {
            setFieldValue(key, "");
          }
          return;
        }
        setFieldValue(
          key,
          selectedIds.filter((selectedId) => selectedId !== normalizedId),
        );
      };
      const toggleArtifactSelection = (artifactId) => {
        const normalizedId = String(artifactId || "").trim();
        if (!normalizedId) {
          return;
        }
        if (isSingleArtifactSelection) {
          setFieldValue(key, normalizedId);
          return;
        }
        const next = new Set(selectedIds);
        if (next.has(normalizedId)) {
          next.delete(normalizedId);
        } else {
          if (effectiveMaxArtifactCount > 0 && next.size >= effectiveMaxArtifactCount) {
            return;
          }
          next.add(normalizedId);
        }
        setFieldValue(key, [...next]);
      };
      return (
        <div key={key}>
          <div style={styles.label}>{fieldLabel}</div>
          {description ? <div style={styles.small}>{description}</div> : null}
          {artifactPicker?.eligible_for ? (
            <div style={styles.small}>{`Eligible for ${String(artifactPicker.eligible_for).replace(/_/g, " ")}`}</div>
          ) : null}
          {requiredConsumptionMode ? (
            <div style={styles.small}>{`Required consumption mode: ${formatConsumptionMode(requiredConsumptionMode)}`}</div>
          ) : null}
          {acceptedArtifactTypes.length > 0 ? (
            <div style={styles.small}>{`Accepted artifact types: ${acceptedArtifactTypes.join(", ")}`}</div>
          ) : null}
          {artifactPicker?.max_artifact_count ? (
            <div style={styles.small}>{`Maximum artifacts: ${String(artifactPicker.max_artifact_count)}`}</div>
          ) : null}
          {pickerArtifacts.length > 0 ? (
            <div style={styles.small}>
              {`${pickerArtifacts.length} eligible artifact${pickerArtifacts.length === 1 ? "" : "s"} available for this field.`}
            </div>
          ) : null}
          <div style={{ ...styles.compactNote, marginTop: 10, display: "grid", gap: 4 }}>
            <div style={{ fontWeight: 700, color: "#334155" }}>
              {isSingleArtifactSelection
                ? "Selected artifact"
                : `Selected artifacts (${selectedArtifacts.length}${effectiveMaxArtifactCount > 0 ? ` of ${effectiveMaxArtifactCount}` : ""})`}
            </div>
            {selectedArtifacts.length === 0 ? (
              <div>No artifact selected.</div>
            ) : (
              selectedArtifacts.map((artifact) => {
                const labelText = String(artifact.display_name || artifact.artifact_id || "Artifact");
                return (
                  <div
                    key={String(artifact.artifact_id)}
                    style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}
                  >
                    <span>
                      {labelText}
                      {artifact?.consumption?.default_mode
                        ? ` (${formatConsumptionMode(artifact.consumption.default_mode)})`
                        : ""}
                    </span>
                    <button
                      type="button"
                      style={styles.inlineActionButton || styles.secondaryButton}
                      onClick={() => removeArtifactSelection(artifact.artifact_id)}
                    >
                      {`Remove ${labelText}`}
                    </button>
                  </div>
                );
              })
            )}
          </div>
          <div style={{ display: "grid", gap: 8, marginTop: 10 }}>
            <div style={{ fontWeight: 700, color: "#334155" }}>Available artifacts</div>
            {pickerArtifacts.length === 0 ? (
              <div style={{ ...styles.compactNote, display: "grid", gap: 4 }}>
                <div>No compatible artifacts are loaded for this field.</div>
                <div>
                  {acceptedArtifactTypes.length > 0
                    ? `Required artifact type: ${acceptedArtifactTypes.join(", ")}.`
                    : "This field requires a reusable artifact."}
                  {requiredConsumptionMode ? ` Required reuse mode: ${formatConsumptionMode(requiredConsumptionMode)}.` : ""}
                </div>
                <div>
                  Open Artifact Library and choose a compatible recommended next step, or create a compatible artifact in this session.
                </div>
              </div>
            ) : (
              pickerArtifacts.map((artifact) => {
                const artifactId = String(artifact.artifact_id || "");
                const selectedForField = selectedIds.includes(artifactId);
                const labelText = String(artifact.display_name || artifactId);
                const selectionControlType = isSingleArtifactSelection ? "radio" : "checkbox";
                const maxReached = !isSingleArtifactSelection
                  && !selectedForField
                  && effectiveMaxArtifactCount > 0
                  && selectedIds.length >= effectiveMaxArtifactCount;
                const metaParts = [
                  artifact.artifact_type ? String(artifact.artifact_type) : "",
                  artifact.mime_type ? String(artifact.mime_type) : "",
                  artifact?.consumption?.default_mode
                    ? `used as ${formatConsumptionMode(artifact.consumption.default_mode)}`
                    : "",
                ].filter(Boolean);
                return (
                  <label
                    key={artifactId}
                    style={{
                      display: "flex",
                      gap: 8,
                      alignItems: "center",
                      border: selectedForField ? "1px solid #0f8f9a" : "1px solid #bfd0e4",
                      borderRadius: 999,
                      padding: "10px 14px",
                      background: selectedForField ? "#e8fbf7" : "#fff",
                      opacity: maxReached ? 0.58 : 1,
                      cursor: maxReached ? "not-allowed" : "pointer",
                    }}
                  >
                    <input
                      type={selectionControlType}
                      name={`artifact-picker-${artifactPickerFieldName}`}
                      checked={selectedForField}
                      disabled={maxReached}
                      onChange={() => toggleArtifactSelection(artifactId)}
                    />
                    <span style={{ fontWeight: selectedForField ? 700 : 600 }}>
                      {labelText}
                      {metaParts.length > 0 ? ` (${metaParts.join(" | ")})` : ""}
                    </span>
                    {maxReached ? <span style={styles.small}>Maximum selected</span> : null}
                  </label>
                );
              })
            )}
          </div>
          {incompatibleArtifactEvaluations.length > 0 ? (
            <div style={{ ...styles.compactNote, marginTop: 10, display: "grid", gap: 6 }}>
              <div style={{ fontWeight: 700, color: "#334155" }}>Unavailable artifacts</div>
              {incompatibleArtifactEvaluations.map(({ artifact, compatibility }) => {
                const artifactId = String(artifact.artifact_id || "");
                const labelText = String(artifact.display_name || artifactId || "Artifact");
                const metaParts = [
                  artifact.artifact_type ? String(artifact.artifact_type) : "",
                  artifact.mime_type ? String(artifact.mime_type) : "",
                  artifact?.consumption?.default_mode
                    ? `used as ${formatConsumptionMode(artifact.consumption.default_mode)}`
                    : "",
                ].filter(Boolean);
                const reasons = Array.isArray(compatibility?.reasons)
                  ? compatibility.reasons.map((reason) => String(reason || "").trim()).filter(Boolean)
                  : [];
                return (
                  <div key={artifactId || labelText} style={{ display: "grid", gap: 4 }}>
                    <button
                      type="button"
                      style={{ ...styles.secondaryButton, opacity: 0.58, cursor: "not-allowed" }}
                      disabled
                    >
                      {labelText}
                      {metaParts.length > 0 ? ` (${metaParts.join(" | ")})` : ""}
                    </button>
                    <div style={styles.small}>
                      {reasons.length > 0
                        ? `Not selectable: ${reasons.join("; ")}`
                        : "Not selectable for this field."}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : null}
          {artifactReuseSummary.length > 0 ? (
            <div style={{ ...styles.compactNote, marginTop: 10, display: "grid", gap: 4 }}>
              <div style={{ fontWeight: 700, color: "#334155" }}>Reuse summary</div>
              {artifactReuseSummary.map((entry) => (
                <div key={`${entry.field_name}-${entry.artifact_id}`}>
                  {`${humanizeFieldName(entry.field_name)} -> ${entry.display_name}`}
                  {entry.resolved_mode ? ` | Resolved mode: ${formatConsumptionMode(entry.resolved_mode)}` : ""}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      );
    }
    if (schemaType === "boolean") {
      return (
        <label key={key}>
          <div style={styles.label}>{fieldLabel}</div>
          {description ? <div style={styles.small}>{description}</div> : null}
          <input
            aria-label={key}
            type="checkbox"
            checked={Boolean(formState[key])}
            onChange={(e) => setFieldValue(key, e.target.checked)}
          />
        </label>
      );
    }
    if (enumValues.length > 0) {
      return (
        <label key={key}>
          <div style={styles.label}>{fieldLabel}</div>
          {description ? <div style={styles.small}>{description}</div> : null}
          <select
            aria-label={key}
            style={styles.select}
            value={formState[key] ?? ""}
            onChange={(e) => setFieldValue(key, e.target.value)}
          >
            <option value="">Select</option>
            {enumValues.map((value) => (
              <option key={String(value)} value={String(value)}>
                {String(value)}
              </option>
            ))}
          </select>
          {defaultValue !== undefined ? <div style={styles.small}>{`Default: ${String(defaultValue)}`}</div> : null}
        </label>
      );
    }
    const isStructured = schemaType === "object" || schemaType === "array";
    const isLongText = isStructured || (schemaType === "string" && /instructions|content|question|prompt|body/i.test(key));
    const sharedProps = {
      "aria-label": key,
      value: formState[key] ?? "",
      onChange: (e) => setFieldValue(key, e.target.value),
      placeholder:
        schemaType === "array"
          ? "item1, item2"
          : schemaType === "object"
            ? '{"key":"value"}'
            : undefined,
    };
    return (
      <label key={key}>
        <div style={styles.label}>{fieldLabel}</div>
        {description ? <div style={styles.small}>{description}</div> : null}
        {isLongText ? (
          <textarea {...sharedProps} style={styles.textarea} />
        ) : (
          <input
            {...sharedProps}
            style={styles.input}
            type={schemaType === "number" || schemaType === "integer" ? "number" : "text"}
          />
        )}
        {defaultValue !== undefined ? <div style={styles.small}>{`Default: ${String(defaultValue)}`}</div> : null}
      </label>
    );
  };

  const validate = () => {
    if (commandKind === "agent") {
      if (!String(agentRequest || "").trim()) {
        return "Agent request is required.";
      }
      return "";
    }
    for (const field of requiredFields) {
      const fieldSchema = properties[field];
      let value = formState[field];
      if (fieldSchema?.type === "object") {
        try {
          value = parseFieldValue(fieldSchema, value);
        } catch (_error) {
          return `Field \`${field}\` must contain valid JSON.`;
        }
      }
      if (Array.isArray(value) && value.length === 0) {
        return `Field \`${field}\` is required.`;
      }
      if (value === "" || value === null || value === undefined) {
        return `Field \`${field}\` is required.`;
      }
    }
    for (const condition of anyOf) {
      const fields = Array.isArray(condition?.required) ? condition.required : [];
      if (fields.length > 0) {
        const hasAny = fields.some((field) => {
          const value = formState[field];
          return !(value === "" || value === null || value === undefined);
        });
        if (!hasAny) {
          return `Provide one of: ${fields.join(", ")}.`;
        }
      }
    }
    return "";
  };

  const handleSubmit = async () => {
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }
    if (commandKind === "agent") {
      setError("");
      setSubmitting(true);
      try {
        await onSubmit?.({
          commandKind,
          targetId: agentBackend,
          executionMode,
          args: {
            request: String(agentRequest || "").trim(),
            ...(String(selectedAgentSkill?.provider_skill_name || "").trim()
              ? { skillHint: String(selectedAgentSkill.provider_skill_name).trim() }
              : {}),
            ...(selectedAgentSkill
              ? {
                  agentSkillRef: {
                    agent_skill_id: selectedAgentSkill.agent_skill_id,
                    approved_fingerprint: selectedAgentSkill.approved_fingerprint,
                  },
                }
              : {}),
            ...(agentArtifactRefs.length > 0 ? { artifactRefs: agentArtifactRefs } : {}),
            ...(persistAgentOutput ? { expectedOutputs: buildDefaultAgentExpectedOutputs(true) } : {}),
          },
        });
      } catch (submitError) {
        setError(String(submitError?.message || submitError || "Execution request failed."));
      } finally {
        setSubmitting(false);
      }
      return;
    }
    let args = {};
    try {
      args = Object.fromEntries(
        Object.entries(formState)
          .filter(([, value]) => value !== "" && value !== null && value !== undefined)
          .filter(([, value]) => !(Array.isArray(value) && value.length === 0))
          .map(([key, value]) => [key, parseFieldValue(properties[key], value)]),
      );
    } catch (_error) {
      setError("One or more fields contain invalid JSON.");
      return;
    }
    if (executionMode === "async") {
      args.execution_mode = "async";
    }
    setError("");
    setSubmitting(true);
    try {
      await onSubmit?.({
        commandKind,
        targetId,
        executionMode,
        args,
      });
    } catch (submitError) {
      setError(String(submitError?.message || submitError || "Execution request failed."));
    } finally {
      setSubmitting(false);
    }
  };

  const composerCardStyle = styles.executionComposerCard
    ? { ...styles.card, ...styles.executionComposerCard }
    : styles.card;

  return (
    <section aria-label="Execution Composer" style={composerCardStyle}>
      <div style={styles.executionLaneHeader}>
        <div>
          <h3 style={styles.sectionTitle}>Execution Composer</h3>
          <div style={styles.small}>{helperCopyForMode(commandKind)}</div>
        </div>
        <div style={styles.row}>
          <button type="button" style={styles.secondaryButton} onClick={onClose} disabled={submitting}>
            Close
          </button>
        </div>
      </div>

      <div style={styles.formGrid}>
        <label>
          <div style={styles.label}>Mode</div>
          <select style={styles.select} value={commandKind} onChange={(e) => setCommandKind(e.target.value)} aria-label="Mode">
            <option value="tool">Tool</option>
            <option value="skill">Skill</option>
            <option value="agent">Agent</option>
          </select>
        </label>
        {commandKind === "agent" ? (
          <>
            <label>
              <div style={styles.label}>Agent Backend</div>
              <select
                style={styles.select}
                value={agentBackend}
                onChange={(e) => {
                  const nextBackend = e.target.value;
                  setAgentBackend(nextBackend);
                  setSelectedAgentSkillId("");
                  Promise.resolve(onRefreshAgentSkills?.({
                    backend: nextBackend,
                    force: false,
                  })).catch((refreshError) => {
                    setError(String(refreshError?.message || refreshError || "Unable to refresh Agent Skills."));
                  });
                }}
                aria-label="Agent Backend"
              >
                <option value="codex_cli">Codex CLI</option>
                <option value="openclaw_cli">OpenClaw CLI</option>
              </select>
            </label>
            <label>
              <div style={styles.label}>Agent Skill</div>
              <select
                style={styles.select}
                value={selectedAgentSkillId}
                onChange={(e) => setSelectedAgentSkillId(e.target.value)}
                aria-label="Agent Skill"
                disabled={agentSkillInventoryLoading}
              >
                <option value="">Auto</option>
                {availableAgentSkills.map((item) => (
                  <option key={item.agent_skill_id} value={item.agent_skill_id}>
                    {item.display_name || item.provider_skill_name || item.agent_skill_id}
                  </option>
                ))}
              </select>
              {agentSkillInventoryLoading ? <div style={styles.small}>Loading approved Agent Skills...</div> : null}
              {agentSkillInventoryError ? <div style={styles.error}>{agentSkillInventoryError}</div> : null}
              {agentSkillProjectionStatusByBackend?.[agentBackend] === "unavailable" ? (
                <div style={styles.small}>Approved skill projection is unavailable. Auto remains available.</div>
              ) : null}
              <button
                type="button"
                style={{ ...styles.secondaryButton, marginTop: 8 }}
                onClick={() => requestAgentSkillRefresh(true)}
                disabled={agentSkillInventoryLoading}
              >
                Refresh Agent Skills
              </button>
            </label>
          </>
        ) : (
          <label>
            <div style={styles.label}>Target</div>
            <select style={styles.select} value={targetId} onChange={(e) => setTargetId(e.target.value)} aria-label="Target">
              {groupedItems.map(([groupLabel, groupItems]) => (
                <optgroup key={groupLabel} label={groupLabel}>
                  {groupItems.map((item) => {
                    const value = item.tool_id || item.skill_id;
                    return (
                      <option key={value} value={value}>
                        {targetOptionLabel(item, commandKind) || value}
                      </option>
                    );
                  })}
                </optgroup>
              ))}
            </select>
          </label>
        )}
        <label>
          <div style={styles.label}>Execution Mode</div>
          <select style={styles.select} value={executionMode} onChange={(e) => setExecutionMode(e.target.value)} aria-label="Execution Mode">
            <option value="sync">sync</option>
            <option value="async">async</option>
          </select>
        </label>
      </div>

      {commandKind === "agent" ? (
        <>
          <div style={styles.compactNote}>
            {agentBackend === "openclaw_cli"
              ? "OpenClaw agent mode runs the request through the `openclaw_cli` backend. Workspace staging and verification are handled by the execution subsystem."
              : "Codex agent mode runs a natural-language task through the `codex_cli` backend."}
          </div>
          <div style={styles.small}>
            {`Predicted policy | ${agentRisk.label} (${agentRisk.riskClass.replace(/^agent_/, "").replace(/_/g, " ")})`}
          </div>
          <div style={styles.small}>{agentRisk.help}</div>
          {selectedApprovedContent ? (
            <div style={styles.small}>
              {`Selected approved revision | ${selectedApprovedContent.revision_id || selectedApprovedContent.approved_content_id || "n/a"}`}
            </div>
          ) : (
            <div style={styles.small}>Selected approved revision | none</div>
          )}
          <div style={{ marginTop: 12 }}>
            <div style={styles.label}>Agent request</div>
            <textarea
              aria-label="Agent Request"
              style={styles.textarea}
              value={agentRequest}
              onChange={(e) => setAgentRequest(e.target.value)}
              placeholder='For example: "Use NotebookLM to create a Traditional Chinese study guide for Micah 2:1-11."'
            />
          </div>
          {renderAgentArtifactSelector()}
        </>
      ) : selected ? (
        <>
          <div style={styles.compactNote}>
            {selected.description || "No description available."}
          </div>
          {commandKind === "tool" && normalizedSuggestedArtifactId ? (
            <>
              <div style={styles.small}>
                {`Suggested artifact | ${String(resolvedSuggestedArtifact?.display_name || normalizedSuggestedArtifactId)}`}
              </div>
              <div style={styles.small}>
                {compatibleToolTargetIds.includes(String(targetId || "").trim())
                  ? "The suggested artifact is compatible with this tool and will be preselected."
                  : artifactPicker
                    ? "The suggested artifact is not compatible with this tool."
                    : "Selected artifact has no compatible tool binding in the current inventory."}
              </div>
              {suggestedArtifactCompatibility?.reasons?.map((reason) => (
                <div key={reason} style={styles.small}>
                  {reason}
                </div>
              ))}
            </>
          ) : null}
          {selectedMetaLines(selected, commandKind).map((line) => (
            <div key={line} style={styles.small}>
              {line}
            </div>
          ))}
          {anyOf.length > 0 ? (
            <div style={styles.small}>
              {`One of these argument groups is required: ${anyOf
                .map((condition) => (Array.isArray(condition?.required) ? condition.required.join(", ") : ""))
                .filter(Boolean)
                .join(" or ")}`}
            </div>
          ) : null}
          <div style={{ marginTop: 12 }}>
            <div style={styles.label}>Required arguments</div>
            {requiredEntries.length > 0 ? (
              <div style={styles.formGrid}>{requiredEntries.map(renderField)}</div>
            ) : (
              <div style={styles.small}>No required arguments.</div>
            )}
          </div>
          {optionalEntries.length > 0 ? (
            <div style={{ marginTop: 12 }}>
              <button
                type="button"
                style={styles.secondaryButton}
                onClick={() => setShowOptionalFields((prev) => !prev)}
              >
                {showOptionalFields ? `Hide optional arguments (${optionalEntries.length})` : `Optional arguments (${optionalEntries.length})`}
              </button>
              {showOptionalFields ? <div style={{ ...styles.formGrid, marginTop: 12 }}>{optionalEntries.map(renderField)}</div> : null}
            </div>
          ) : null}
        </>
      ) : null}

      {error && <div style={styles.error}>{error}</div>}

      <div style={styles.actionRow}>
        <button
          type="button"
          style={styles.button}
          onClick={handleSubmit}
          disabled={(commandKind !== "agent" && !selected) || submitting || (commandKind === "agent" && uploadBusy)}
        >
          {submitting ? "Running..." : "Run"}
        </button>
      </div>
    </section>
  );
}
