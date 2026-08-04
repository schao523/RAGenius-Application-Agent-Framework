import React from "react";

export default function AppSidebar({
  applications,
  selectedAppId,
  setSelectedAppId,
  appInfo,
  appError,
  refreshApp,
  sessionId,
  userId,
  setUserId,
  baseUrl,
  setBaseUrl,
  builderBaseUrl,
  setBuilderBaseUrl,
  builderAvailable,
  newSession,
  sessions,
  currentSessionId,
  onSelectSession,
  currentSessionTitle,
  sessionTitleDraft,
  setSessionTitleDraft,
  saveSessionTitle,
  savingSessionTitle,
  sessionSearch,
  setSessionSearch,
  includeArchivedSessions,
  setIncludeArchivedSessions,
  togglePinnedSession,
  archiveSession,
  deleteSession,
  actingSessionId,
  styles,
  safeCount,
  shortenPreview,
  workflowStatusLabel,
  formatWhen,
}) {
  const readyCount = safeCount(appInfo?.documents?.filter((doc) => doc.status === "ready"));

  return (
    <aside style={styles.sidebarRail}>
      <div style={styles.sidebarTop}>
        <div>
          <div style={styles.sidebarBrand}>RAGenius</div>
          <div style={styles.sidebarSubbrand}>Applications</div>
        </div>
        <button style={styles.sidebarPrimaryButton} onClick={newSession}>
          New Chat
        </button>
      </div>

      <section style={styles.sidebarSection}>
        <div style={styles.sidebarSectionHeader}>
          <div style={styles.sidebarSectionTitle}>Applications</div>
          <span style={styles.small}>{applications.length}</span>
        </div>
        <div style={styles.sidebarAppList}>
          {applications.map((app) => {
            const isSelected = app.id === selectedAppId;
            return (
              <button
                key={app.id}
                style={styles.sidebarAppItem(isSelected)}
                onClick={() => setSelectedAppId(app.id)}
              >
                <strong>{app.name}</strong>
                {isSelected && <div style={styles.small}>{app.description || app.slug || app.id}</div>}
              </button>
            );
          })}
          {applications.length === 0 && (
            <div style={styles.sidebarEmptyState}>No applications returned by the backend.</div>
          )}
        </div>
        <div style={{ ...styles.row, marginTop: 10 }}>
          <button style={styles.secondaryButton} onClick={refreshApp} disabled={!selectedAppId}>
            Load
          </button>
          <span style={styles.small}>{appInfo?.name || "No app loaded"}</span>
        </div>
        {appInfo && (
          <div style={styles.sidebarMetaCard}>
            <div style={styles.row}>
              <span style={styles.pill}>{appInfo.slug || "n/a"}</span>
              <span style={styles.pill}>Docs {safeCount(appInfo.documents)}</span>
              <span style={styles.pill}>Ready {readyCount}</span>
            </div>
            <div style={{ ...styles.small, marginTop: 8, lineHeight: 1.5 }}>
              {appInfo.description || "No description stored in builder."}
            </div>
          </div>
        )}
      </section>

      <div style={styles.sidebarDivider} />

      <section style={styles.sidebarSection}>
        <div style={styles.sidebarSectionHeader}>
          <div style={styles.sidebarSectionTitle}>Sessions</div>
          <span style={styles.small}>{sessions.length}</span>
        </div>
        <input
          style={styles.sidebarInput}
          value={sessionSearch}
          onChange={(e) => setSessionSearch(e.target.value)}
          placeholder="Search sessions"
        />
        <label style={{ ...styles.small, display: "block", marginTop: 10 }}>
          <input
            type="checkbox"
            checked={includeArchivedSessions}
            onChange={(e) => setIncludeArchivedSessions(e.target.checked)}
            style={{ marginRight: 8 }}
          />
          Show archived
        </label>
        <div style={styles.sidebarSessionList}>
          {Array.isArray(sessions) && sessions.length > 0 ? (
            sessions.map((session) => {
              const isSelected = session.id === currentSessionId;
              return (
                <div key={session.id} style={styles.sidebarSessionItem(isSelected)}>
                  <button
                    style={styles.sidebarSessionButton}
                    onClick={() => onSelectSession(session.id)}
                  >
                    <div style={styles.sidebarSessionTitleRow}>
                      <strong>{session.title || "Untitled chat"}</strong>
                      {isSelected && <span style={styles.pill}>Open</span>}
                    </div>
                    {isSelected && (
                      <>
                        {workflowStatusLabel(session.workflow_status) && (
                          <div style={styles.small}>Stage: {workflowStatusLabel(session.workflow_status)}</div>
                        )}
                        <div style={styles.small}>{formatWhen(session.last_message_at || session.created_at)}</div>
                      </>
                    )}
                  </button>
                  {isSelected && (
                    <div style={styles.sidebarSessionActions}>
                      <button
                        style={styles.sidebarMiniButton}
                        onClick={() => togglePinnedSession(session)}
                        disabled={actingSessionId === session.id}
                      >
                        {session.pinned ? "Unpin" : "Pin"}
                      </button>
                      <button
                        style={styles.sidebarMiniButton}
                        onClick={() => archiveSession(session)}
                        disabled={actingSessionId === session.id}
                      >
                        {session.archived ? "Unarchive" : "Archive"}
                      </button>
                      <button
                        style={styles.sidebarMiniButton}
                        onClick={() => deleteSession(session)}
                        disabled={actingSessionId === session.id}
                      >
                        Delete
                      </button>
                    </div>
                  )}
                </div>
              );
            })
          ) : (
            <div style={styles.sidebarEmptyState}>No sessions yet.</div>
          )}
        </div>
      </section>

      <div style={styles.sidebarDivider} />

      <section style={styles.sidebarSection}>
        <div style={styles.sidebarSectionTitle}>Profile</div>
        <input
          style={styles.sidebarInput}
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
          placeholder="user1"
        />
        {currentSessionTitle !== undefined && (
          <div style={{ marginTop: 10 }}>
            <input
              style={styles.sidebarInput}
              value={sessionTitleDraft}
              onChange={(e) => setSessionTitleDraft(e.target.value)}
              placeholder={currentSessionTitle || "Untitled chat"}
            />
            <button
              style={{ ...styles.secondaryButton, marginTop: 10 }}
              onClick={saveSessionTitle}
              disabled={savingSessionTitle || !selectedAppId}
            >
              {savingSessionTitle ? "Saving..." : "Save Title"}
            </button>
          </div>
        )}
      </section>

      <details style={styles.sidebarDetails}>
        <summary style={styles.summary}>Advanced</summary>
        <div style={styles.sidebarSection}>
          <div style={styles.sidebarSectionTitle}>API Base URL</div>
          <input style={styles.sidebarInput} value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
          <div style={styles.sidebarSectionTitle}>Builder URL</div>
          <input style={styles.sidebarInput} value={builderBaseUrl} onChange={(e) => setBuilderBaseUrl(e.target.value)} />
          <div style={builderAvailable ? styles.small : styles.offlineNote}>
            {builderAvailable ? "Builder online" : "Builder offline"}
          </div>
          <div style={styles.sidebarSectionTitle}>Session ID</div>
          <input style={styles.sidebarInput} value={sessionId} readOnly />
        </div>
      </details>

      {appError && <div style={styles.error}>{appError}</div>}
    </aside>
  );
}
