import React from "react";

export default function AdminPanels({
  styles,
  adminTabs,
  adminTab,
  setAdminTab,
  children,
}) {
  return (
    <details style={styles.adminShell}>
      <summary style={styles.summary}>Admin Panels</summary>
      <div style={{ ...styles.small, marginTop: 10, lineHeight: 1.6 }}>
        Builder and runtime diagnostics stay available here, but the default user path remains chat-first.
      </div>
      <div style={{ ...styles.tabRow, marginTop: 12, marginBottom: 12 }}>
        {adminTabs.map(([id, label]) => (
          <button key={id} style={styles.tabBtn(adminTab === id)} onClick={() => setAdminTab(id)}>
            {label}
          </button>
        ))}
      </div>
      {children}
    </details>
  );
}
