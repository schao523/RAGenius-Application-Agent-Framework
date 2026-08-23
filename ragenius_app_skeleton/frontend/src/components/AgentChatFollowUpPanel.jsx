import React, { useEffect, useRef, useState } from "react";

function latestTurnPrompt(chatSession) {
  const turns = Array.isArray(chatSession?.turns) ? [...chatSession.turns].reverse() : [];
  return turns
    .map((turn) => String(turn?.result?.output_text || "").trim())
    .find(Boolean) || "";
}

function numberedChoices(prompt) {
  if (!/\b(?:choose|pick|select|reply)\b/i.test(prompt)) return [];
  const choices = String(prompt || "")
    .split(/\r?\n/)
    .map((line) => line.match(/^\s*(\d{1,2})[.)]\s+(.+?)\s*$/))
    .filter(Boolean)
    .map((match) => ({
      label: match[2].replace(/\*\*|__|`/g, "").trim(),
      value: match[1],
    }));
  return choices.length >= 2 ? choices.slice(0, 9) : [];
}

export default function AgentChatFollowUpPanel({
  chatSession,
  error = "",
  onCancel,
  onEnd,
  onFollowUp,
  prompt = "",
  submitting = false,
  styles,
}) {
  const [text, setText] = useState("");
  const finalizedSummaryRef = useRef("");
  const ready = chatSession?.state === "ready_for_follow_up";
  const running = chatSession?.state === "running";
  const displayedPrompt = latestTurnPrompt(chatSession)
    || String(chatSession?.latest_output_text || prompt || "").trim();
  const choices = numberedChoices(displayedPrompt);
  const latestTurn = Array.isArray(chatSession?.turns) && chatSession.turns.length > 0
    ? chatSession.turns[chatSession.turns.length - 1]
    : null;
  const summarized = ready && latestTurn?.kind === "graceful_cancel";
  const summarizedTurnKey = summarized
    ? String(latestTurn.chat_turn_id || latestTurn.sequence || chatSession.session_version || "summary")
    : "";
  useEffect(() => {
    if (!summarizedTurnKey || finalizedSummaryRef.current === summarizedTurnKey || !onEnd) return;
    finalizedSummaryRef.current = summarizedTurnKey;
    onEnd({ persistFinalOutput: true });
  }, [onEnd, summarizedTurnKey]);
  if (!chatSession || (!ready && !running)) return null;
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
      {ready && displayedPrompt && (
        <div
          aria-label="OpenClaw question"
          style={{
            ...styles.compactNote,
            marginTop: 10,
            maxHeight: "min(24vh, 220px)",
            overflowY: "auto",
            overflowX: "hidden",
            overflowWrap: "anywhere",
            overscrollBehavior: "contain",
            paddingRight: 8,
            scrollbarGutter: "stable",
            whiteSpace: "pre-wrap",
          }}
        >
          {displayedPrompt}
        </div>
      )}
      {ready && !summarized && choices.length > 0 && (
        <div aria-label="OpenClaw choices" style={{ ...styles.row, marginTop: 10 }}>
          {choices.map((choice) => (
            <button
              key={choice.value}
              disabled={submitting}
              onClick={() => setText(choice.value)}
              style={styles.secondaryButton}
              type="button"
            >
              {choice.value}. {choice.label}
            </button>
          ))}
        </div>
      )}
      {summarized && (
        <div style={{ ...styles.row, marginTop: 10 }}>
          <button
            disabled={submitting}
            onClick={() => onEnd?.({ persistFinalOutput: true })}
            style={styles.primaryButton}
            type="button"
          >
            Finish and close
          </button>
        </div>
      )}
      {ready && !summarized && (
        <>
          <textarea
            aria-label="OpenClaw follow-up"
            disabled={submitting}
            onChange={(event) => setText(event.target.value)}
            placeholder="Reply with a selection, clarification, or revision request."
            rows={2}
            style={{ ...styles.input, marginTop: 8, width: "100%" }}
            value={text}
          />
          <div style={{ ...styles.row, marginTop: 8 }}>
            <button disabled={submitting || !text.trim()} onClick={() => submitText("reply")} style={styles.primaryButton} type="button">Reply</button>
            <button disabled={submitting} onClick={() => onFollowUp?.({ kind: "continue" })} style={styles.secondaryButton} type="button">Continue without reply</button>
            <button disabled={submitting || !text.trim()} onClick={() => submitText("revise")} style={styles.secondaryButton} type="button">Revise</button>
            <button disabled={submitting} onClick={() => onFollowUp?.({ kind: "graceful_cancel" })} style={styles.secondaryButton} type="button">Stop and summarize</button>
            <button disabled={submitting} onClick={onEnd} style={styles.secondaryButton} type="button">Cancel interaction</button>
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
