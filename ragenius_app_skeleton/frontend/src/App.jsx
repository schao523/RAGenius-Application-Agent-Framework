import React, { useEffect, useMemo, useRef, useState } from "react";
import AdminPanels from "./components/AdminPanels";
import AppSidebar from "./components/AppSidebar";
import ChatLanding from "./components/ChatLanding";
import ChatMessageCard from "./components/ChatMessageCard";
import DocumentsPanel from "./components/DocumentsPanel";
import InstructionsPanel from "./components/InstructionsPanel";
import RuntimeInspector from "./components/RuntimeInspector";
import RuntimePanel from "./components/RuntimePanel";
import SessionHeader from "./components/SessionHeader";

const DEFAULT_BASE_URL = import.meta.env.VITE_APP_BASE_URL || "http://127.0.0.1:8000";
const DEFAULT_BUILDER_BASE_URL = "http://127.0.0.1:5000";

const styles = {
  page: {
    minHeight: "100vh",
    background: "linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%)",
    color: "#1f2937",
    fontFamily: "'Trebuchet MS', 'Segoe UI', sans-serif",
    padding: 16,
  },
  shell: {
    maxWidth: 1440,
    margin: "0 auto",
  },
  shellLayout: {
    display: "grid",
    gridTemplateColumns: "300px minmax(0, 1fr)",
    gap: 18,
    alignItems: "start",
  },
  sidebarRail: {
    position: "sticky",
    top: 16,
    display: "grid",
    gap: 14,
    maxHeight: "calc(100vh - 32px)",
    overflowY: "auto",
    padding: 18,
    borderRadius: 24,
    background: "linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)",
    border: "1px solid rgba(148,163,184,0.24)",
    boxShadow: "0 18px 40px rgba(15,23,42,0.08)",
  },
  sidebarTop: {
    display: "grid",
    gap: 10,
  },
  sidebarBrand: {
    fontSize: 28,
    fontWeight: 800,
    color: "#0f172a",
  },
  sidebarSubbrand: {
    fontSize: 12,
    textTransform: "uppercase",
    letterSpacing: 1.1,
    color: "#64748b",
    marginTop: 4,
  },
  sidebarPrimaryButton: {
    padding: "12px 16px",
    borderRadius: 999,
    border: "1px solid #0f766e",
    background: "linear-gradient(135deg, #0f766e 0%, #0ea5e9 100%)",
    color: "#fff",
    fontWeight: 800,
    cursor: "pointer",
  },
  sidebarSection: {
    display: "grid",
    gap: 10,
  },
  sidebarDivider: {
    height: 1,
    background: "linear-gradient(90deg, rgba(203,213,225,0) 0%, rgba(203,213,225,0.9) 18%, rgba(203,213,225,0.9) 82%, rgba(203,213,225,0) 100%)",
  },
  sidebarSectionTitle: {
    fontSize: 12,
    fontWeight: 800,
    letterSpacing: 1,
    textTransform: "uppercase",
    color: "#64748b",
  },
  sidebarSectionHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 8,
  },
  sidebarInput: {
    width: "100%",
    boxSizing: "border-box",
    padding: "10px 12px",
    borderRadius: 12,
    border: "1px solid #cbd5e1",
    background: "#ffffff",
    fontSize: 14,
  },
  sidebarSelect: {
    width: "100%",
    boxSizing: "border-box",
    padding: "10px 12px",
    borderRadius: 12,
    border: "1px solid #cbd5e1",
    background: "#ffffff",
    fontSize: 14,
  },
  sidebarMetaCard: {
    padding: 12,
    borderRadius: 16,
    background: "linear-gradient(180deg, #f8fbff 0%, #eef6ff 100%)",
    border: "1px solid #dbeafe",
  },
  sidebarAppList: {
    display: "grid",
    gap: 8,
    maxHeight: 220,
    overflowY: "auto",
    paddingRight: 4,
  },
  sidebarAppItem: (active) => ({
    padding: "10px 12px",
    borderRadius: 14,
    border: `1px solid ${active ? "#0f766e" : "#dbeafe"}`,
    background: active ? "#ecfeff" : "#ffffff",
    cursor: "pointer",
    textAlign: "left",
    display: "grid",
    gap: 4,
  }),
  sidebarSessionList: {
    display: "grid",
    gap: 10,
    maxHeight: 340,
    overflowY: "auto",
    paddingRight: 4,
  },
  sidebarSessionItem: (active) => ({
    padding: 12,
    borderRadius: 16,
    border: `1px solid ${active ? "#0f766e" : "#dbeafe"}`,
    background: active ? "linear-gradient(180deg, #f0fdfa 0%, #ecfeff 100%)" : "#ffffff",
    display: "grid",
    gap: 8,
  }),
  sidebarSessionButton: {
    background: "transparent",
    border: "none",
    padding: 0,
    textAlign: "left",
    cursor: "pointer",
    display: "grid",
    gap: 6,
  },
  sidebarSessionTitleRow: {
    display: "flex",
    justifyContent: "space-between",
    gap: 8,
    alignItems: "center",
  },
  sidebarSessionActions: {
    display: "flex",
    gap: 6,
    flexWrap: "wrap",
  },
  sidebarMiniButton: {
    padding: "5px 9px",
    borderRadius: 999,
    border: "1px solid #cbd5e1",
    background: "#ffffff",
    color: "#334155",
    fontWeight: 700,
    cursor: "pointer",
    fontSize: 12,
  },
  sidebarEmptyState: {
    padding: 12,
    borderRadius: 14,
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    color: "#64748b",
  },
  sidebarDetails: {
    borderTop: "1px solid #e2e8f0",
    paddingTop: 12,
  },
  mainColumn: {
    display: "grid",
    gap: 18,
  },
  adminShell: {
    borderRadius: 18,
    border: "1px solid #e2e8f0",
    background: "rgba(255,255,255,0.72)",
    padding: 14,
  },
  workspaceShell: {
    display: "grid",
    gap: 18,
  },
  card: {
    background: "rgba(255,255,255,0.92)",
    border: "1px solid rgba(148,163,184,0.22)",
    borderRadius: 20,
    padding: 18,
    boxShadow: "0 18px 40px rgba(15,23,42,0.08)",
  },
  sectionTitle: {
    margin: "0 0 8px 0",
    fontSize: 22,
    color: "#0f172a",
  },
  muted: {
    color: "#475569",
    lineHeight: 1.6,
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "1.2fr 0.95fr",
    gap: 18,
    marginBottom: 18,
  },
  row: {
    display: "flex",
    gap: 10,
    alignItems: "center",
    flexWrap: "wrap",
  },
  formGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
    gap: 12,
    marginTop: 14,
  },
  label: {
    display: "block",
    fontSize: 12,
    fontWeight: 700,
    color: "#334155",
    marginBottom: 6,
    textTransform: "uppercase",
    letterSpacing: 1.1,
  },
  input: {
    width: "100%",
    boxSizing: "border-box",
    padding: "11px 12px",
    borderRadius: 12,
    border: "1px solid #cbd5e1",
    background: "#ffffff",
    fontSize: 14,
  },
  select: {
    width: "100%",
    boxSizing: "border-box",
    padding: "11px 12px",
    borderRadius: 12,
    border: "1px solid #cbd5e1",
    background: "#ffffff",
    fontSize: 14,
  },
  textarea: {
    width: "100%",
    minHeight: 130,
    boxSizing: "border-box",
    padding: "13px 14px",
    borderRadius: 14,
    border: "1px solid #cbd5e1",
    background: "#ffffff",
    fontSize: 15,
    lineHeight: 1.55,
    resize: "vertical",
  },
  button: {
    padding: "10px 16px",
    borderRadius: 999,
    border: "1px solid #0f766e",
    background: "linear-gradient(135deg, #0f766e 0%, #0ea5e9 100%)",
    color: "#fff",
    fontWeight: 700,
    cursor: "pointer",
  },
  secondaryButton: {
    padding: "10px 16px",
    borderRadius: 999,
    border: "1px solid #94a3b8",
    background: "#ffffff",
    color: "#0f172a",
    fontWeight: 700,
    cursor: "pointer",
  },
  starterGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
    gap: 12,
    marginTop: 16,
    marginBottom: 14,
  },
  starterCard: {
    textAlign: "left",
    padding: "14px 16px",
    borderRadius: 16,
    border: "1px solid #bfdbfe",
    background: "linear-gradient(135deg, #f8fbff 0%, #eff6ff 100%)",
    color: "#0f172a",
    fontWeight: 700,
    lineHeight: 1.45,
    cursor: "pointer",
  },
  tabRow: {
    display: "flex",
    gap: 12,
    flexWrap: "wrap",
    marginBottom: 18,
  },
  tabBtn: (active) => ({
    padding: "12px 18px",
    borderRadius: 999,
    border: `1px solid ${active ? "#0f766e" : "#cbd5e1"}`,
    background: active ? "linear-gradient(135deg, #ccfbf1 0%, #dbeafe 100%)" : "#ffffff",
    color: active ? "#0f172a" : "#475569",
    fontWeight: 800,
    cursor: "pointer",
    boxShadow: active ? "0 12px 24px rgba(14,165,233,0.12)" : "none",
  }),
  pill: {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    padding: "6px 9px",
    borderRadius: 999,
    background: "#eff6ff",
    border: "1px solid #bfdbfe",
    fontSize: 11,
    color: "#1d4ed8",
    fontWeight: 700,
  },
  statusOk: {
    color: "#166534",
    background: "#dcfce7",
    border: "1px solid #86efac",
  },
  statusWarn: {
    color: "#92400e",
    background: "#fef3c7",
    border: "1px solid #fcd34d",
  },
  statusErr: {
    color: "#991b1b",
    background: "#fee2e2",
    border: "1px solid #fca5a5",
  },
  metricGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
    gap: 12,
    marginTop: 14,
  },
  metric: {
    padding: 14,
    borderRadius: 16,
    background: "#ffffff",
    border: "1px solid #e2e8f0",
  },
  metricLabel: {
    fontSize: 11,
    textTransform: "uppercase",
    letterSpacing: 1.2,
    color: "#64748b",
    marginBottom: 8,
  },
  metricValue: {
    fontSize: 24,
    fontWeight: 800,
    color: "#0f172a",
  },
  note: {
    padding: "12px 14px",
    borderRadius: 14,
    background: "#f8fafc",
    border: "1px solid #dbeafe",
    color: "#1e3a8a",
    marginTop: 14,
    lineHeight: 1.55,
  },
  offlineNote: {
    padding: "8px 10px",
    borderRadius: 10,
    background: "#fff7ed",
    border: "1px solid #fdba74",
    color: "#9a3412",
    fontSize: 12,
    lineHeight: 1.4,
  },
  sessionList: {
    display: "grid",
    gap: 8,
    marginTop: 14,
  },
  sessionItem: (active) => ({
    display: "flex",
    justifyContent: "space-between",
    gap: 10,
    alignItems: "center",
    padding: "10px 12px",
    borderRadius: 14,
    border: `1px solid ${active ? "#0f766e" : "#dbeafe"}`,
    background: active ? "#ecfeff" : "#ffffff",
    cursor: "pointer",
  }),
  groundedNote: {
    padding: "10px 12px",
    borderRadius: 14,
    background: "#ecfdf5",
    border: "1px solid #86efac",
    color: "#166534",
    marginTop: 14,
    lineHeight: 1.55,
  },
  fallbackNote: {
    padding: "10px 12px",
    borderRadius: 14,
    background: "#fff7ed",
    border: "1px solid #fdba74",
    color: "#9a3412",
    marginTop: 14,
    lineHeight: 1.55,
  },
  messageList: {
    display: "grid",
    gap: 12,
    marginTop: 18,
  },
  workspaceGrid: (inspectorOpen) => ({
    display: "grid",
    gridTemplateColumns: inspectorOpen ? "minmax(0, 1fr) 340px" : "minmax(0, 1fr)",
    gap: 18,
    alignItems: "start",
  }),
  chatStage: {
    display: "grid",
    gap: 16,
  },
  sessionHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 12,
    padding: "12px 14px",
    borderRadius: 18,
    border: "1px solid #dbeafe",
    background: "linear-gradient(135deg, #ffffff 0%, #f8fbff 100%)",
  },
  sessionHeaderTitle: {
    margin: 0,
    fontSize: 24,
    color: "#0f172a",
  },
  sessionHeaderMeta: {
    color: "#475569",
    lineHeight: 1.6,
  },
  landingShell: {
    minHeight: 480,
    display: "grid",
    alignItems: "center",
    padding: "24px 10px 8px",
  },
  landingInner: {
    maxWidth: 760,
    margin: "0 auto",
    textAlign: "center",
  },
  landingAvatar: {
    width: 82,
    height: 82,
    borderRadius: "50%",
    margin: "0 auto 18px",
    display: "grid",
    placeItems: "center",
    background: "radial-gradient(circle at 30% 30%, #fef3c7, #0ea5e9 58%, #0f172a 100%)",
    color: "#ffffff",
    fontSize: 30,
    fontWeight: 800,
    boxShadow: "0 18px 40px rgba(15,23,42,0.18)",
  },
  landingTitle: {
    margin: 0,
    fontSize: 42,
    fontWeight: 800,
    color: "#0f172a",
    lineHeight: 1.08,
  },
  landingByline: {
    marginTop: 10,
    fontSize: 14,
    color: "#64748b",
    textTransform: "uppercase",
    letterSpacing: 1.1,
  },
  landingSubtitle: {
    maxWidth: 720,
    margin: "18px auto 0",
    color: "#334155",
    lineHeight: 1.7,
    fontSize: 18,
  },
  starterCardCompact: {
    textAlign: "left",
    padding: "18px 18px",
    borderRadius: 20,
    border: "1px solid #dbeafe",
    background: "linear-gradient(180deg, #ffffff 0%, #f8fbff 100%)",
    color: "#0f172a",
    fontWeight: 700,
    lineHeight: 1.55,
    cursor: "pointer",
    boxShadow: "0 12px 30px rgba(15,23,42,0.06)",
  },
  actionRow: {
    display: "flex",
    gap: 10,
    alignItems: "center",
    flexWrap: "wrap",
    marginTop: 10,
  },
  inlineActionButton: {
    padding: "6px 10px",
    borderRadius: 999,
    border: "1px solid #cbd5e1",
    background: "#ffffff",
    color: "#334155",
    fontWeight: 700,
    cursor: "pointer",
    fontSize: 12,
  },
  compactNote: {
    marginTop: 8,
    color: "#475569",
    lineHeight: 1.55,
    fontSize: 13,
  },
  inspectorPane: {
    position: "sticky",
    top: 18,
    display: "grid",
    gap: 12,
  },
  inspectorHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 10,
  },
  inspectorTabRow: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap",
  },
  inspectorTab: (active) => ({
    padding: "8px 12px",
    borderRadius: 999,
    border: `1px solid ${active ? "#0f766e" : "#cbd5e1"}`,
    background: active ? "#ecfeff" : "#ffffff",
    color: active ? "#0f172a" : "#475569",
    fontWeight: 700,
    cursor: "pointer",
    fontSize: 12,
  }),
  inspectorSection: {
    padding: 14,
    borderRadius: 16,
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    lineHeight: 1.6,
    display: "grid",
    gap: 10,
  },
  inspectorGroup: {
    padding: "10px 12px",
    borderRadius: 14,
    background: "#ffffff",
    border: "1px solid #e2e8f0",
  },
  inspectorGroupTitle: {
    margin: "0 0 8px 0",
    fontSize: 12,
    fontWeight: 800,
    letterSpacing: 1,
    textTransform: "uppercase",
    color: "#475569",
  },
  inspectorKeyValue: {
    display: "grid",
    gap: 8,
    color: "#334155",
    lineHeight: 1.5,
    fontSize: 14,
  },
  sourceList: {
    margin: 0,
    paddingLeft: 18,
    display: "grid",
    gap: 8,
  },
  transcriptShell: {
    position: "relative",
    marginTop: 18,
  },
  transcriptWrapper: {
    position: "relative",
    marginTop: 18,
  },
  transcript: {
    maxHeight: "60vh",
    minHeight: 320,
    overflowY: "auto",
    paddingRight: 8,
    borderRadius: 18,
    border: "1px solid #dbeafe",
    background: "linear-gradient(180deg, rgba(248,250,252,0.92) 0%, rgba(255,255,255,0.98) 100%)",
    padding: 14,
    boxShadow: "inset 0 1px 0 rgba(255,255,255,0.85)",
    display: "grid",
    gap: 12,
  },
  transcriptPanel: {
    maxHeight: "60vh",
    minHeight: 320,
    overflowY: "auto",
    paddingRight: 8,
    borderRadius: 18,
    border: "1px solid #dbeafe",
    background: "linear-gradient(180deg, rgba(248,250,252,0.92) 0%, rgba(255,255,255,0.98) 100%)",
    padding: 14,
    boxShadow: "inset 0 1px 0 rgba(255,255,255,0.85)",
  },
  composerShell: {
    position: "sticky",
    bottom: 0,
    marginTop: 16,
    paddingTop: 14,
    background: "linear-gradient(180deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.98) 28%, rgba(255,255,255,1) 100%)",
    zIndex: 2,
  },
  scrollLatestButton: {
    position: "absolute",
    right: 18,
    bottom: 18,
    padding: "10px 14px",
    borderRadius: 999,
    border: "1px solid #0f766e",
    background: "rgba(15,118,110,0.92)",
    color: "#ffffff",
    fontWeight: 700,
    cursor: "pointer",
    boxShadow: "0 12px 24px rgba(15,118,110,0.24)",
  },
  debugCode: {
    background: "#0f172a",
    color: "#e2e8f0",
    padding: 12,
    borderRadius: 12,
    whiteSpace: "pre-wrap",
    fontSize: 11,
    overflowX: "auto",
    overflowY: "auto",
    maxHeight: 220,
  },
  messageCard: (role) => ({
    padding: 16,
    borderRadius: 18,
    border: role === "user" ? "1px solid #bfdbfe" : "1px solid #d1fae5",
    background: role === "user" ? "#eff6ff" : "#f0fdf4",
  }),
  code: {
    background: "#0f172a",
    color: "#e2e8f0",
    padding: 14,
    borderRadius: 14,
    whiteSpace: "pre-wrap",
    fontSize: 12,
    overflowX: "auto",
  },
  tableLike: {
    display: "grid",
    gap: 10,
    marginTop: 14,
  },
  docRow: {
    display: "grid",
    gridTemplateColumns: "1.6fr 0.8fr 0.7fr 0.9fr 1fr",
    gap: 12,
    padding: 14,
    borderRadius: 16,
    background: "#ffffff",
    border: "1px solid #e2e8f0",
    alignItems: "start",
  },
  tinyButton: {
    padding: "8px 12px",
    borderRadius: 999,
    border: "1px solid #94a3b8",
    background: "#ffffff",
    color: "#0f172a",
    fontWeight: 700,
    cursor: "pointer",
    fontSize: 12,
  },
  uploadList: {
    display: "grid",
    gap: 8,
    marginTop: 12,
  },
  uploadItem: {
    padding: "10px 12px",
    borderRadius: 14,
    border: "1px solid #dbeafe",
    background: "#f8fafc",
  },
  uploadChipRow: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap",
    marginTop: 10,
  },
  uploadChip: {
    display: "inline-flex",
    alignItems: "center",
    gap: 8,
    padding: "8px 12px",
    borderRadius: 999,
    border: "1px solid #cbd5e1",
    background: "#f8fafc",
    color: "#334155",
    fontSize: 12,
    fontWeight: 700,
  },
  small: {
    fontSize: 12,
    color: "#64748b",
  },
  linkButton: {
    padding: "10px 16px",
    borderRadius: 999,
    border: "1px solid #94a3b8",
    background: "#ffffff",
    color: "#0f172a",
    fontWeight: 700,
    cursor: "pointer",
    fontSize: 12,
    textDecoration: "none",
    display: "inline-flex",
    alignItems: "center",
  },
  disabledLinkButton: {
    padding: "10px 16px",
    borderRadius: 999,
    border: "1px solid #cbd5e1",
    background: "#f8fafc",
    color: "#94a3b8",
    fontWeight: 700,
    cursor: "not-allowed",
    fontSize: 12,
    display: "inline-flex",
    alignItems: "center",
  },
  disabledTinyButton: {
    padding: "7px 10px",
    borderRadius: 999,
    border: "1px solid #cbd5e1",
    background: "#f8fafc",
    color: "#94a3b8",
    fontWeight: 700,
    fontSize: 12,
    display: "inline-flex",
    alignItems: "center",
    cursor: "not-allowed",
  },
  error: {
    color: "#b91c1c",
    marginTop: 12,
    whiteSpace: "pre-wrap",
  },
  details: {
    marginTop: 16,
    borderTop: "1px solid #e2e8f0",
    paddingTop: 12,
  },
  sessionSearch: {
    marginTop: 14,
  },
  summary: {
    cursor: "pointer",
    fontWeight: 700,
    color: "#0f172a",
  },
  assistantMetaRow: {
    display: "flex",
    gap: 8,
    alignItems: "center",
    flexWrap: "wrap",
    marginBottom: 6,
  },
  messageBodyText: {
    whiteSpace: "pre-wrap",
    lineHeight: 1.75,
    color: "#0f172a",
    fontSize: 15,
  },
  messageRoleLabel: {
    fontSize: 12,
    fontWeight: 800,
    color: "#0f172a",
    letterSpacing: 0.3,
  },
  docError: {
    marginTop: 8,
    padding: "8px 10px",
    borderRadius: 12,
    background: "#fef2f2",
    border: "1px solid #fecaca",
    color: "#991b1b",
    fontSize: 12,
    lineHeight: 1.5,
  },
};

async function fetchJson(url, options = {}) {
  const res = await fetch(url, options);
  const text = await res.text();
  if (!res.ok) {
    throw new Error(text || `Request failed ${res.status}`);
  }
  return text ? JSON.parse(text) : {};
}

async function checkUrlReachable(url) {
  try {
    const response = await fetch(url, { method: "GET" });
    return Boolean(response);
  } catch (_error) {
    return false;
  }
}

function safeCount(value) {
  return Array.isArray(value) ? value.length : 0;
}

function formatStatusPill(status) {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "ready" || normalized === "success" || normalized === "ok") {
    return { label: status, style: { ...styles.pill, ...styles.statusOk } };
  }
  if (normalized === "error" || normalized === "failed") {
    return { label: status, style: { ...styles.pill, ...styles.statusErr } };
  }
  return { label: status || "unknown", style: { ...styles.pill, ...styles.statusWarn } };
}

function createSessionId() {
  return `session-${Date.now()}`;
}

function buildThreadKey(appId, sessionId) {
  return `${appId || "no-app"}::${sessionId || "no-session"}`;
}

export function resolveActiveAppDisplay(selectedApp, appInfo, selectedAppId) {
  const selected = selectedApp && selectedApp.id === selectedAppId ? selectedApp : null;
  const detailed = appInfo && appInfo.id === selectedAppId ? appInfo : null;
  return {
    appName: detailed?.name || selected?.name || "",
    starterQuestions: detailed?.starter_questions || selected?.starter_questions || [],
  };
}

export function resolveInstructionUnderstandingState(appInfo) {
  const preview =
    appInfo?.instruction_understanding_preview &&
    typeof appInfo.instruction_understanding_preview === "object"
      ? appInfo.instruction_understanding_preview
      : {};
  const status =
    appInfo?.instruction_understanding_status &&
    typeof appInfo.instruction_understanding_status === "object"
      ? appInfo.instruction_understanding_status
      : {};
  const primaryServiceMode = String(preview.primary_service_mode || "").trim();
  const requiresValidSemanticModel =
    new Set([
      "single_default_workflow",
      "intent_routed_multi_workflow",
      "intent_routed_interaction_logic",
      "hybrid_active",
    ]).has(primaryServiceMode) ||
    Boolean(preview.semantic_compile_attached);
  const compileRequired = Boolean(
    preview.compile_required ||
      !preview.compiled_id ||
      (requiresValidSemanticModel && preview.semantic_compile_valid === false)
  );
  return {
    preview,
    status,
    compileRequired,
    message: compileRequired
      ? "This application has no compiled instruction-understanding model loaded. Go to the Admin panel and run Recompile before starting chat."
      : "",
  };
}

function classifyAssistantTurn(message) {
  const citationCount = Array.isArray(message?.citations) ? message.citations.length : 0;
  const missingCount = Array.isArray(message?.missingInfoTypes) ? message.missingInfoTypes.length : 0;
  const answerSource = String(message?.retrievalSummary?.answer_source || "").toLowerCase();
  const visibleOutputCount = Number(message?.retrievalSummary?.visible_output_count ?? 0);
  if (answerSource.startsWith("direct_")) {
    return { label: "Direct Guide", style: styles.pill };
  }
  if (answerSource.startsWith("fallback_")) {
    return { label: "Fallback", style: { ...styles.pill, ...styles.statusWarn } };
  }
  if (answerSource === "visible_outputs") {
    return { label: "Structured Output", style: styles.pill };
  }
  if (citationCount > 0) {
    return { label: "Grounded", style: { ...styles.pill, ...styles.statusOk } };
  }
  if (answerSource === "llm" || answerSource === "llm_safe") {
    return { label: "LLM", style: styles.pill };
  }
  if (visibleOutputCount > 0) {
    return { label: "Structured Output", style: styles.pill };
  }
  if (missingCount > 0) {
    return { label: "LLM Missing Info", style: { ...styles.pill, ...styles.statusWarn } };
  }
  if (answerSource) {
    return { label: humanizeActionType(answerSource), style: styles.pill };
  }
  return { label: "Answer", style: styles.pill };
}

function normalizeBackendMessages(rows) {
  if (!Array.isArray(rows)) {
    return [];
  }
  return rows.map((row) => {
    const retrievalSummary =
      row.retrievalSummary && typeof row.retrievalSummary === "object"
        ? row.retrievalSummary
        : (row.retrieval_summary && typeof row.retrieval_summary === "object" ? row.retrieval_summary : {});
    return {
      role: row.role,
      content: row.content || "",
      citations: Array.isArray(row.citations) ? row.citations : [],
      missingInfoTypes: Array.isArray(row.missingInfoTypes)
        ? row.missingInfoTypes
        : (Array.isArray(row.missing_info_types) ? row.missing_info_types : []),
      retrievalSummary,
      workflowProgress:
        row.workflow_progress && typeof row.workflow_progress === "object"
          ? row.workflow_progress
          : (retrievalSummary.workflow_progress && typeof retrievalSummary.workflow_progress === "object"
              ? retrievalSummary.workflow_progress
              : {}),
      turnExecutionPlan:
        row.turn_execution_plan && typeof row.turn_execution_plan === "object"
          ? row.turn_execution_plan
          : (retrievalSummary.turn_execution_plan && typeof retrievalSummary.turn_execution_plan === "object"
              ? retrievalSummary.turn_execution_plan
              : {}),
      sessionExecutionState:
        row.session_execution_state && typeof row.session_execution_state === "object"
          ? row.session_execution_state
          : (retrievalSummary.session_execution_state && typeof retrievalSummary.session_execution_state === "object"
              ? retrievalSummary.session_execution_state
              : {}),
      createdAt: row.created_at,
    };
  });
}

function formatWhen(value) {
  if (!value) {
    return "n/a";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

function shortenPreview(value, maxLength = 96) {
  const normalized = String(value || "").replace(/\s+/g, " ").trim();
  if (!normalized) {
    return "No messages yet.";
  }
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength - 3)}...` : normalized;
}

function workflowStatusLabel(workflowStatus) {
  if (!workflowStatus || typeof workflowStatus !== "object") {
    return "";
  }
  const workflowTitle = workflowStatus.workflow_title || workflowStatus.workflowTitle;
  const currentStep = workflowStatus.current_step || workflowStatus.currentStep;
  if (!currentStep) {
    return workflowTitle || "";
  }
  const stepTitle = currentStep.title || `Step ${currentStep.order || "?"}`;
  return workflowTitle ? `${workflowTitle} · ${stepTitle}` : stepTitle;
}

function humanizeActionType(value) {
  const normalized = String(value || "").trim();
  if (!normalized) {
    return "n/a";
  }
  return normalized
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function humanizePresentationMode(value) {
  const normalized = String(value || "").trim();
  if (!normalized) {
    return "n/a";
  }
  return normalized
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function humanizeScope(scope) {
  if (!scope || typeof scope !== "object") {
    return "n/a";
  }
  const title = scope.title || scope.scope_id || scope.id || "n/a";
  const scopeType = scope.scope_type ? humanizeActionType(scope.scope_type) : "";
  return scopeType ? `${scopeType}: ${title}` : title;
}

function summarizePrimaryScope(summary) {
  if (!summary || typeof summary !== "object") {
    return "n/a";
  }
  if (summary.primary_scope && typeof summary.primary_scope === "object") {
    return humanizeScope(summary.primary_scope);
  }
  if (summary.primary_scope_id || summary.primary_scope_type) {
    return [
      summary.primary_scope_type ? humanizeActionType(summary.primary_scope_type) : null,
      summary.primary_scope_id || null,
    ]
      .filter(Boolean)
      .join(": ");
  }
  if (summary.instruction_block_title) {
    const blockType = summary.instruction_block_type
      ? ` (${summary.instruction_block_type})`
      : "";
    return `${summary.instruction_block_title}${blockType}`;
  }
  if (summary.instruction_module_title) {
    return summary.instruction_module_title;
  }
  return "n/a";
}

function summarizeTurnAction(message) {
  const retrievalSummary =
    message?.retrievalSummary && typeof message.retrievalSummary === "object"
      ? message.retrievalSummary
      : {};
  const summaryActionTypes = Array.isArray(retrievalSummary.action_types)
    ? retrievalSummary.action_types.filter((item) => String(item || "").trim())
    : [];
  if (summaryActionTypes.length > 0) {
    const primaryAction = humanizeActionType(summaryActionTypes[0]);
    if (summaryActionTypes.length === 1) {
      return primaryAction;
    }
    return `${primaryAction} +${summaryActionTypes.length - 1}`;
  }
  if (retrievalSummary.primary_action_type) {
    return humanizeActionType(retrievalSummary.primary_action_type);
  }
  const turnExecutionPlan =
    message?.turnExecutionPlan && typeof message.turnExecutionPlan === "object"
      ? message.turnExecutionPlan
      : {};
  const actions = Array.isArray(turnExecutionPlan.actions) ? turnExecutionPlan.actions : [];
  if (actions.length > 0) {
    const primaryAction = humanizeActionType(actions[0]?.action_type);
    if (actions.length === 1) {
      return primaryAction;
    }
    return `${primaryAction} +${actions.length - 1}`;
  }
  return humanizeActionType(retrievalSummary.action_type);
}

function buildAssistantEvidenceNote(message) {
  const citationCount = Array.isArray(message?.citations) ? message.citations.length : 0;
  const retrievalSummary = message?.retrievalSummary || {};
  const answerSource = String(retrievalSummary.answer_source || "").toLowerCase();
  const visibleOutputCount = Number(retrievalSummary.visible_output_count ?? 0);

  if (citationCount > 0) {
    return {
      style: styles.groundedNote,
      text: `Grounded answer based on ${citationCount} cited source${citationCount === 1 ? "" : "s"}.`,
    };
  }
  if (answerSource.startsWith("fallback_")) {
    return {
      style: styles.fallbackNote,
      text: "This turn fell back to a generic response path. Treat it as degraded guidance, not grounded evidence.",
    };
  }
  if (answerSource.startsWith("direct_")) {
    return {
      style: styles.note,
      text: "This turn was produced directly from application instructions and loaded guide content. Citations are not expected here.",
    };
  }
  if (answerSource === "visible_outputs" || visibleOutputCount > 0) {
    return {
      style: styles.note,
      text: "This turn surfaced structured execution outputs according to the application instructions. Citations are optional unless those outputs came from retrieved evidence.",
    };
  }
  if (answerSource === "llm" || answerSource === "llm_safe") {
    return {
      style: styles.note,
      text: "This turn was generated by the answer model without cited evidence. Treat it as instruction-driven or conversational guidance, not a grounded evidence answer.",
    };
  }
  return null;
}

function getSessionPhaseLabel(workflowStatus, latestAssistantMessage) {
  if (workflowStatus?.current_step?.title) {
    return workflowStatus.current_step.title;
  }
  const retrievalSummary = latestAssistantMessage?.retrievalSummary || {};
  if (retrievalSummary?.primary_scope && typeof retrievalSummary.primary_scope === "object") {
    return humanizeScope(retrievalSummary.primary_scope);
  }
  if (retrievalSummary?.primary_scope_id || retrievalSummary?.primary_scope_type) {
    return summarizePrimaryScope(retrievalSummary);
  }
  const executionStatus = latestAssistantMessage?.sessionExecutionState?.execution_status;
  if (executionStatus) {
    return humanizeActionType(executionStatus);
  }
  return "";
}

function getSourceSummary(message) {
  const retrievalSummary = message?.retrievalSummary || {};
  const citationCount = Array.isArray(message?.citations) ? message.citations.length : 0;
  if (citationCount > 0) {
    return `Sources (${citationCount})`;
  }
  if (retrievalSummary?.answer_source?.startsWith("direct_")) {
    return "Instruction-guided";
  }
  if (retrievalSummary?.answer_source === "visible_outputs" || (retrievalSummary?.visible_output_count ?? 0) > 0) {
    return "Structured output";
  }
  if (retrievalSummary?.answer_source?.startsWith("fallback_")) {
    return "Fallback";
  }
  if (retrievalSummary?.answer_source === "llm" || retrievalSummary?.answer_source === "llm_safe") {
    return "LLM response";
  }
  return "";
}

function getGenerationSummary(message) {
  const retrievalSummary = message?.retrievalSummary || {};
  if (!retrievalSummary?.is_generation_request) {
    return "";
  }
  const subtype = String(retrievalSummary.generation_subtype || "").trim();
  return subtype ? `Generation: ${humanizeActionType(subtype)}` : "Generation";
}

function getRetrievalBypassSummary(message) {
  const retrievalSummary = message?.retrievalSummary || {};
  if (!retrievalSummary?.retrieval_bypassed) {
    return "";
  }
  const reason = String(retrievalSummary.retrieval_bypass_reason || "").trim();
  return reason ? `Retrieval bypassed: ${humanizeActionType(reason)}` : "Retrieval bypassed";
}

function ChatPanel({
  appId,
  appName,
  starterQuestions,
  instructionUnderstandingState,
  messages,
  sessionUploads,
  workflowStatus,
  onSubmitQuery,
  onSubmitStarterQuestion,
  onAdvanceWorkflow,
  onUploadArtifact,
}) {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [showScrollLatest, setShowScrollLatest] = useState(false);
  const [isInspectorOpen, setIsInspectorOpen] = useState(false);
  const [inspectorTab, setInspectorTab] = useState("details");
  const [inspectedMessageIndex, setInspectedMessageIndex] = useState(-1);
  const transcriptRef = useRef(null);
  const uploadInputRef = useRef(null);

  const isLandingState = messages.length === 0;
  const latestAssistantIndex = [...messages]
    .map((message, index) => ({ message, index }))
    .reverse()
    .find((entry) => entry.message.role === "assistant")?.index ?? -1;
  const latestAssistantMessage = latestAssistantIndex >= 0 ? messages[latestAssistantIndex] : null;
  const inspectedMessage =
    inspectedMessageIndex >= 0 &&
    inspectedMessageIndex < messages.length &&
    messages[inspectedMessageIndex]?.role === "assistant"
      ? messages[inspectedMessageIndex]
      : latestAssistantMessage;
  const phaseLabel = getSessionPhaseLabel(workflowStatus, latestAssistantMessage);

  useEffect(() => {
    if (!transcriptRef.current) {
      return;
    }
    transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    setShowScrollLatest(false);
  }, [messages]);

  const updateScrollAffordance = () => {
    if (!transcriptRef.current) {
      return;
    }
    const node = transcriptRef.current;
    const distanceFromBottom = node.scrollHeight - node.scrollTop - node.clientHeight;
    setShowScrollLatest(distanceFromBottom > 80);
  };

  const scrollToLatest = () => {
    if (!transcriptRef.current) {
      return;
    }
    transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    setShowScrollLatest(false);
  };

  const openInspector = (tabName = "details", messageIndex = latestAssistantIndex) => {
    if (messageIndex < 0 || messages[messageIndex]?.role !== "assistant") {
      return;
    }
    setInspectedMessageIndex(messageIndex);
    setInspectorTab(tabName);
    setIsInspectorOpen(true);
  };

  const submitQuery = async (nextQuery) => {
    const normalizedQuery = String(nextQuery || "").trim();
    if (!normalizedQuery || !appId || !onSubmitQuery) {
      return;
    }
    setLoading(true);
    setError("");
    try {
      await onSubmitQuery(normalizedQuery);
      setQuery("");
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setLoading(false);
    }
  };

  const submitStarterQuestion = async (nextQuery) => {
    const normalizedQuery = String(nextQuery || "").trim();
    if (!normalizedQuery || !appId || !onSubmitStarterQuestion) {
      return;
    }
    setLoading(true);
    setError("");
    try {
      await onSubmitStarterQuestion(normalizedQuery);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setLoading(false);
    }
  };

  const send = async () => {
    await submitQuery(query);
  };

  const uploadArtifact = async (event) => {
    const file = event?.target?.files?.[0];
    if (!file || !appId || !onUploadArtifact) {
      return;
    }
    setUploading(true);
    setError("");
    try {
      await onUploadArtifact(file);
      if (uploadInputRef.current) {
        uploadInputRef.current.value = "";
      }
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div style={styles.workspaceGrid(isInspectorOpen)}>
      <section style={{ ...styles.card, marginBottom: 0 }}>
        {isLandingState ? (
          <ChatLanding
            appName={appName}
            starterQuestions={starterQuestions}
            styles={styles}
            loading={loading}
            appId={appId}
            compileRequiredMessage={instructionUnderstandingState.compileRequired ? instructionUnderstandingState.message : ""}
            onSelectStarterQuestion={submitStarterQuestion}
          />
        ) : (
          <>
            <SessionHeader
              appName={appName}
              phaseLabel={phaseLabel}
              workflowStatus={workflowStatus}
              styles={styles}
              loading={loading}
              appId={appId}
              onAdvanceWorkflow={onAdvanceWorkflow}
              onOpenInspector={() => openInspector("details")}
              hasAssistantTurn={Boolean(latestAssistantMessage)}
            />
            <div style={styles.transcriptWrapper}>
              <div
                ref={transcriptRef}
                style={styles.transcript}
                onScroll={updateScrollAffordance}
              >
                {messages.map((message, index) => {
                  const retrievalSummary = message.retrievalSummary || {};
                  return (
                    <ChatMessageCard
                      key={`${message.role}-${index}`}
                      message={message}
                      index={index}
                      styles={styles}
                      assistantType={message.role === "assistant" ? classifyAssistantTurn(message) : null}
                      turnIntentLabel={message.role === "assistant" && retrievalSummary.turn_intent ? humanizeActionType(retrievalSummary.turn_intent) : ""}
                      generationSummary={message.role === "assistant" ? getGenerationSummary(message) : ""}
                      primaryScopeSummary={message.role === "assistant" ? summarizePrimaryScope(retrievalSummary) : ""}
                      sourceSummary={message.role === "assistant" ? getSourceSummary(message) : ""}
                      retrievalBypassSummary={message.role === "assistant" ? getRetrievalBypassSummary(message) : ""}
                      evidenceNote={message.role === "assistant" ? buildAssistantEvidenceNote(message) : ""}
                      onOpenInspector={(messageIndex) => openInspector("details", messageIndex)}
                      onOpenSources={(messageIndex) => openInspector("sources", messageIndex)}
                    />
                  );
                })}
              </div>
              {showScrollLatest && (
                <button style={styles.scrollLatestButton} onClick={scrollToLatest}>
                  Scroll to latest
                </button>
              )}
            </div>
          </>
        )}

        <div style={styles.details}>
          <div style={styles.label}>Session Artifact Upload</div>
          <div style={styles.row}>
            <input
              ref={uploadInputRef}
              type="file"
              onChange={uploadArtifact}
              disabled={!appId || uploading}
            />
            <span style={styles.small}>
              Upload an artifact for this chat session only. It is not ingested into app knowledge.
            </span>
          </div>
          {Array.isArray(sessionUploads) && sessionUploads.length > 0 && (
            <>
              <div style={styles.uploadChipRow}>
                {sessionUploads.map((upload) => (
                  <span key={`chip-${upload.id}`} style={styles.uploadChip}>
                    {upload.filename}
                  </span>
                ))}
              </div>
              <details style={{ ...styles.details, marginTop: 10 }}>
                <summary style={styles.summary}>Session files</summary>
                <div style={styles.uploadList}>
                  {sessionUploads.map((upload) => (
                    <div key={upload.id} style={styles.uploadItem}>
                      <strong>{upload.filename}</strong>
                      <div style={styles.small}>{upload.id}</div>
                      <div style={styles.small}>
                        {upload.mime_type || "application/octet-stream"} | {upload.size_bytes || 0} bytes
                      </div>
                    </div>
                  ))}
                </div>
              </details>
            </>
          )}
        </div>

        <div style={styles.composerShell}>
          <textarea
            style={styles.textarea}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={isLandingState ? "Ask anything or use a starter prompt." : "Type your next message."}
            disabled={!appId}
          />
          <div style={{ ...styles.row, marginTop: 12 }}>
            <button style={styles.button} onClick={send} disabled={loading || !appId}>
              {loading ? "Sending..." : "Ask"}
            </button>
            {uploading && <span style={styles.small}>Uploading artifact...</span>}
          </div>
          {error && <div style={{ ...styles.error, marginTop: 12 }}>{error}</div>}
        </div>
      </section>
      <RuntimeInspector
        open={isInspectorOpen}
        tab={inspectorTab}
        onChangeTab={setInspectorTab}
        onClose={() => setIsInspectorOpen(false)}
        message={inspectedMessage}
        workflowStatus={workflowStatus}
        styles={styles}
        humanizeActionType={humanizeActionType}
        humanizePresentationMode={humanizePresentationMode}
        summarizePrimaryScope={summarizePrimaryScope}
      />
    </div>
  );
}

export default function App() {
  const [adminTab, setAdminTab] = useState("documents");
  const [baseUrl, setBaseUrl] = useState(DEFAULT_BASE_URL);
  const [builderBaseUrl, setBuilderBaseUrl] = useState(DEFAULT_BUILDER_BASE_URL);
  const [builderAvailable, setBuilderAvailable] = useState(false);
  const [applications, setApplications] = useState([]);
  const [selectedAppId, setSelectedAppId] = useState("");
  const [sessionId, setSessionId] = useState(createSessionId());
  const [userId, setUserId] = useState("user1");
  const [appInfo, setAppInfo] = useState(null);
  const [appError, setAppError] = useState("");
  const [threadsBySession, setThreadsBySession] = useState({});
  const [sessionUploadsBySession, setSessionUploadsBySession] = useState({});
  const [sessions, setSessions] = useState([]);
  const [sessionTitleDraft, setSessionTitleDraft] = useState("");
  const [savingSessionTitle, setSavingSessionTitle] = useState(false);
  const [sessionSearch, setSessionSearch] = useState("");
  const [includeArchivedSessions, setIncludeArchivedSessions] = useState(false);
  const [actingSessionId, setActingSessionId] = useState("");

  const adminTabs = useMemo(
    () => [
      ["documents", "Documents"],
      ["instructions", "Instructions"],
      ["runtime", "Runtime"],
    ],
    []
  );

  const selectedApp = applications.find((app) => app.id === selectedAppId) || null;
  const activeAppDisplay = resolveActiveAppDisplay(selectedApp, appInfo, selectedAppId);
  const instructionUnderstandingState = resolveInstructionUnderstandingState(appInfo);
  const activeThreadKey = buildThreadKey(selectedAppId, sessionId);
  const activeMessages = threadsBySession[activeThreadKey] || [];
  const activeSessionUploads = sessionUploadsBySession[activeThreadKey] || [];
  const currentSession = sessions.find((session) => session.id === sessionId) || null;
  const filteredSessions = useMemo(() => {
    const needle = sessionSearch.trim().toLowerCase();
    if (!needle) {
      return sessions;
    }
    return sessions.filter((session) => {
      const haystack = [
        session.title,
        session.id,
        session.last_message_preview,
        session.last_message_role,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(needle);
    });
  }, [sessionSearch, sessions]);

  const loadApplications = async () => {
    try {
      const data = await fetchJson(`${baseUrl}/apps`);
      const apps = data.applications || [];
      setApplications(apps);
      if (!selectedAppId && apps.length > 0) {
        setSelectedAppId(apps[0].id);
      }
    } catch (e) {
      setAppError(String(e.message || e));
    }
  };

  const loadSessions = async (
    appIdOverride = selectedAppId,
    userIdOverride = userId,
    includeArchivedOverride = includeArchivedSessions,
  ) => {
    if (!appIdOverride || !userIdOverride) {
      setSessions([]);
      return;
    }
    try {
      const data = await fetchJson(
        `${baseUrl}/apps/${appIdOverride}/sessions?user_id=${encodeURIComponent(userIdOverride)}&include_archived=${includeArchivedOverride ? "true" : "false"}`
      );
      setSessions(data.sessions || []);
    } catch (_e) {
      setSessions([]);
    }
  };

  const refreshApp = async () => {
    if (!selectedAppId) {
      return;
    }
    setAppError("");
    try {
      const [app, docs, instructions] = await Promise.all([
        fetchJson(`${baseUrl}/apps/${selectedAppId}`),
        fetchJson(`${baseUrl}/apps/${selectedAppId}/documents`, { headers: { "x-role": "admin" } }),
        fetchJson(`${baseUrl}/apps/${selectedAppId}/instructions`, { headers: { "x-role": "admin" } }),
      ]);
      setAppInfo({
        ...app,
        documents: docs.documents || [],
        instructions: instructions.instructions || null,
        instruction_understanding_status: instructions.instruction_understanding_status || {},
        instruction_understanding_preview: instructions.instruction_understanding_preview || {},
      });
    } catch (e) {
      setAppError(String(e.message || e));
      setAppInfo(null);
    }
  };

  const newSession = () => {
    setSessionId(createSessionId());
    setSessionTitleDraft("");
  };

  const saveSessionTitle = async () => {
    if (!selectedAppId || !sessionId) {
      return;
    }
    setSavingSessionTitle(true);
    try {
      await fetchJson(`${baseUrl}/sessions/${sessionId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          app_id: selectedAppId,
          user_id: userId,
          title: sessionTitleDraft,
        }),
      });
      await loadSessions(selectedAppId, userId, includeArchivedSessions);
    } catch (e) {
      setAppError(String(e.message || e));
    } finally {
      setSavingSessionTitle(false);
    }
  };

  const appendAssistantMessage = (data) => ({
    role: "assistant",
    content: (data.content || "").trim() || "(No answer text returned by backend)",
    citations: data.citations || [],
    missingInfoTypes: data.missing_infoTypes || data.missingInfoTypes || [],
    retrievalSummary: data.retrieval_summary || {},
    workflowProgress: data.workflow_progress || {},
    turnExecutionPlan: data.turn_execution_plan || data.retrieval_summary?.turn_execution_plan || {},
    sessionExecutionState: data.session_execution_state || data.retrieval_summary?.session_execution_state || {},
  });

  const sendQueryToSession = async (targetSessionId, rawQuery) => {
    const normalizedQuery = String(rawQuery || "").trim();
    if (!selectedAppId || !normalizedQuery) {
      return;
    }
    if (instructionUnderstandingState.compileRequired) {
      throw new Error(instructionUnderstandingState.message);
    }
    const targetThreadKey = buildThreadKey(selectedAppId, targetSessionId);
    const userMessage = { role: "user", content: normalizedQuery };

    setThreadsBySession((prev) => ({
      ...prev,
      [targetThreadKey]: [...(prev[targetThreadKey] || []), userMessage],
    }));

    const payload = {
      user_id: userId,
      app_id: selectedAppId,
      user_query: normalizedQuery,
      template_version: 1,
    };
    const data = await fetchJson(`${baseUrl}/sessions/${targetSessionId}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setThreadsBySession((prev) => ({
      ...prev,
      [targetThreadKey]: [...(prev[targetThreadKey] || []), appendAssistantMessage(data)],
    }));
    await loadSessions(selectedAppId, userId, includeArchivedSessions);
  };

  const sendStarterQuestionInNewSession = async (rawQuery) => {
    const nextSessionId = createSessionId();
    setSessionId(nextSessionId);
    setSessionTitleDraft("");
      setThreadsBySession((prev) => ({
        ...prev,
        [buildThreadKey(selectedAppId, nextSessionId)]: [],
      }));
      setSessionUploadsBySession((prev) => ({
        ...prev,
        [buildThreadKey(selectedAppId, nextSessionId)]: [],
      }));
    await sendQueryToSession(nextSessionId, rawQuery);
  };

  const uploadArtifactToSession = async (file) => {
    if (!selectedAppId || !sessionId || !userId || !file) {
      return;
    }
    const formData = new FormData();
    formData.append("app_id", selectedAppId);
    formData.append("user_id", userId);
    formData.append("file", file);
    const data = await fetchJson(`${baseUrl}/sessions/${sessionId}/uploads`, {
      method: "POST",
      body: formData,
    });
    const upload = data.upload || null;
    if (upload) {
      setSessionUploadsBySession((prev) => ({
        ...prev,
        [activeThreadKey]: [...(prev[activeThreadKey] || []), upload],
      }));
    }
    if (data && (data.content || data.retrieval_summary || data.turn_execution_plan || data.session_execution_state)) {
      setThreadsBySession((prev) => ({
        ...prev,
        [activeThreadKey]: [...(prev[activeThreadKey] || []), appendAssistantMessage(data)],
      }));
    }
    await loadSessions(selectedAppId, userId, includeArchivedSessions);
  };

  const togglePinnedSession = async (session) => {
    setActingSessionId(session.id);
    try {
      await fetchJson(`${baseUrl}/sessions/${session.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          app_id: selectedAppId,
          user_id: userId,
          pinned: !session.pinned,
        }),
      });
      await loadSessions(selectedAppId, userId, includeArchivedSessions);
    } catch (e) {
      setAppError(String(e.message || e));
    } finally {
      setActingSessionId("");
    }
  };

  const archiveSession = async (session) => {
    setActingSessionId(session.id);
    try {
      await fetchJson(`${baseUrl}/sessions/${session.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          app_id: selectedAppId,
          user_id: userId,
          archived: !session.archived,
        }),
      });
      if (session.id === sessionId && !session.archived) {
        setSessionId(createSessionId());
      }
      await loadSessions(selectedAppId, userId, includeArchivedSessions);
    } catch (e) {
      setAppError(String(e.message || e));
    } finally {
      setActingSessionId("");
    }
  };

  const deleteSession = async (session) => {
    setActingSessionId(session.id);
    try {
      await fetchJson(
        `${baseUrl}/sessions/${session.id}?app_id=${encodeURIComponent(selectedAppId)}&user_id=${encodeURIComponent(userId)}`,
        { method: "DELETE" }
      );
      setThreadsBySession((prev) => {
        const next = { ...prev };
        delete next[buildThreadKey(selectedAppId, session.id)];
        return next;
      });
      setSessionUploadsBySession((prev) => {
        const next = { ...prev };
        delete next[buildThreadKey(selectedAppId, session.id)];
        return next;
      });
      if (session.id === sessionId) {
        setSessionId(createSessionId());
        setSessionTitleDraft("");
      }
      await loadSessions(selectedAppId, userId, includeArchivedSessions);
    } catch (e) {
      setAppError(String(e.message || e));
    } finally {
      setActingSessionId("");
    }
  };

  const advanceWorkflowStep = async () => {
    if (!selectedAppId || !sessionId) {
      return;
    }
    try {
      await fetchJson(`${baseUrl}/sessions/${sessionId}/workflow/advance`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          app_id: selectedAppId,
          user_id: userId,
        }),
      });
      await loadSessions(selectedAppId, userId, includeArchivedSessions);
    } catch (e) {
      setAppError(String(e.message || e));
    }
  };

  useEffect(() => {
    loadApplications();
  }, [baseUrl]);

  useEffect(() => {
    let cancelled = false;
    const probeBuilder = async () => {
      const reachable = await checkUrlReachable(builderBaseUrl);
      if (!cancelled) {
        setBuilderAvailable(reachable);
      }
    };
    probeBuilder();
    return () => {
      cancelled = true;
    };
  }, [builderBaseUrl]);

  useEffect(() => {
    if (selectedAppId) {
      refreshApp();
      loadSessions(selectedAppId, userId, includeArchivedSessions);
      setSessionId(createSessionId());
      setSessionSearch("");
    }
  }, [selectedAppId]);

  useEffect(() => {
    if (selectedAppId && userId) {
      loadSessions(selectedAppId, userId, includeArchivedSessions);
    }
  }, [baseUrl, selectedAppId, userId, includeArchivedSessions]);

  useEffect(() => {
    setSessionTitleDraft(currentSession?.title || "");
  }, [currentSession?.title, sessionId]);

  useEffect(() => {
    const loadThread = async () => {
      if (!selectedAppId || !userId || !sessionId) {
        return;
      }
      try {
        const data = await fetchJson(
          `${baseUrl}/sessions/${sessionId}/messages?app_id=${encodeURIComponent(selectedAppId)}&user_id=${encodeURIComponent(userId)}`
        );
        if (data.workflow_status) {
          setSessions((prev) =>
            prev.map((session) =>
              session.id === sessionId
                ? { ...session, workflow_status: data.workflow_status }
                : session
            )
          );
        }
        setThreadsBySession((prev) => ({
          ...prev,
          [activeThreadKey]: normalizeBackendMessages(data.messages || []),
        }));
        setSessionUploadsBySession((prev) => ({
          ...prev,
          [activeThreadKey]: Array.isArray(data.session_uploads) ? data.session_uploads : [],
        }));
      } catch (e) {
        setThreadsBySession((prev) => ({
          ...prev,
          [activeThreadKey]: prev[activeThreadKey] || [],
        }));
        setSessionUploadsBySession((prev) => ({
          ...prev,
          [activeThreadKey]: prev[activeThreadKey] || [],
        }));
      }
    };
    loadThread();
  }, [baseUrl, selectedAppId, sessionId, userId, activeThreadKey]);

  return (
    <main style={styles.page}>
      <div style={styles.shell}>
        <div style={styles.shellLayout}>
          <AppSidebar
            applications={applications}
            selectedAppId={selectedAppId}
            setSelectedAppId={setSelectedAppId}
            appInfo={appInfo}
            appError={appError}
            refreshApp={refreshApp}
            sessionId={sessionId}
            userId={userId}
            setUserId={setUserId}
            baseUrl={baseUrl}
            setBaseUrl={setBaseUrl}
            builderBaseUrl={builderBaseUrl}
            setBuilderBaseUrl={setBuilderBaseUrl}
            builderAvailable={builderAvailable}
            newSession={newSession}
            sessions={filteredSessions}
            currentSessionId={sessionId}
            onSelectSession={setSessionId}
            currentSessionTitle={currentSession?.title || ""}
            sessionTitleDraft={sessionTitleDraft}
            setSessionTitleDraft={setSessionTitleDraft}
            saveSessionTitle={saveSessionTitle}
            savingSessionTitle={savingSessionTitle}
            sessionSearch={sessionSearch}
            setSessionSearch={setSessionSearch}
            includeArchivedSessions={includeArchivedSessions}
            setIncludeArchivedSessions={setIncludeArchivedSessions}
            togglePinnedSession={togglePinnedSession}
            archiveSession={archiveSession}
            deleteSession={deleteSession}
            actingSessionId={actingSessionId}
            styles={styles}
            safeCount={safeCount}
            shortenPreview={shortenPreview}
            workflowStatusLabel={workflowStatusLabel}
            formatWhen={formatWhen}
          />

          <div style={styles.mainColumn}>
            <ChatPanel
              appId={selectedAppId}
              appName={activeAppDisplay.appName}
              starterQuestions={activeAppDisplay.starterQuestions}
              instructionUnderstandingState={instructionUnderstandingState}
              messages={activeMessages}
              sessionUploads={activeSessionUploads}
              workflowStatus={currentSession?.workflow_status || null}
              onSubmitQuery={(query) => sendQueryToSession(sessionId, query)}
              onSubmitStarterQuestion={sendStarterQuestionInNewSession}
              onAdvanceWorkflow={advanceWorkflowStep}
              onUploadArtifact={uploadArtifactToSession}
            />

            <AdminPanels
              styles={styles}
              adminTabs={adminTabs}
              adminTab={adminTab}
              setAdminTab={setAdminTab}
            >
              {adminTab === "documents" && (
                <DocumentsPanel
                  baseUrl={baseUrl}
                  builderBaseUrl={builderBaseUrl}
                  builderAvailable={builderAvailable}
                  appId={selectedAppId}
                  onDocumentsLoaded={(documents) =>
                    setAppInfo((prev) => (prev ? { ...prev, documents } : prev))
                  }
                  styles={styles}
                  fetchJson={fetchJson}
                  formatStatusPill={formatStatusPill}
                />
              )}
              {adminTab === "instructions" && (
                <InstructionsPanel
                  baseUrl={baseUrl}
                  builderBaseUrl={builderBaseUrl}
                  builderAvailable={builderAvailable}
                  appId={selectedAppId}
                  styles={styles}
                  fetchJson={fetchJson}
                />
              )}
              {adminTab === "runtime" && (
                <RuntimePanel
                  baseUrl={baseUrl}
                  builderBaseUrl={builderBaseUrl}
                  builderAvailable={builderAvailable}
                  appId={selectedAppId}
                  styles={styles}
                  fetchJson={fetchJson}
                />
              )}
            </AdminPanels>
          </div>
        </div>
      </div>
    </main>
  );
}




