import React, { useState } from "react";

export default function AgentChatFollowUpPanel({
  chatSession,
  error = "",
  onCancel,
  onEnd,
  onFollowUp,
  submitting = false,
  styles,
}) {
  const [text, setText] = useState("");
  if (!chatSession) return null;
  const ready = chatSession.state === "ready_for_follow_up";
  const running = chatSession.state === "running";
  const submitText = (kind) => {
    const value = text.trim();
    if (!value || !onFollowUp) return;
    onFollowUp({ kind, text: value });
  };

  return (
    <section aria-label="OpenClaw chat continuation" style={{ marginTop: 14 }}>
      <div style={styles.sidebarSectionTitle}>OpenClaw follow-up</div>
      <div style={styles.compactNote}>
        Each follow-up starts a new Agent run in the same OpenClaw session. It is ordinary chat input, not a typed approval.
      </div>
      {ready && (
        <>
          <textarea
            aria-label="OpenClaw follow-up"
            disabled={submitting}
            onChange={(event) => setText(event.target.value)}
            placeholder="Reply with a selection, clarification, or revision request."
            rows={3}
            style={{ ...styles.input, marginTop: 8, width: "100%" }}
            value={text}
          />
          <div style={{ ...styles.row, marginTop: 8 }}>
            <button disabled={submitting || !text.trim()} onClick={() => submitText("reply")} style={styles.primaryButton} type="button">Reply</button>
            <button disabled={submitting} onClick={() => onFollowUp?.({ kind: "continue" })} style={styles.secondaryButton} type="button">Continue</button>
            <button disabled={submitting || !text.trim()} onClick={() => submitText("revise")} style={styles.secondaryButton} type="button">Revise</button>
            <button disabled={submitting} onClick={() => onFollowUp?.({ kind: "graceful_cancel" })} style={styles.secondaryButton} type="button">Graceful cancel</button>
            <button disabled={submitting} onClick={onEnd} style={styles.secondaryButton} type="button">End session</button>
          </div>
        </>
      )}
      {running && (
        <div style={{ ...styles.row, marginTop: 8 }}>
          <span style={styles.compactNote}>The current follow-up run is active.</span>
          <button disabled={submitting} onClick={onCancel} style={styles.secondaryButton} type="button">Cancel current run</button>
        </div>
      )}
      {error && <div style={styles.errorText}>{error}</div>}
    </section>
  );
}
