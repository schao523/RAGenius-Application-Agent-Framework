import React, { useEffect, useState } from "react";

function isUnavailable(interaction) {
  if (!interaction || interaction.state !== "pending") return true;
  const expiresAt = Date.parse(String(interaction.expires_at || ""));
  return Number.isFinite(expiresAt) && expiresAt <= Date.now();
}

export default function AgentInteractionCard({
  interaction,
  onRespond,
  onLaunch,
  onCancel,
  onRefresh,
  submitting = false,
  error = "",
  styles,
}) {
  const [text, setText] = useState("");
  const [selectedOptions, setSelectedOptions] = useState([]);
  const unavailable = isUnavailable(interaction);

  useEffect(() => {
    setText("");
    setSelectedOptions([]);
  }, [interaction?.interaction_id, interaction?.version]);

  if (!interaction) return null;

  const disabled = unavailable || submitting;
  const presentation = interaction.presentation || {};
  const toggleOption = (optionId) => {
    setSelectedOptions((current) => (
      current.includes(optionId)
        ? current.filter((value) => value !== optionId)
        : [...current, optionId]
    ));
  };

  return (
    <section
      aria-label="Agent interaction required"
      style={{
        marginTop: 14,
        padding: 16,
        borderRadius: 16,
        border: "1px solid #d97706",
        background: "linear-gradient(135deg, #fff7ed 0%, #fffbeb 100%)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <strong>Agent needs your input</strong>
          <div style={styles?.compactNote}>Type: {String(interaction.type || "interaction").replace(/_/g, " ")}</div>
        </div>
        <span style={{ ...(styles?.pill || {}), ...(styles?.statusWarn || {}) }}>
          {interaction.state || "pending"}
        </span>
      </div>
      <p style={{ margin: "12px 0", whiteSpace: "pre-wrap" }}>{interaction.prompt}</p>

      {interaction.type === "approval" && (
        <div>
          <div style={styles?.compactNote}>Approval applies once to this pending action.</div>
          <div style={styles?.row}>
            <button
              type="button"
              style={styles?.button}
              disabled={disabled}
              onClick={() => onRespond?.({ kind: "approval", decision: "allow_once" })}
            >
              Allow once
            </button>
            <button
              type="button"
              style={styles?.secondaryButton}
              disabled={disabled}
              onClick={() => onRespond?.({ kind: "approval", decision: "deny" })}
            >
              Deny
            </button>
          </div>
        </div>
      )}

      {interaction.type === "clarification" && (
        <div>
          <label htmlFor={`interaction-${interaction.interaction_id}`}>Your response</label>
          <textarea
            id={`interaction-${interaction.interaction_id}`}
            aria-label="Your response"
            style={{ ...(styles?.input || {}), display: "block", width: "100%", minHeight: 84, marginTop: 6 }}
            value={text}
            maxLength={8000}
            disabled={disabled}
            onChange={(event) => setText(event.target.value)}
          />
          <button
            type="button"
            style={{ ...(styles?.button || {}), marginTop: 10 }}
            disabled={disabled || !text.trim()}
            onClick={() => onRespond?.({ kind: "clarification", text: text.trim() })}
          >
            Submit response
          </button>
        </div>
      )}

      {interaction.type === "selection" && (
        <div>
          {(interaction.options || []).map((option) => (
            <label key={option.id} style={{ display: "block", marginBottom: 8 }}>
              <input
                type="checkbox"
                checked={selectedOptions.includes(option.id)}
                disabled={disabled}
                onChange={() => toggleOption(option.id)}
              />{" "}{option.label}
              {option.description ? ` - ${option.description}` : ""}
            </label>
          ))}
          <button
            type="button"
            style={styles?.button}
            disabled={disabled || selectedOptions.length === 0}
            onClick={() => onRespond?.({ kind: "selection", option_ids: selectedOptions })}
          >
            Submit selection
          </button>
        </div>
      )}

      {["authentication_handoff", "user_action_required"].includes(interaction.type) && (
        <div>
          {interaction.type === "authentication_handoff" && (
            <>
              <div style={styles?.compactNote}>
                Target: {presentation.target_label || "Approved provider"}
                {presentation.target_host ? ` (${presentation.target_host})` : ""}
              </div>
              <div style={{ ...styles?.compactNote, marginTop: 6 }}>
                Enter credentials, one-time codes, and recovery codes only in the provider window. Never enter them in RAGenius.
              </div>
            </>
          )}
          {interaction.type === "user_action_required" && presentation.completion_label && (
            <div style={styles?.compactNote}>{presentation.completion_label}</div>
          )}
          <div style={{ ...(styles?.row || {}), marginTop: 10 }}>
            {interaction.type === "authentication_handoff" && presentation.launch_available && (
              <button type="button" style={styles?.button} disabled={disabled} onClick={onLaunch}>
                Open sign-in
              </button>
            )}
            <button
              type="button"
              style={styles?.button}
              disabled={disabled}
              onClick={() => onRespond?.({ kind: "user_action", outcome: "completed" })}
            >
              {presentation.completion_label || "I completed this step"}
            </button>
            <button
              type="button"
              style={styles?.secondaryButton}
              disabled={disabled}
              onClick={() => onRespond?.({ kind: "user_action", outcome: "cancelled" })}
            >
              Cancel step
            </button>
          </div>
        </div>
      )}

      <div style={{ ...(styles?.row || {}), marginTop: 12 }}>
        {onCancel && (
          <button type="button" style={styles?.secondaryButton} disabled={submitting} onClick={onCancel}>
            Cancel execution
          </button>
        )}
        {onRefresh && (
          <button type="button" style={styles?.secondaryButton} disabled={submitting} onClick={onRefresh}>
            Refresh interaction
          </button>
        )}
      </div>
      {unavailable && <div style={styles?.compactNote}>This interaction is no longer pending. Refresh to load current state.</div>}
      {error && <div style={styles?.error}>{error}</div>}
    </section>
  );
}
