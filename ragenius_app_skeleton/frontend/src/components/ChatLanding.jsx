import React from "react";

export default function ChatLanding({
  appName,
  starterQuestions,
  styles,
  loading,
  appId,
  compileRequiredMessage,
  onSelectStarterQuestion,
}) {
  return (
    <div style={styles.landingShell}>
      <div style={styles.landingInner}>
        <div style={styles.landingAvatar}>{(appName || "A").slice(0, 1).toUpperCase()}</div>
        <h2 style={styles.landingTitle}>{appName || "Application chat"}</h2>
        <div style={styles.landingByline}>LLM-first application runtime</div>
        <p style={styles.landingSubtitle}>
          {appName
            ? `Start a new conversation with ${appName}. Runtime planning, resource loading, and hidden execution state stay behind the chat surface.`
            : "Select and load an application first. The conversation shell stays clean while the runtime remains inspectable on demand."}
        </p>
        {compileRequiredMessage ? (
          <div style={styles.fallbackNote}>
            {compileRequiredMessage}
          </div>
        ) : null}
        {Array.isArray(starterQuestions) && starterQuestions.filter(Boolean).length > 0 && (
          <div style={styles.starterGrid}>
            {starterQuestions.filter(Boolean).slice(0, 4).map((question, index) => (
              <button
                key={`${question}-${index}`}
                style={styles.starterCardCompact}
                onClick={() => onSelectStarterQuestion(question)}
                disabled={loading || !appId || Boolean(compileRequiredMessage)}
              >
                {question}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
