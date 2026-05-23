import React from "react";

export default function ChatMessageCard({
  message,
  index,
  styles,
  assistantType,
  turnIntentLabel,
  generationSummary,
  primaryScopeSummary,
  sourceSummary,
  retrievalBypassSummary,
  evidenceNote,
  onOpenInspector,
  onOpenSources,
}) {
  const isAssistant = message.role === "assistant";
  const assistantTypeLabel =
    assistantType && typeof assistantType === "object" ? assistantType.label : assistantType;
  const assistantTypeStyle =
    assistantType && typeof assistantType === "object" && assistantType.style
      ? assistantType.style
      : styles.pill;
  const evidenceNoteText =
    evidenceNote && typeof evidenceNote === "object" ? evidenceNote.text : evidenceNote;
  const evidenceNoteStyle =
    evidenceNote && typeof evidenceNote === "object" && evidenceNote.style
      ? evidenceNote.style
      : styles.compactNote;

  return (
    <div style={styles.messageCard(message.role)}>
      <div style={styles.assistantMetaRow}>
        <span style={styles.messageRoleLabel}>{isAssistant ? "Assistant" : "You"}</span>
        {isAssistant && assistantTypeLabel && <span style={assistantTypeStyle}>{assistantTypeLabel}</span>}
        {isAssistant && turnIntentLabel && <span style={styles.pill}>Intent: {turnIntentLabel}</span>}
        {isAssistant && generationSummary && <span style={styles.pill}>{generationSummary}</span>}
        {isAssistant && primaryScopeSummary && <span style={styles.pill}>Scope: {primaryScopeSummary}</span>}
        {isAssistant && sourceSummary && <span style={styles.pill}>{sourceSummary}</span>}
        {isAssistant && retrievalBypassSummary && <span style={{ ...styles.pill, ...styles.statusWarn }}>{retrievalBypassSummary}</span>}
      </div>
      <div style={styles.messageBodyText}>{message.content}</div>
      {isAssistant && (
        <>
          {evidenceNoteText && <div style={evidenceNoteStyle}>{evidenceNoteText}</div>}
          <div style={styles.actionRow}>
            <button style={styles.inlineActionButton} onClick={() => onOpenInspector(index)}>
              Inspect
            </button>
            <button style={styles.inlineActionButton} onClick={() => onOpenSources(index)}>
              Sources
            </button>
          </div>
        </>
      )}
    </div>
  );
}
