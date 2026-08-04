import React, { useState } from "react";

function formatPreview(value, maxLength = 180) {
  const normalized = String(value || "").replace(/\s+/g, " ").trim();
  if (!normalized) {
    return "";
  }
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength - 1)}...` : normalized;
}

function formatApprovedAt(value) {
  const text = String(value || "").trim();
  if (!text) {
    return "";
  }
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) {
    return text;
  }
  const yyyy = date.getUTCFullYear();
  const mm = String(date.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(date.getUTCDate()).padStart(2, "0");
  const hh = String(date.getUTCHours()).padStart(2, "0");
  const mi = String(date.getUTCMinutes()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${hh}:${mi} UTC`;
}

export default function ApprovedContentPanel({
  approvedContent,
  selectedApprovedContentId,
  onSelectApprovedContent,
  latestAssistantMessage,
  onApproveLatest,
  approving,
  styles,
}) {
  const [showSelectedDetails, setShowSelectedDetails] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [showLegacyPanel, setShowLegacyPanel] = useState(false);
  const items = Array.isArray(approvedContent) ? approvedContent : [];
  const latest = items.length > 0 ? items[items.length - 1] : null;
  const selected =
    items.find((item) => item.approved_content_id === selectedApprovedContentId)
    || latest
    || null;
  const recentItems = [...items].reverse().slice(0, 5);

  if (items.length > 0 && !showLegacyPanel) {
    return (
      <section style={styles.approvedContentShell}>
        <div style={styles.approvedContentHeader}>
          <div>
            <div style={styles.sidebarSectionTitle}>Legacy Approved Content</div>
            <div style={styles.small}>
              A legacy approved revision is selected for older @exec flows. Artifact reuse is the primary path.
            </div>
          </div>
          <button
            type="button"
            style={styles.secondaryButton}
            onClick={() => setShowLegacyPanel(true)}
          >
            Show Legacy Approved Content
          </button>
        </div>
      </section>
    );
  }

  return (
    <section style={styles.approvedContentShell}>
      <div style={styles.approvedContentHeader}>
        <div>
          <div style={styles.sidebarSectionTitle}>{items.length > 0 ? "Legacy Approved Content" : "Approved Content"}</div>
          <div style={styles.small}>
            {selected
              ? `Selected revision: ${selected.revision_id || selected.approved_content_id}`
              : "No approved revision selected yet."}
          </div>
        </div>
        <div style={styles.row}>
          {selected && (
            <button
              style={styles.secondaryButton}
              onClick={() => setShowSelectedDetails((value) => !value)}
              type="button"
            >
              {showSelectedDetails ? "Hide Details" : "Details"}
            </button>
          )}
          {recentItems.length > 1 && (
            <button
              style={styles.secondaryButton}
              onClick={() => setShowHistory((value) => !value)}
              type="button"
            >
              {showHistory ? "Hide History" : "History"}
            </button>
          )}
          <button
            style={styles.secondaryButton}
            onClick={onApproveLatest}
            disabled={!latestAssistantMessage || approving}
          >
            {approving ? "Approving..." : "Approve Latest Reply"}
          </button>
        </div>
      </div>
      {selected ? (
        <>
          <div style={styles.row}>
            <span style={styles.pill}>{selected.revision_id || selected.approved_content_id}</span>
            <span style={{ ...styles.pill, ...styles.statusOk }}>Legacy selected for @exec</span>
            {selected.approved_content_id === latest?.approved_content_id && (
              <span style={styles.pill}>Latest</span>
            )}
            {items.length > 1 && (
              <span style={styles.pill}>{items.length} revisions</span>
            )}
          </div>
          {showSelectedDetails && (
        <div style={styles.approvedContentCard}>
          <div style={styles.approvedContentMeta}>
            {selected.created_at && <span>Approved {formatApprovedAt(selected.created_at)}</span>}
            {selected.source_message_id && <span>Source message: {selected.source_message_id}</span>}
          </div>
          <div style={styles.compactNote}>{formatPreview(selected.content_text)}</div>
        </div>
          )}
        </>
      ) : (
        <div style={styles.compactNote}>
          Approve a reviewed assistant reply before using `@exec skill ...` without explicit instructions.
        </div>
      )}
      {showHistory && recentItems.length > 1 && (
        <div style={styles.approvedContentList}>
          {recentItems.map((item) => {
            const isSelected = item.approved_content_id === selectedApprovedContentId;
            return (
              <div
                key={item.approved_content_id}
                style={styles.approvedContentListItem(isSelected)}
              >
                <div style={styles.row}>
                  <span style={styles.pill}>{item.revision_id || item.approved_content_id}</span>
                  {isSelected && <span style={{ ...styles.pill, ...styles.statusOk }}>Legacy selected</span>}
                  {item.approved_content_id === latest?.approved_content_id && (
                    <span style={styles.pill}>Latest</span>
                  )}
                </div>
                <div style={styles.approvedContentMeta}>
                  {item.created_at && <span>Approved {formatApprovedAt(item.created_at)}</span>}
                  {item.source_message_id && <span>Source message: {item.source_message_id}</span>}
                </div>
                <div style={styles.compactNote}>{formatPreview(item.content_text, 120)}</div>
                <button
                  style={styles.secondaryButton}
                  onClick={() => onSelectApprovedContent?.(item.approved_content_id)}
                  disabled={isSelected}
                >
                  {isSelected ? "Selected" : "Use for @exec"}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
