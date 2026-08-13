import React, { useEffect, useMemo, useRef, useState } from "react";
import AdminPanels from "./components/AdminPanels";
import ApprovedContentPanel from "./components/ApprovedContentPanel";
import AppSidebar from "./components/AppSidebar";
import ChatLanding from "./components/ChatLanding";
import ChatMessageCard from "./components/ChatMessageCard";
import DocumentsPanel from "./components/DocumentsPanel";
import ExecutionInspector from "./components/ExecutionInspector";
import ExecutionComposer from "./components/ExecutionComposer";
import ExecutionLaneStatusCard from "./components/ExecutionLaneStatusCard";
import ArtifactLibrary from "./components/ArtifactLibrary";
import InstructionsPanel from "./components/InstructionsPanel";
import RuntimeInspector from "./components/RuntimeInspector";
import RuntimePanel from "./components/RuntimePanel";
import SessionHeader from "./components/SessionHeader";
import { retryArtifactUpload, uploadArtifact } from "./artifactUploadClient";
import ArtifactUploadControl from "./components/ArtifactUploadControl";

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
  chatWorkspaceCard: {
    display: "grid",
    gridTemplateRows: "auto auto minmax(0, 1fr) auto auto",
    maxHeight: "calc(100vh - 32px)",
    overflow: "hidden",
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
  approvedContentShell: {
    display: "grid",
    gap: 8,
    padding: "10px 12px",
    borderRadius: 16,
    border: "1px solid #dbeafe",
    background: "linear-gradient(180deg, #ffffff 0%, #f8fbff 100%)",
    marginBottom: 12,
  },
  approvedContentHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 12,
    flexWrap: "wrap",
  },
  approvedContentCard: {
    padding: "9px 11px",
    borderRadius: 12,
    background: "#ffffff",
    border: "1px solid #dbeafe",
  },
  approvedContentList: {
    display: "grid",
    gap: 10,
  },
  approvedContentListItem: (selected) => ({
    display: "grid",
    gap: 8,
    padding: "10px 12px",
    borderRadius: 14,
    background: selected ? "#eff6ff" : "#ffffff",
    border: `1px solid ${selected ? "#93c5fd" : "#dbeafe"}`,
  }),
  executionLaneShell: {
    display: "grid",
    gap: 10,
    padding: "12px 14px",
    borderRadius: 18,
    border: "1px solid #e2e8f0",
    background: "linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)",
    marginBottom: 14,
  },
  executionLaneHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 12,
    flexWrap: "wrap",
  },
  executionLaneGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
    gap: 10,
  },
  executionLaneMetric: {
    padding: "10px 12px",
    borderRadius: 14,
    background: "#ffffff",
    border: "1px solid #e2e8f0",
  },
  executionLaneValue: {
    fontSize: 13,
    fontWeight: 700,
    color: "#0f172a",
    lineHeight: 1.4,
    wordBreak: "break-word",
  },
  executionDetailsShell: {
    display: "grid",
    gap: 10,
    padding: "12px 14px",
    borderRadius: 14,
    background: "#ffffff",
    border: "1px solid #dbeafe",
  },
  executionDetailsTitle: {
    fontSize: 13,
    fontWeight: 800,
    color: "#0f172a",
  },
  executionDetailsBlock: {
    display: "grid",
    gap: 6,
  },
  executionDetailsList: {
    display: "grid",
    gap: 8,
  },
  executionDetailsItem: {
    display: "grid",
    gap: 4,
    padding: "10px 12px",
    borderRadius: 12,
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
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
    lineHeight: 1.45,
  },
  workflowStrip: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap",
    marginBottom: 12,
  },
  workflowBadge: (kind) => ({
    display: "inline-flex",
    alignItems: "center",
    padding: "8px 12px",
    borderRadius: 999,
    border: kind === "current" ? "1px solid #93c5fd" : "1px solid #dbeafe",
    background: kind === "current" ? "#eff6ff" : "#f8fafc",
    color: kind === "current" ? "#1d4ed8" : "#475569",
    fontWeight: 700,
    fontSize: 13,
    lineHeight: 1.3,
  }),
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
    maxHeight: "calc(100vh - 36px)",
    overflowY: "scroll",
    paddingRight: 6,
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
    minHeight: 0,
  },
  transcript: {
    height: "100%",
    minHeight: 0,
    overflowY: "scroll",
    overflowX: "hidden",
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
  executionComposerCard: {
    maxHeight: "min(72vh, 760px)",
    overflowY: "auto",
    overflowX: "hidden",
    overscrollBehavior: "contain",
    scrollbarGutter: "stable",
  },
  executionComposerShelf: {
    minWidth: 0,
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
  messageCard: (role, selectedForExport = false) => ({
    padding: 16,
    minWidth: 0,
    maxWidth: "100%",
    borderRadius: 18,
    border: selectedForExport
      ? "2px solid #2563eb"
      : role === "user"
        ? "1px solid #bfdbfe"
        : "1px solid #d1fae5",
    background: role === "user" ? "#eff6ff" : "#f0fdf4",
    boxShadow: selectedForExport ? "0 0 0 3px rgba(37, 99, 235, 0.12)" : "none",
    cursor: selectedForExport ? "pointer" : "default",
    transition: "border-color 120ms ease, box-shadow 120ms ease",
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
    overflowWrap: "anywhere",
    wordBreak: "break-word",
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

function artifactDeleteErrorMessage(error) {
  const raw = String(error?.message || error || "");
  try {
    const payload = JSON.parse(raw);
    const detail = payload?.detail || payload?.error || {};
    if (detail?.code === "ARTIFACT_IN_USE") {
      return "This artifact is in use by an active execution. Wait for it to finish, then retry deletion.";
    }
    return String(detail?.message || "Unable to delete the artifact.");
  } catch {
    return raw || "Unable to delete the artifact.";
  }
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

export function createSessionId(randomUUID = () => globalThis.crypto.randomUUID()) {
  return randomUUID();
}

function buildThreadKey(appId, sessionId) {
  return `${appId || "no-app"}::${sessionId || "no-session"}`;
}

export function buildAgentSkillInventoryKey(appId, sessionId, userId, backend) {
  return JSON.stringify([
    String(appId || "").trim(),
    String(sessionId || "").trim(),
    String(userId || "").trim(),
    String(backend || "").trim(),
  ]);
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

export function applyApprovedContentSelectionToExecQuery(rawQuery, approvedContentId) {
  const normalizedQuery = String(rawQuery || "").trim();
  const selectedId = String(approvedContentId || "").trim();
  if (!normalizedQuery || !selectedId) {
    return normalizedQuery;
  }
  if (!/^@exec\s+(?:async\s+|sync\s+)?(?:tool|skill)\b/i.test(normalizedQuery)) {
    return normalizedQuery;
  }
  if (/(^|\s)(approvedContentId|approved_content_id)=/i.test(normalizedQuery)) {
    return normalizedQuery;
  }
  return `${normalizedQuery} approvedContentId="${selectedId}"`;
}

function stringifyExecArgValue(value) {
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value === "number") {
    return String(value);
  }
  if (Array.isArray(value) || (value && typeof value === "object")) {
    return `'${JSON.stringify(value)}'`;
  }
  return `"${String(value).replace(/"/g, '\\"')}"`;
}

export function buildExecCommand({ commandKind, targetId, args = {}, executionMode = "sync", approvedContentId = "" }) {
  if (commandKind === "agent") {
    const requestText = String(args.request || "").trim();
    const skillHint = String(args.skillHint || "").trim();
    const execPrefix = executionMode === "async" ? "@exec async" : "@exec";
    if (targetId === "openclaw_cli") {
      if (skillHint) {
        return `${execPrefix} openclaw use ${skillHint} "${requestText.replace(/"/g, '\\"')}"`.trim();
      }
      return `${execPrefix} openclaw "${requestText.replace(/"/g, '\\"')}"`.trim();
    }
    if (skillHint) {
      return `${execPrefix} codex use ${skillHint} "${requestText.replace(/"/g, '\\"')}"`.trim();
    }
    return `${execPrefix} codex "${requestText.replace(/"/g, '\\"')}"`.trim();
  }
  const normalizedKind = commandKind === "skill" ? "skill" : "tool";
  const normalizedTargetId = String(targetId || "").trim();
  const nextArgs = { ...args };
  if (approvedContentId && !nextArgs.approvedContentId) {
    nextArgs.approvedContentId = approvedContentId;
  }
  const serializedArgs = Object.entries(nextArgs)
    .filter(([, value]) => value !== "" && value !== null && value !== undefined)
    .map(([key, value]) => `${key}=${stringifyExecArgValue(value)}`)
    .join(" ");
  const execPrefix = executionMode === "async" ? "@exec async" : "@exec";
  return `${execPrefix} ${normalizedKind} ${normalizedTargetId}${serializedArgs ? ` ${serializedArgs}` : ""}`.trim();
}

function normalizeComposerArtifactRefs(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((entry) => {
      if (!entry || typeof entry !== "object") {
        return null;
      }
      const artifactId = String(entry.artifact_id || entry.artifactId || "").trim();
      if (!artifactId) {
        return null;
      }
      return {
        artifact_id: artifactId,
        role: String(entry.role || "source").trim() || "source",
        reuse_mode: String(entry.reuse_mode || entry.reuseMode || "inline_text").trim() || "inline_text",
      };
    })
    .filter(Boolean);
}

function normalizeComposerExpectedOutputs(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((entry) => {
      if (!entry || typeof entry !== "object") {
        return null;
      }
      const outputId = String(entry.output_id || entry.outputId || "").trim();
      if (!outputId) {
        return null;
      }
      return {
        ...entry,
        output_id: outputId,
        ...(entry.artifactType && !entry.artifact_type ? { artifact_type: entry.artifactType } : {}),
        ...(entry.mediaType && !entry.media_type ? { media_type: entry.mediaType } : {}),
        ...(entry.persistAsArtifact !== undefined && entry.persist_as_artifact === undefined
          ? { persist_as_artifact: Boolean(entry.persistAsArtifact) }
          : {}),
      };
    })
    .filter(Boolean);
}

function normalizeComposerAgentSkillRef(value) {
  if (!value || typeof value !== "object") {
    return null;
  }
  const agentSkillId = String(value.agent_skill_id || value.agentSkillId || "").trim();
  const approvedFingerprint = String(value.approved_fingerprint || value.approvedFingerprint || "").trim();
  if (!agentSkillId || !approvedFingerprint) {
    return null;
  }
  return {
    agent_skill_id: agentSkillId,
    approved_fingerprint: approvedFingerprint,
  };
}

export function buildExecutionRequestForComposer({ commandKind, targetId, args = {}, executionMode = "sync" }) {
  if (commandKind !== "agent") {
    return null;
  }
  const artifactRefs = normalizeComposerArtifactRefs(args.artifactRefs || args.artifact_refs);
  const expectedOutputs = normalizeComposerExpectedOutputs(args.expectedOutputs || args.expected_outputs);
  const agentSkillRef = normalizeComposerAgentSkillRef(args.agentSkillRef || args.agent_skill_ref);
  if (artifactRefs.length === 0 && expectedOutputs.length === 0 && !agentSkillRef) {
    return null;
  }
  return {
    request_type: "execute_agent",
    agent_backend: String(targetId || "codex_cli").trim() || "codex_cli",
    execution_mode: executionMode === "async" ? "async" : "sync",
    ...(agentSkillRef ? { agent_skill_ref: agentSkillRef } : {}),
    ...(artifactRefs.length > 0 ? { artifact_refs: artifactRefs } : {}),
    ...(expectedOutputs.length > 0 ? { expected_outputs: expectedOutputs } : {}),
  };
}

function extractErrorDetail(error) {
  const rawMessage = String(error?.message || error || "").trim();
  if (!rawMessage) {
    return "Execution request failed before submission.";
  }
  try {
    const parsed = JSON.parse(rawMessage);
    if (typeof parsed?.detail === "string" && parsed.detail.trim()) {
      return parsed.detail.trim();
    }
    if (typeof parsed?.error?.message === "string" && parsed.error.message.trim()) {
      return parsed.error.message.trim();
    }
  } catch (_error) {
    // Non-JSON backend errors are already useful enough to show directly.
  }
  return rawMessage;
}

function parseExecQueryTarget(rawQuery) {
  const normalized = String(rawQuery || "").trim();
  const match = normalized.match(/^@exec\s+(?:async\s+|sync\s+)?(tool|skill|codex)\s+([^\s"]+)?/i);
  if (!match) {
    return { command: "", target_id: "", skill_id: "" };
  }
  const command = String(match[1] || "").trim().toLowerCase();
  const target = String(match[2] || "").trim();
  return {
    command,
    target_id: command === "tool" || command === "codex" ? target : "",
    skill_id: command === "skill" ? target : "",
  };
}

function suggestedActionForExecutionError(detail) {
  const normalized = String(detail || "").toLowerCase();
  if (normalized.includes("artifact") && normalized.includes("not found")) {
    return "Select a current-session artifact from Artifact Library and retry the execution.";
  }
  if (normalized.includes("consumption mode")) {
    return "Choose an artifact whose reuse mode matches the selected tool.";
  }
  if (normalized.includes("file") && normalized.includes("not")) {
    return "Open the artifact details and verify the saved file still exists before retrying.";
  }
  return "Inspect the execution details, adjust the request, and retry.";
}

export function buildExecutionSubmitErrorTurn(rawQuery, error) {
  const detail = extractErrorDetail(error);
  const suggestedAction = suggestedActionForExecutionError(detail);
  const target = parseExecQueryTarget(rawQuery);
  return {
    role: "assistant",
    content: [
      "Execution request failed before submission.",
      detail,
      suggestedAction,
    ].filter(Boolean).join(" "),
    retrievalSummary: {
      execution_override: true,
      command: target.command,
      target_id: target.target_id,
      skill_id: target.skill_id,
      execution_submit_result: {
        status: "failed",
        error: {
          code: "EXECUTION_SUBMIT_FAILED",
          message: detail,
          suggested_action: suggestedAction,
        },
      },
    },
  };
}

export function classifyAssistantTurn(message) {
  const citationCount = Array.isArray(message?.citations) ? message.citations.length : 0;
  const missingCount = Array.isArray(message?.missingInfoTypes) ? message.missingInfoTypes.length : 0;
  const answerSource = String(message?.retrievalSummary?.answer_source || "").toLowerCase();
  const visibleOutputCount = Number(message?.retrievalSummary?.visible_output_count ?? 0);
  if (message?.retrievalSummary?.execution_override) {
    return { label: "Execution", style: { ...styles.pill, ...styles.statusOk } };
  }
  if (message?.retrievalSummary?.approval_event) {
    return { label: "Approval", style: { ...styles.pill, ...styles.statusWarn } };
  }
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

function normalizeSessionLaneState(value) {
  if (!value || typeof value !== "object") {
    return {};
  }
  return value;
}

export function mergeTaskModelDiagnostics(retrievalSummary, taskModelDiagnostics) {
  const summary =
    retrievalSummary && typeof retrievalSummary === "object" ? retrievalSummary : {};
  if (
    summary.task_model_diagnostics
    && typeof summary.task_model_diagnostics === "object"
    && Object.keys(summary.task_model_diagnostics).length > 0
  ) {
    return summary;
  }
  if (
    taskModelDiagnostics
    && typeof taskModelDiagnostics === "object"
    && Object.keys(taskModelDiagnostics).length > 0
  ) {
    return { ...summary, task_model_diagnostics: taskModelDiagnostics };
  }
  return summary;
}

function normalizeBackendMessages(rows) {
  if (!Array.isArray(rows)) {
    return [];
  }
  return rows.map((row) => {
    const storedSummary =
      row.retrievalSummary && typeof row.retrievalSummary === "object"
        ? row.retrievalSummary
        : (row.retrieval_summary && typeof row.retrieval_summary === "object" ? row.retrieval_summary : {});
    const retrievalSummary = mergeTaskModelDiagnostics(
      storedSummary,
      row.task_model_diagnostics || row.taskModelDiagnostics,
    );
    return {
      id: row.id || null,
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
      workflowStatus:
        row.workflow_status && typeof row.workflow_status === "object"
          ? row.workflow_status
          : (retrievalSummary.workflow_status && typeof retrievalSummary.workflow_status === "object"
              ? retrievalSummary.workflow_status
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

function isExecutionTurn(message) {
  return Boolean(message?.retrievalSummary?.execution_override);
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

function joinPreviewTitles(values, limit = 3) {
  const titles = values
    .map((item) => {
      if (typeof item === "string") {
        return item;
      }
      if (item && typeof item === "object") {
        return item.title || item.name || item.id || "";
      }
      return "";
    })
    .map((value) => String(value || "").trim())
    .filter(Boolean)
    .slice(0, limit);
  return titles.join(", ");
}

function executionPayloadFromMessage(message) {
  const retrievalSummary =
    message?.retrievalSummary && typeof message.retrievalSummary === "object"
      ? message.retrievalSummary
      : {};
  const submitResult =
    retrievalSummary.execution_submit_result && typeof retrievalSummary.execution_submit_result === "object"
      ? retrievalSummary.execution_submit_result
      : {};
  if (Object.keys(submitResult).length > 0) {
    return submitResult;
  }
  const statusResult =
    retrievalSummary.execution_status_result && typeof retrievalSummary.execution_status_result === "object"
      ? retrievalSummary.execution_status_result
      : {};
  return statusResult;
}

function executionIdFromMessage(message) {
  const payload = executionPayloadFromMessage(message);
  const retrievalSummary =
    message?.retrievalSummary && typeof message.retrievalSummary === "object"
      ? message.retrievalSummary
      : {};
  return String(payload.execution_id || retrievalSummary.execution_id || "").trim();
}

export function buildExecutionResultPreview(message) {
  const retrievalSummary =
    message?.retrievalSummary && typeof message.retrievalSummary === "object"
      ? message.retrievalSummary
      : {};
  if (!retrievalSummary.execution_override) {
    return "";
  }
  const submitResult = executionPayloadFromMessage(message);
  const command = String(retrievalSummary.command || "").trim().toLowerCase();
  const lifecycleStatus = String(submitResult.status || "").trim().toLowerCase();
  const lifecycleResult =
    submitResult.result && typeof submitResult.result === "object"
      ? submitResult.result
      : {};
  if (command === "codex") {
    const summary = String(lifecycleResult.summary || "").trim();
    const diagnostics =
      lifecycleResult.diagnostics && typeof lifecycleResult.diagnostics === "object"
        ? lifecycleResult.diagnostics
        : {};
    const detail = summary || String(diagnostics.failure_message || "").trim();
    if (lifecycleStatus === "pending_confirmation") {
      const riskClass = String(lifecycleResult.risk_class || "").trim().replace(/^agent_/, "").replace(/_/g, " ");
      return `Codex confirmation required${riskClass ? ` (${riskClass})` : ""}`;
    }
    if (lifecycleStatus === "running") {
      return "Codex execution is running";
    }
    if (lifecycleStatus === "failed") {
      return `Codex failed${detail ? `: ${shortenPreview(detail, 180)}` : ""}`;
    }
    if (lifecycleStatus === "partial") {
      return `Codex partially completed${detail ? `: ${shortenPreview(detail, 180)}` : ""}`;
    }
    if (lifecycleStatus === "completed") {
      const operations = Array.isArray(lifecycleResult.operation_verification)
        ? lifecycleResult.operation_verification
        : [];
      const isProcessing = operations.some((item) =>
        ["accepted", "processing"].includes(String(item?.status || "").toLowerCase()),
      );
      if (isProcessing) {
        return `Codex generation started${detail ? `: ${shortenPreview(detail, 180)}` : ""}`;
      }
      const isNormalized =
        operations.length > 0
        || Boolean(lifecycleResult.provider_metadata)
        || Boolean(summary);
      if (isNormalized && detail) {
        return `Codex completed: ${shortenPreview(detail, 180)}`;
      }
    }
  }
  if (
    command === "openclaw" &&
    ["pending_confirmation", "running", "partial", "failed"].includes(lifecycleStatus)
  ) {
    const providerLabel = "OpenClaw";
    if (lifecycleStatus === "pending_confirmation") {
      const riskClass = String(lifecycleResult.risk_class || "").trim().replace(/^agent_/, "").replace(/_/g, " ");
      return `${providerLabel} confirmation required${riskClass ? ` (${riskClass})` : ""}`;
    }
    if (lifecycleStatus === "running") {
      return `${providerLabel} execution is running`;
    }
    const summary = String(lifecycleResult.summary || "").trim();
    const diagnostics =
      lifecycleResult.diagnostics && typeof lifecycleResult.diagnostics === "object"
        ? lifecycleResult.diagnostics
        : {};
    const detail = summary || String(diagnostics.failure_message || "").trim();
    return `${providerLabel} execution ${lifecycleStatus === "partial" ? "completed with warnings" : "failed"}${detail ? `: ${shortenPreview(detail, 180)}` : ""}`;
  }
  if (command === "codex") {
    const status = lifecycleStatus;
    const result = lifecycleResult;
    const userSummary = result.user_summary && typeof result.user_summary === "object" ? result.user_summary : {};
    const skills = Array.isArray(result.activated_skills)
      ? result.activated_skills.map((item) => String(item || "").trim()).filter(Boolean)
      : [];
    const artifacts = Array.isArray(result.artifacts) ? result.artifacts : [];
    const toolSummary = Array.isArray(result.tool_summary)
      ? result.tool_summary.map((item) => String(item || "").trim()).filter(Boolean)
      : [];
    if (submitResult.error) {
      return "";
    }
    if (status !== "completed") {
      return "";
    }
    const summaryTitle = String(userSummary.title || "").trim();
    const summarySubtitle = String(userSummary.subtitle || "").trim();
    const summaryPreview = String(userSummary.preview || "").trim();
    if (summaryTitle) {
      const heading = summarySubtitle ? `${summaryTitle} (${summarySubtitle})` : summaryTitle;
      return summaryPreview ? `${heading}: ${shortenPreview(summaryPreview, 180)}` : heading;
    }
    const parts = [];
    if (skills.length > 0) {
      parts.push(`Activated skills: ${skills.join(", ")}`);
    }
    if (toolSummary.length > 0) {
      parts.push(`Actions: ${toolSummary.slice(0, 2).join("; ")}`);
    }
    if (artifacts.length > 0) {
      parts.push(`Artifacts: ${artifacts.length}`);
    }
    return parts.join(" | ");
  }
  if (command === "openclaw") {
    const result = submitResult.result && typeof submitResult.result === "object" ? submitResult.result : {};
    if (submitResult.error) {
      return "";
    }
    const providerMetadata =
      result.provider_metadata && typeof result.provider_metadata === "object"
        ? result.provider_metadata
        : {};
    const providerName = String(providerMetadata.provider_name || "OpenClaw").trim();
    const summary = String(result.summary || "").trim();
    const outputText = String(result.output_text || "").trim();
    const artifacts = Array.isArray(result.artifacts) ? result.artifacts : [];
    const verificationResults = Array.isArray(result.verification_results)
      ? result.verification_results
      : [];
    const verifiedOutputCount = Number.isFinite(Number(providerMetadata.verified_output_count))
      ? Number(providerMetadata.verified_output_count)
      : verificationResults.filter((item) => item?.verified === true).length;
    const requiredOutputCount = Number.isFinite(Number(providerMetadata.required_output_count))
      ? Number(providerMetadata.required_output_count)
      : verificationResults.filter((item) => item?.required === true).length;
    const status = String(result.status || submitResult.status || "").trim();
    const parts = [];
    parts.push(summary || `${providerName}${status ? ` ${status}` : " completed"}`);
    if (outputText) {
      parts.push(shortenPreview(outputText, 180));
    }
    if (requiredOutputCount > 0 || verifiedOutputCount > 0) {
      parts.push(`Verified outputs: ${verifiedOutputCount}/${requiredOutputCount}`);
    }
    if (artifacts.length > 0) {
      parts.push(`Artifacts: ${artifacts.length}`);
    }
    return parts.join(" | ");
  }
  if (command !== "tool") {
    return "";
  }
  if (submitResult.error || String(submitResult.status || "").toLowerCase() !== "completed") {
    return "";
  }
  const result = submitResult.result && typeof submitResult.result === "object" ? submitResult.result : {};
  const targetId = String(retrievalSummary.target_id || "").trim().toLowerCase();
  if (Array.isArray(result.notebooks)) {
    return `NotebookLM notebooks (${result.notebooks.length}): ${joinPreviewTitles(result.notebooks)}`;
  }
  if (Array.isArray(result.sources)) {
    return `Sources (${result.sources.length}): ${joinPreviewTitles(result.sources)}`;
  }
  if (typeof result.answer === "string" && result.answer.trim()) {
    return `Answer: ${shortenPreview(result.answer, 180)}`;
  }
  if (Array.isArray(result.results)) {
    if (targetId.includes("gmail")) {
      return `Messages (${result.results.length}): ${joinPreviewTitles(result.results)}`;
    }
    if (targetId.includes("gdrive")) {
      return `Files (${result.results.length}): ${joinPreviewTitles(result.results)}`;
    }
    if (targetId.includes("gdocs")) {
      return `Documents (${result.results.length}): ${joinPreviewTitles(result.results)}`;
    }
    if (targetId.includes("cms")) {
      return `Pages (${result.results.length}): ${joinPreviewTitles(result.results)}`;
    }
    return `Results (${result.results.length}): ${joinPreviewTitles(result.results)}`;
  }
  if (targetId.includes("create_draft_with_attachments")) {
    if (result.id || result.threadId) {
      return `Draft with attachments created: ${result.id || result.threadId}`;
    }
  }
  if (targetId.includes("create_draft")) {
    if (result.id || result.threadId) {
      return `Draft created: ${result.id || result.threadId}`;
    }
  }
  if (targetId.includes("send_draft")) {
    if (result.id || result.threadId) {
      return `Draft sent: ${result.id || result.threadId}`;
    }
  }
  if (targetId.includes("send_message")) {
    if (result.id || result.threadId) {
      return `Message sent: ${result.id || result.threadId}`;
    }
  }
  if (targetId.includes("create_page")) {
    if (result.title || result.id) {
      return `Page created: ${result.title || result.id}`;
    }
  }
  if (targetId.includes("download_file") && (result.name || result.file_id)) {
    return `Drive file exported: ${result.name || result.file_id}`;
  }
  if (targetId.includes("add_source_")) {
    const sourceTitle =
      (result.source && typeof result.source === "object" && (result.source.title || result.source.id)) ||
      result.source_title ||
      result.notebook_id;
    if (sourceTitle) {
      return `Source added: ${sourceTitle}`;
    }
  }
  if (targetId.includes("generate_report") || targetId.includes("generate_slide_deck") || targetId.includes("generate_video")) {
    const artifactKind = String(result.artifact_kind || "").trim();
    const taskId = String(result.task_id || "").trim();
    const status = String(result.status || "").trim().toLowerCase();
    const kindLabel = artifactKind
      ? humanizeActionType(artifactKind.replace(/_/g, " "))
      : targetId.includes("generate_video")
        ? "Video"
        : targetId.includes("generate_slide_deck")
          ? "Slide deck"
          : "Report";
    if (status === "completed") {
      return `${kindLabel} completed${taskId ? `: ${taskId}` : ""}`;
    }
    if (taskId || status) {
      return `${kindLabel} ${status || "submitted"}${taskId ? `: ${taskId}` : ""}`;
    }
  }
  return "";
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
  baseUrl,
  sessionId,
  userId,
  appId,
  appName,
  starterQuestions,
  instructionUnderstandingState,
  messages,
  approvedContent,
  selectedApprovedContentId,
  sessionLaneState,
  workflowStatus,
  onSubmitQuery,
  onSubmitStarterQuestion,
  onAdvanceWorkflow,
  onUploadArtifact,
  onRetryArtifactUpload,
  onApproveLatestAssistantMessage,
  onSelectApprovedContent,
  toolInventory,
  skillInventory,
  agentSkillInventory,
  agentSkillInventoryLoading,
  agentSkillInventoryError,
  agentSkillProjectionStatusByBackend,
  artifactInventory,
  artifactInventoryLoading,
  artifactInventoryError,
  onPrepareExecutionComposer,
  onRefreshAgentSkills,
  onUploadExecutionInput,
  onRunExecutionComposer,
  selectedExportMessageIds,
  onToggleMessageExportSelection,
  onExportSelectedMessages,
  onConfirmExecution,
  agentInteraction,
  onRefreshAgentInteraction,
  onRespondAgentInteraction,
  onCancelAgentExecution,
  agentInteractionSubmitting,
  agentInteractionError,
  onDeleteArtifact,
}) {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [approving, setApproving] = useState(false);
  const [refreshingExecutionStatus, setRefreshingExecutionStatus] = useState(false);
  const [confirmingExecution, setConfirmingExecution] = useState(false);
  const [loggingInToNotebookLm, setLoggingInToNotebookLm] = useState(false);
  const [exportingSelection, setExportingSelection] = useState(false);
  const [showExecutionComposer, setShowExecutionComposer] = useState(false);
  const [showArtifactLibrary, setShowArtifactLibrary] = useState(true);
  const [artifactSuggestionForComposer, setArtifactSuggestionForComposer] = useState(null);
  const [artifactSuggestionsForComposer, setArtifactSuggestionsForComposer] = useState([]);
  const [artifactPreferredTargetIdForComposer, setArtifactPreferredTargetIdForComposer] = useState("");
  const [artifactPreferredCommandKindForComposer, setArtifactPreferredCommandKindForComposer] = useState("");
  const [artifactPreferredAgentBackendForComposer, setArtifactPreferredAgentBackendForComposer] = useState("");
  const [error, setError] = useState("");
  const [showScrollLatest, setShowScrollLatest] = useState(false);
  const [isInspectorOpen, setIsInspectorOpen] = useState(false);
  const [inspectorTab, setInspectorTab] = useState("details");
  const [inspectedMessageIndex, setInspectedMessageIndex] = useState(-1);
  const transcriptRef = useRef(null);

  const openExecutionComposer = () => {
    setShowExecutionComposer(true);
    Promise.resolve(onPrepareExecutionComposer?.()).catch((prepareError) => {
      setError(String(prepareError?.message || prepareError || "Unable to prepare execution session."));
    });
  };

  const isLandingState = messages.length === 0;
  const latestAssistantIndex = [...messages]
    .map((message, index) => ({ message, index }))
    .reverse()
    .find((entry) => entry.message.role === "assistant")?.index ?? -1;
  const latestAssistantMessage = latestAssistantIndex >= 0 ? messages[latestAssistantIndex] : null;
  const selectedApprovedContent =
    approvedContent.find((item) => item.approved_content_id === selectedApprovedContentId)
    || approvedContent[approvedContent.length - 1]
    || null;
  const inspectedMessage =
    inspectedMessageIndex >= 0 &&
    inspectedMessageIndex < messages.length &&
    messages[inspectedMessageIndex]?.role === "assistant"
      ? messages[inspectedMessageIndex]
      : latestAssistantMessage;
  const inspectedMessageIsExecution = isExecutionTurn(inspectedMessage);
  const phaseLabel = getSessionPhaseLabel(workflowStatus, latestAssistantMessage);
  const exportSelectionCount = Array.isArray(selectedExportMessageIds) ? selectedExportMessageIds.length : 0;

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

  const approveLatestAssistantMessage = async () => {
    if (!latestAssistantMessage || !onApproveLatestAssistantMessage) {
      return;
    }
    setApproving(true);
    setError("");
    try {
      await onApproveLatestAssistantMessage(latestAssistantMessage);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setApproving(false);
    }
  };

  const approveMessage = async (messageIndex) => {
    const message = messages[messageIndex];
    if (!message || message.role !== "assistant" || !onApproveLatestAssistantMessage) {
      return;
    }
    setApproving(true);
    setError("");
    try {
      await onApproveLatestAssistantMessage(message);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setApproving(false);
    }
  };

  const refreshExecutionStatus = async () => {
    const executionId = sessionLaneState?.execution_lane?.latest_execution_id;
    if (!executionId || !onSubmitQuery) {
      return;
    }
    setRefreshingExecutionStatus(true);
    setError("");
    try {
      await onSubmitQuery(`@exec status ${executionId}`);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setRefreshingExecutionStatus(false);
    }
  };

  const retryLastExecution = async () => {
    const lastExecQuery = sessionLaneState?.execution_lane?.latest_execution_request_query;
    if (!lastExecQuery || !onSubmitQuery) {
      return;
    }
    setError("");
    try {
      await onSubmitQuery(lastExecQuery);
    } catch (e) {
      setError(String(e.message || e));
    }
  };

  const refreshExecutionStatusForMessage = async (message) => {
    const executionId = executionIdFromMessage(message) || sessionLaneState?.execution_lane?.latest_execution_id;
    if (!executionId || !onSubmitQuery) {
      return;
    }
    setRefreshingExecutionStatus(true);
    setError("");
    try {
      await onSubmitQuery(`@exec status ${executionId}`);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setRefreshingExecutionStatus(false);
    }
  };

  const retryExecutionForMessage = async (_message) => {
    await retryLastExecution();
  };

  const confirmExecutionForMessage = async (message) => {
    const executionId = executionIdFromMessage(message);
    if (!executionId || !onConfirmExecution) {
      return;
    }
    setConfirmingExecution(true);
    setError("");
    try {
      await onConfirmExecution(executionId);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setConfirmingExecution(false);
    }
  };

  const launchNotebookLmLogin = async () => {
    if (!appId || !sessionId || !userId) {
      return;
    }
    setLoggingInToNotebookLm(true);
    setError("");
    try {
      const data = await fetchJson(`${baseUrl}/sessions/${sessionId}/integrations/notebooklm/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          app_id: appId,
          user_id: userId,
        }),
      });
      if (data?.content) {
        setThreadsBySession((prev) => ({
          ...prev,
          [activeThreadKey]: [
            ...(prev[activeThreadKey] || []),
            {
              id: null,
              role: "assistant",
              content: data.content,
              citations: [],
              missingInfoTypes: [],
              retrievalSummary: {
                execution_override: true,
                command: "login",
                provider: "notebooklm",
              },
              workflowProgress: {},
              turnExecutionPlan: {},
              sessionExecutionState: {},
            },
          ],
        }));
      }
      if (data?.session_lane_state) {
        setSessionLaneStateBySession((prev) => ({
          ...prev,
          [activeThreadKey]: normalizeSessionLaneState(data.session_lane_state),
        }));
      }
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setLoggingInToNotebookLm(false);
    }
  };

  const exportSelectedMessages = async () => {
    if (!onExportSelectedMessages || exportSelectionCount === 0) {
      return;
    }
    setExportingSelection(true);
    setError("");
    try {
      await onExportSelectedMessages();
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setExportingSelection(false);
    }
  };

  return (
    <div style={styles.workspaceGrid(isInspectorOpen)}>
      <div style={styles.chatStage}>
        <section
          style={{
            ...styles.card,
            ...(isLandingState ? {} : styles.chatWorkspaceCard),
            marginBottom: 0,
          }}
        >
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
                onOpenInspector={() => openInspector(isExecutionTurn(latestAssistantMessage) ? "summary" : "details")}
                hasAssistantTurn={Boolean(latestAssistantMessage)}
              />
              <ApprovedContentPanel
                approvedContent={approvedContent}
                selectedApprovedContentId={selectedApprovedContentId}
                onSelectApprovedContent={onSelectApprovedContent}
                latestAssistantMessage={latestAssistantMessage}
                onApproveLatest={approveLatestAssistantMessage}
                approving={approving}
                styles={styles}
              />
              <ExecutionLaneStatusCard
                selectedApprovedContent={selectedApprovedContent}
                sessionLaneState={sessionLaneState}
                onRefreshStatus={refreshExecutionStatus}
                refreshing={refreshingExecutionStatus}
                onRetryExecution={retryLastExecution}
                onOpenComposer={openExecutionComposer}
                onOpenInspector={() => openInspector("summary")}
                interaction={agentInteraction}
                onRefreshInteraction={onRefreshAgentInteraction}
                onRespondInteraction={onRespondAgentInteraction}
                onCancelInteraction={onCancelAgentExecution}
                interactionSubmitting={agentInteractionSubmitting}
                interactionError={agentInteractionError}
                styles={styles}
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
                        executionResultPreview={message.role === "assistant" ? buildExecutionResultPreview(message) : ""}
                        // Mark Reviewed still writes legacy approved content until reviewed artifacts are implemented.
                        onApproveMessage={message.role === "assistant" ? approveMessage : null}
                        selectable={Boolean(message.id)}
                        selectedForExport={Boolean(message.id && selectedExportMessageIds?.includes(message.id))}
                        onToggleSelectedForExport={onToggleMessageExportSelection}
                        onRefreshExecutionStatus={refreshExecutionStatusForMessage}
                        onConfirmExecution={confirmExecutionForMessage}
                        confirmingExecution={confirmingExecution}
                        onRetryExecution={retryExecutionForMessage}
                        onLoginNotebookLm={launchNotebookLmLogin}
                        loggingInToNotebookLm={loggingInToNotebookLm}
                        baseUrl={baseUrl}
                        onUseArtifactInComposer={(artifact, options = {}) => {
                          setArtifactSuggestionForComposer(artifact);
                          setArtifactSuggestionsForComposer([]);
                          setArtifactPreferredTargetIdForComposer("");
                          setArtifactPreferredCommandKindForComposer(String(options?.commandKind || "").trim());
                          setArtifactPreferredAgentBackendForComposer(String(options?.agentBackend || "").trim());
                          setShowArtifactLibrary(true);
                          openExecutionComposer();
                        }}
                        onViewArtifactLibrary={() => setShowArtifactLibrary(true)}
                        onOpenInspector={(messageIndex) => openInspector(isExecutionTurn(messages[messageIndex]) ? "summary" : "details", messageIndex)}
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

          <div style={{ ...styles.details, display: "grid", gap: 8 }}>
            <div style={styles.label}>Upload artifact</div>
            <ArtifactUploadControl
              disabled={!appId}
              onUpload={(file, operationId, onProgress, signal) => onUploadArtifact(file, operationId, onProgress, signal)}
              onRetry={onRetryArtifactUpload}
            />
            <span style={styles.small}>
              Files are available to this chat and Agent execution. Successful uploads appear in Artifact Library.
            </span>
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
              <button
                type="button"
                style={styles.secondaryButton}
                onClick={() => {
                  setArtifactSuggestionForComposer(null);
                  setArtifactSuggestionsForComposer([]);
                  setArtifactPreferredTargetIdForComposer("");
                  setArtifactPreferredCommandKindForComposer("");
                  setArtifactPreferredAgentBackendForComposer("");
                  openExecutionComposer();
                }}
                disabled={!appId}
              >
                Run Tool or Skill
              </button>
              <button
                type="button"
                style={styles.secondaryButton}
                onClick={() => setShowArtifactLibrary((value) => !value)}
                disabled={!appId}
              >
                {showArtifactLibrary ? "Hide Artifact Library" : "Show Artifact Library"}
              </button>
              <button
                type="button"
                style={styles.secondaryButton}
                onClick={exportSelectedMessages}
                disabled={!appId || exportSelectionCount === 0 || exportingSelection}
              >
                {exportingSelection ? "Creating Reuse Artifact..." : `Create Reuse Artifact (${exportSelectionCount})`}
              </button>
            </div>
            {error && <div style={{ ...styles.error, marginTop: 12 }}>{error}</div>}
          </div>
        </section>
        {showExecutionComposer && (
          <div style={styles.executionComposerShelf}>
            <ExecutionComposer
              key={`${appId}:${sessionId}:${userId}`}
              toolInventory={toolInventory}
              skillInventory={skillInventory}
              agentSkillInventory={agentSkillInventory}
              agentSkillInventoryLoading={agentSkillInventoryLoading}
              agentSkillInventoryError={agentSkillInventoryError}
              agentSkillProjectionStatusByBackend={agentSkillProjectionStatusByBackend}
              artifactInventory={artifactInventory}
              onUploadExecutionInput={onUploadExecutionInput}
              onRetryArtifactUpload={onRetryArtifactUpload}
              initialArtifactSuggestion={artifactSuggestionForComposer}
              initialArtifactSuggestions={artifactSuggestionsForComposer}
              initialTargetId={artifactPreferredTargetIdForComposer}
              initialCommandKind={artifactPreferredCommandKindForComposer}
              initialAgentBackend={artifactPreferredAgentBackendForComposer}
              selectedApprovedContent={
                approvedContent.find((item) => item.approved_content_id === selectedApprovedContentId) || null
              }
              onRefreshAgentSkills={onRefreshAgentSkills}
              onSubmit={async (payload) => {
                await onRunExecutionComposer?.(payload);
                setArtifactSuggestionForComposer(null);
                setArtifactSuggestionsForComposer([]);
                setArtifactPreferredTargetIdForComposer("");
                setArtifactPreferredCommandKindForComposer("");
                setArtifactPreferredAgentBackendForComposer("");
                setShowExecutionComposer(false);
              }}
              onClose={() => {
                setArtifactSuggestionForComposer(null);
                setArtifactSuggestionsForComposer([]);
                setArtifactPreferredTargetIdForComposer("");
                setArtifactPreferredCommandKindForComposer("");
                setArtifactPreferredAgentBackendForComposer("");
                setShowExecutionComposer(false);
              }}
              styles={styles}
            />
          </div>
        )}
        {showArtifactLibrary ? (
          <ArtifactLibrary
            artifacts={artifactInventory}
            toolInventory={toolInventory}
            loading={artifactInventoryLoading}
            error={artifactInventoryError}
            onDeleteArtifact={onDeleteArtifact}
            baseUrl={baseUrl}
            onUseInNextStep={(artifact, options = {}) => {
              setArtifactSuggestionForComposer(artifact);
              setArtifactSuggestionsForComposer([]);
              setArtifactPreferredTargetIdForComposer(String(options?.preferredTargetId || "").trim());
              setArtifactPreferredCommandKindForComposer(String(options?.commandKind || "").trim());
              setArtifactPreferredAgentBackendForComposer(String(options?.agentBackend || "").trim());
              openExecutionComposer();
            }}
            onUseSelectedInNextStep={(artifacts, options = {}) => {
              const selectedArtifacts = Array.isArray(artifacts) ? artifacts : [];
              setArtifactSuggestionForComposer(selectedArtifacts[0] || null);
              setArtifactSuggestionsForComposer(selectedArtifacts);
              setArtifactPreferredTargetIdForComposer(String(options?.preferredTargetId || "").trim());
              setArtifactPreferredCommandKindForComposer(String(options?.commandKind || "agent").trim());
              setArtifactPreferredAgentBackendForComposer(String(options?.agentBackend || "openclaw_cli").trim());
              openExecutionComposer();
            }}
            onClose={() => setShowArtifactLibrary(false)}
            styles={styles}
          />
        ) : null}
      </div>
      {inspectedMessageIsExecution ? (
        <ExecutionInspector
          open={isInspectorOpen}
          tab={inspectorTab}
          onChangeTab={setInspectorTab}
          onClose={() => setIsInspectorOpen(false)}
          message={inspectedMessage}
          sessionLaneState={
            inspectedMessageIndex < 0 || inspectedMessageIndex === latestAssistantIndex
              ? sessionLaneState
              : null
          }
          styles={styles}
        />
      ) : (
        <RuntimeInspector
          open={isInspectorOpen}
          tab={inspectorTab}
          onChangeTab={setInspectorTab}
          onClose={() => setIsInspectorOpen(false)}
          message={inspectedMessage}
          workflowStatus={
            inspectedMessageIndex < 0 || inspectedMessageIndex === latestAssistantIndex
              ? workflowStatus
              : null
          }
          styles={styles}
          humanizeActionType={humanizeActionType}
          humanizePresentationMode={humanizePresentationMode}
          summarizePrimaryScope={summarizePrimaryScope}
        />
      )}
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
  const [approvedContentBySession, setApprovedContentBySession] = useState({});
  const [selectedApprovedContentIdBySession, setSelectedApprovedContentIdBySession] = useState({});
  const [selectedExportMessageIdsBySession, setSelectedExportMessageIdsBySession] = useState({});
  const [sessionLaneStateBySession, setSessionLaneStateBySession] = useState({});
  const [sessionUploadsBySession, setSessionUploadsBySession] = useState({});
  const [execToolInventory, setExecToolInventory] = useState([]);
  const [execSkillInventory, setExecSkillInventory] = useState([]);
  const [execAgentSkillInventoryByScope, setExecAgentSkillInventoryByScope] = useState({});
  const [execAgentSkillInventoryErrorByScope, setExecAgentSkillInventoryErrorByScope] = useState({});
  const [execAgentSkillInventoryLoadingByScope, setExecAgentSkillInventoryLoadingByScope] = useState({});
  const agentSkillInventoryRequestSequence = useRef({});
  const preparedExecutionSessionKeys = useRef(new Set());
  const executionSessionPreparationPromises = useRef(new Map());
  const [execArtifactInventory, setExecArtifactInventory] = useState([]);
  const [execArtifactInventoryLoading, setExecArtifactInventoryLoading] = useState(false);
  const [execArtifactInventoryError, setExecArtifactInventoryError] = useState("");
  const [sessions, setSessions] = useState([]);
  const [sessionTitleDraft, setSessionTitleDraft] = useState("");
  const [savingSessionTitle, setSavingSessionTitle] = useState(false);
  const [sessionSearch, setSessionSearch] = useState("");
  const [includeArchivedSessions, setIncludeArchivedSessions] = useState(false);
  const [actingSessionId, setActingSessionId] = useState("");
  const [agentInteractionsBySession, setAgentInteractionsBySession] = useState({});
  const [agentInteractionSubmitting, setAgentInteractionSubmitting] = useState(false);
  const [agentInteractionError, setAgentInteractionError] = useState("");

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
  const activeApprovedContent = approvedContentBySession[activeThreadKey] || [];
  const activeSelectedApprovedContentId =
    selectedApprovedContentIdBySession[activeThreadKey]
    || activeApprovedContent[activeApprovedContent.length - 1]?.approved_content_id
    || "";
  const activeSessionLaneState = sessionLaneStateBySession[activeThreadKey] || {};
  const activeExecutionLane = activeSessionLaneState.execution_lane || {};
  const activeExecutionId = activeExecutionLane.latest_execution_id || "";
  const activeExecutionStatus = String(
    activeExecutionLane.latest_status_result?.status
    || activeExecutionLane.latest_execution_result?.status
    || "",
  ).toLowerCase();
  const activeAgentInteractions = agentInteractionsBySession[activeThreadKey] || [];
  const activeAgentInteraction = activeAgentInteractions
    .filter((item) => item && typeof item === "object")
    .sort((left, right) => Number(right.sequence || 0) - Number(left.sequence || 0))
    .find((item) => item.state === "pending") || null;
  const activeSelectedExportMessageIds = selectedExportMessageIdsBySession[activeThreadKey] || [];
  const currentSession = sessions.find((session) => session.id === sessionId) || null;
  const activeAgentSkillScopeKeys = ["codex_cli", "openclaw_cli"].map((backend) => [
    backend,
    buildAgentSkillInventoryKey(selectedAppId, sessionId, userId, backend),
  ]);
  const activeAgentSkillInventory = activeAgentSkillScopeKeys.flatMap(([, key]) => (
    Array.isArray(execAgentSkillInventoryByScope[key]?.items)
      ? execAgentSkillInventoryByScope[key].items
      : []
  ));
  const activeAgentSkillProjectionStatusByBackend = Object.fromEntries(
    activeAgentSkillScopeKeys.map(([backend, key]) => [
      backend,
      String(execAgentSkillInventoryByScope[key]?.projection_status || "unavailable"),
    ]),
  );
  const activeAgentSkillInventoryError = activeAgentSkillScopeKeys
    .map(([, key]) => String(execAgentSkillInventoryErrorByScope[key] || "").trim())
    .find(Boolean) || "";
  const activeAgentSkillInventoryLoading = activeAgentSkillScopeKeys
    .some(([, key]) => execAgentSkillInventoryLoadingByScope[key] === true);
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

  const loadExecInventories = async () => {
    try {
      const skillQuery = new URLSearchParams();
      skillQuery.set("visibility", "user");
      if (selectedAppId) {
        skillQuery.set("app_id", selectedAppId);
      }
      const [toolData, skillData] = await Promise.all([
        fetchJson(`${baseUrl}/exec/tools`),
        fetchJson(`${baseUrl}/exec/skills?${skillQuery.toString()}`),
      ]);
      setExecToolInventory(Array.isArray(toolData?.items) ? toolData.items : []);
      setExecSkillInventory(Array.isArray(skillData?.items) ? skillData.items : []);
    } catch (e) {
      setAppError(String(e.message || e));
    }
  };

  const loadArtifactInventory = async (
    appIdOverride = selectedAppId,
    sessionIdOverride = sessionId,
    userIdOverride = userId,
  ) => {
    if (!appIdOverride || !sessionIdOverride || !userIdOverride) {
      setExecArtifactInventoryLoading(false);
      setExecArtifactInventoryError("");
      setExecArtifactInventory([]);
      return;
    }
    setExecArtifactInventoryLoading(true);
    setExecArtifactInventoryError("");
    try {
      const data = await fetchJson(
        `${baseUrl}/sessions/${sessionIdOverride}/artifacts?app_id=${encodeURIComponent(appIdOverride)}&user_id=${encodeURIComponent(userIdOverride)}`
      );
      setExecArtifactInventory(Array.isArray(data?.items) ? data.items : []);
      if (data?.warning) {
        setExecArtifactInventoryError(String(data.warning));
      }
    } catch (error) {
      setExecArtifactInventory([]);
      setExecArtifactInventoryError(String(error?.message || error || "Unknown error."));
    } finally {
      setExecArtifactInventoryLoading(false);
    }
  };

  const loadAgentSkillInventory = async (
    backend,
    appIdOverride = selectedAppId,
    sessionIdOverride = sessionId,
    userIdOverride = userId,
  ) => {
    if (!appIdOverride || !sessionIdOverride || !userIdOverride || !backend) {
      return;
    }
    const scopeKey = buildAgentSkillInventoryKey(
      appIdOverride,
      sessionIdOverride,
      userIdOverride,
      backend,
    );
    const sequence = (agentSkillInventoryRequestSequence.current[scopeKey] || 0) + 1;
    agentSkillInventoryRequestSequence.current[scopeKey] = sequence;
    setExecAgentSkillInventoryLoadingByScope((previous) => ({ ...previous, [scopeKey]: true }));
    setExecAgentSkillInventoryErrorByScope((previous) => ({ ...previous, [scopeKey]: "" }));
    try {
      const data = await fetchJson(
        `${baseUrl}/sessions/${sessionIdOverride}/exec/agent-skills`
        + `?app_id=${encodeURIComponent(appIdOverride)}`
        + `&user_id=${encodeURIComponent(userIdOverride)}`
        + `&backend=${encodeURIComponent(backend)}`,
      );
      if (agentSkillInventoryRequestSequence.current[scopeKey] !== sequence) {
        return;
      }
      setExecAgentSkillInventoryByScope((previous) => {
        const nextInventory = {
          items: Array.isArray(data?.items) ? data.items : [],
          inventory_revision: data?.inventory_revision ?? null,
          projection_status: String(data?.projection_status || "unavailable"),
        };
        const currentInventory = previous[scopeKey];
        if (
          nextInventory.inventory_revision !== null
          && currentInventory?.inventory_revision === nextInventory.inventory_revision
        ) {
          return previous;
        }
        return { ...previous, [scopeKey]: nextInventory };
      });
    } catch (error) {
      if (agentSkillInventoryRequestSequence.current[scopeKey] !== sequence) {
        return;
      }
      setExecAgentSkillInventoryByScope((previous) => ({
        ...previous,
        [scopeKey]: { items: [], inventory_revision: null, projection_status: "unavailable" },
      }));
      setExecAgentSkillInventoryErrorByScope((previous) => ({
        ...previous,
        [scopeKey]: String(error?.message || error || "Unable to load approved Agent Skills."),
      }));
    } finally {
      if (agentSkillInventoryRequestSequence.current[scopeKey] === sequence) {
        setExecAgentSkillInventoryLoadingByScope((previous) => ({ ...previous, [scopeKey]: false }));
      }
    }
  };

  const ensureExecutionSessionPrepared = async () => {
    if (!selectedAppId || !sessionId || !userId) {
      return;
    }
    if (currentSession || preparedExecutionSessionKeys.current.has(activeThreadKey)) {
      return;
    }
    const existingPreparation = executionSessionPreparationPromises.current.get(activeThreadKey);
    if (existingPreparation) {
      await existingPreparation;
      return;
    }
    const preparation = fetchJson(`${baseUrl}/sessions/${sessionId}/prepare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          app_id: selectedAppId,
          user_id: userId,
          config_version: 1,
          adapter_version: 1,
          template_version: 1,
        }),
      }).then(() => {
        preparedExecutionSessionKeys.current.add(activeThreadKey);
      }).finally(() => {
        executionSessionPreparationPromises.current.delete(activeThreadKey);
      });
    executionSessionPreparationPromises.current.set(activeThreadKey, preparation);
    await preparation;
  };

  const prepareExecutionComposer = async () => {
    if (!selectedAppId || !sessionId || !userId) {
      return;
    }
    const sessionWasDraft = !currentSession;
    await ensureExecutionSessionPrepared();
    await Promise.all([
      loadAgentSkillInventory("codex_cli", selectedAppId, sessionId, userId),
      loadAgentSkillInventory("openclaw_cli", selectedAppId, sessionId, userId),
    ]);
    if (sessionWasDraft) {
      await loadSessions(selectedAppId, userId, includeArchivedSessions);
    }
  };

  const refreshAgentSkills = async ({ backend = "", force = false } = {}) => {
    if (!selectedAppId || !sessionId || !userId) {
      return;
    }
    await ensureExecutionSessionPrepared();
    const requestedBackends = ["codex_cli", "openclaw_cli"].includes(backend)
      ? [backend]
      : ["codex_cli", "openclaw_cli"];
    await Promise.all(requestedBackends.map((requestedBackend) => (
      loadAgentSkillInventory(requestedBackend, selectedAppId, sessionId, userId, { force })
    )));
  };

  const uploadCanonicalArtifact = async (file, operationId, onProgress, analysisMode, signal) => {
    if (!selectedAppId || !sessionId || !userId || !file) {
      throw new Error("An application, session, user, and file are required.");
    }
    await ensureExecutionSessionPrepared();
    const data = await uploadArtifact({
      baseUrl,
      sessionId,
      appId: selectedAppId,
      userId,
      file,
      operationId,
      analysisMode,
      onProgress,
      signal,
    });
    const analysisResult = data?.analysis_result;
    if (analysisResult && typeof analysisResult === "object") {
      setThreadsBySession((prev) => ({
        ...prev,
        [activeThreadKey]: [...(prev[activeThreadKey] || []), appendAssistantMessage(analysisResult)],
      }));
      setSessionLaneStateBySession((prev) => ({
        ...prev,
        [activeThreadKey]: normalizeSessionLaneState(analysisResult.session_lane_state),
      }));
      await loadSessions(selectedAppId, userId, includeArchivedSessions);
    }
    await loadArtifactInventory(selectedAppId, sessionId, userId);
    return data;
  };

  const retryCanonicalArtifact = async (operationId) => {
    if (!selectedAppId || !sessionId || !userId || !operationId) {
      throw new Error("An application, session, user, and upload operation are required.");
    }
    await ensureExecutionSessionPrepared();
    const data = await retryArtifactUpload({
      baseUrl,
      sessionId,
      appId: selectedAppId,
      userId,
      operationId,
    });
    const analysisResult = data?.analysis_result;
    if (analysisResult && typeof analysisResult === "object") {
      setThreadsBySession((prev) => ({
        ...prev,
        [activeThreadKey]: [...(prev[activeThreadKey] || []), appendAssistantMessage(analysisResult)],
      }));
      setSessionLaneStateBySession((prev) => ({
        ...prev,
        [activeThreadKey]: normalizeSessionLaneState(analysisResult.session_lane_state),
      }));
      await loadSessions(selectedAppId, userId, includeArchivedSessions);
    }
    await loadArtifactInventory(selectedAppId, sessionId, userId);
    return data;
  };

  const uploadExecutionInput = (file, operationId, onProgress, signal) => (
    uploadCanonicalArtifact(file, operationId, onProgress, "none", signal)
  );

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

  const appendAssistantMessage = (data) => {
    const baseSummary = mergeTaskModelDiagnostics(
      data.retrieval_summary && typeof data.retrieval_summary === "object"
        ? { ...data.retrieval_summary }
        : {},
      data.task_model_diagnostics || data.taskModelDiagnostics,
    );
    if (data.execution_override && typeof data.execution_override === "object") {
      baseSummary.execution_override = true;
      baseSummary.command = data.execution_override.command;
      baseSummary.target_id = data.execution_override.target_id;
      baseSummary.skill_id = data.execution_override.skill_id;
      baseSummary.execution_id = data.execution_override.execution_id || "";
      baseSummary.agent_query = data.execution_override.agent_query || "";
      baseSummary.agent_skill_hint = data.execution_override.agent_skill_hint || "";
      baseSummary.approved_content_id = data.execution_override.approved_content_id;
      baseSummary.approved_revision_id = data.execution_override.approved_revision_id;
      baseSummary.execution_intent = data.execution_override.execution_intent || {};
      baseSummary.execution_submit_result = data.execution_override.submit_result || {};
      baseSummary.execution_status_result = data.execution_override.status_result || {};
      baseSummary.login_required = Boolean(data.execution_override.login_requirement?.auth_required);
    }
    return {
      id: data.id || data.message_id || null,
      role: "assistant",
      content: (data.content || "").trim() || "(No answer text returned by backend)",
      citations: data.citations || [],
      missingInfoTypes: data.missing_infoTypes || data.missingInfoTypes || [],
      retrievalSummary: baseSummary,
      workflowProgress: data.workflow_progress || {},
      turnExecutionPlan: data.turn_execution_plan || baseSummary.turn_execution_plan || {},
      sessionExecutionState: data.session_execution_state || baseSummary.session_execution_state || {},
    };
  };

  const sendQueryToSession = async (targetSessionId, rawQuery, options = {}) => {
    const targetThreadKey = buildThreadKey(selectedAppId, targetSessionId);
    const normalizedQuery = applyApprovedContentSelectionToExecQuery(
      rawQuery,
      selectedApprovedContentIdBySession[targetThreadKey] || "",
    );
    if (!selectedAppId || !normalizedQuery) {
      return;
    }
    if (instructionUnderstandingState.compileRequired) {
      throw new Error(instructionUnderstandingState.message);
    }
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
      ...(options.executionRequest ? { execution_request: options.executionRequest } : {}),
    };
    let data;
    try {
      data = await fetchJson(`${baseUrl}/sessions/${targetSessionId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } catch (queryError) {
      if (/^@exec\b/i.test(normalizedQuery)) {
        const errorTurn = buildExecutionSubmitErrorTurn(normalizedQuery, queryError);
        setThreadsBySession((prev) => ({
          ...prev,
          [targetThreadKey]: [...(prev[targetThreadKey] || []), errorTurn],
        }));
        return;
      }
      throw queryError;
    }
    setThreadsBySession((prev) => ({
      ...prev,
      [targetThreadKey]: [...(prev[targetThreadKey] || []), appendAssistantMessage(data)],
    }));
    setSessionLaneStateBySession((prev) => ({
      ...prev,
      [targetThreadKey]: normalizeSessionLaneState(data.session_lane_state),
    }));
    await loadSessions(selectedAppId, userId, includeArchivedSessions);
  };

  const runExecutionComposer = async ({ commandKind, targetId, args, executionMode }) => {
    const rawQuery = buildExecCommand({
      commandKind,
      targetId,
      args,
      executionMode,
      approvedContentId: activeSelectedApprovedContentId,
    });
    const executionRequest = buildExecutionRequestForComposer({
      commandKind,
      targetId,
      args,
      executionMode,
    });
    await sendQueryToSession(sessionId, rawQuery, { executionRequest });
  };

  const toggleMessageExportSelection = (messageId) => {
    const normalizedId = String(messageId || "").trim();
    if (!normalizedId) {
      return;
    }
    setSelectedExportMessageIdsBySession((prev) => {
      const current = new Set(prev[activeThreadKey] || []);
      if (current.has(normalizedId)) {
        current.delete(normalizedId);
      } else {
        current.add(normalizedId);
      }
      return {
        ...prev,
        [activeThreadKey]: [...current],
      };
    });
  };

  const exportSelectedMessages = async () => {
    if (!selectedAppId || !sessionId || !userId || activeSelectedExportMessageIds.length === 0) {
      return;
    }
    const data = await fetchJson(`${baseUrl}/sessions/${sessionId}/exports`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        app_id: selectedAppId,
        user_id: userId,
        message_ids: activeSelectedExportMessageIds,
        format: "md",
      }),
    });
    if (data?.summary_text) {
      const exportArtifact =
        data?.export_artifact && typeof data.export_artifact === "object"
          ? data.export_artifact
          : {};
      const exportResult =
        data?.export_result?.result && typeof data.export_result.result === "object"
          ? data.export_result.result
          : {};
      setThreadsBySession((prev) => ({
        ...prev,
        [activeThreadKey]: [
          ...(prev[activeThreadKey] || []),
          {
            id: null,
            role: "assistant",
            content: data.summary_text,
            citations: [],
            missingInfoTypes: [],
            retrievalSummary: {
              execution_override: true,
              command: "export",
              artifact_export: true,
              export_artifact: {
                ...exportArtifact,
                ...(exportResult.path ? { path: exportResult.path } : {}),
                ...(exportResult.file_path ? { file_path: exportResult.file_path } : {}),
              },
              execution_submit_result: data.export_result || {},
            },
            workflowProgress: {},
            turnExecutionPlan: {},
            sessionExecutionState: {},
          },
        ],
      }));
    }
    await loadArtifactInventory(selectedAppId, sessionId, userId);
    setSelectedExportMessageIdsBySession((prev) => ({
      ...prev,
      [activeThreadKey]: [],
    }));
  };

  const confirmExecutionForSession = async (executionId) => {
    if (!selectedAppId || !sessionId || !userId || !executionId) {
      return;
    }
    const data = await fetchJson(`${baseUrl}/sessions/${sessionId}/executions/${encodeURIComponent(executionId)}/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        app_id: selectedAppId,
        user_id: userId,
      }),
    });
    setThreadsBySession((prev) => ({
      ...prev,
      [activeThreadKey]: [...(prev[activeThreadKey] || []), appendAssistantMessage(data)],
    }));
    setSessionLaneStateBySession((prev) => ({
      ...prev,
      [activeThreadKey]: normalizeSessionLaneState(data.session_lane_state),
    }));
    await loadArtifactInventory(selectedAppId, sessionId, userId);
    await loadSessions(selectedAppId, userId, includeArchivedSessions);
  };

  const refreshAgentInteraction = async (executionIdOverride = activeExecutionId) => {
    const executionId = String(executionIdOverride || "").trim();
    if (!selectedAppId || !sessionId || !userId || !executionId) return;
    setAgentInteractionError("");
    try {
      const scope = `app_id=${encodeURIComponent(selectedAppId)}&user_id=${encodeURIComponent(userId)}`;
      const interactions = await fetchJson(
        `${baseUrl}/sessions/${sessionId}/executions/${encodeURIComponent(executionId)}/interactions?${scope}`,
      );
      setAgentInteractionsBySession((previous) => ({
        ...previous,
        [activeThreadKey]: Array.isArray(interactions.items) ? interactions.items : [],
      }));
      let latestLane = interactions.session_lane_state;
      const afterSequence = Number(
        interactions.session_lane_state?.execution_lane?.last_event_sequence
        || activeExecutionLane.last_event_sequence
        || 0,
      );
      const events = await fetchJson(
        `${baseUrl}/sessions/${sessionId}/executions/${encodeURIComponent(executionId)}/events?${scope}`
        + `&after_sequence=${encodeURIComponent(afterSequence)}&limit=100`,
      );
      latestLane = events.session_lane_state || latestLane;
      if (latestLane) {
        setSessionLaneStateBySession((previous) => ({
          ...previous,
          [activeThreadKey]: normalizeSessionLaneState(latestLane),
        }));
      }
    } catch (interactionError) {
      setAgentInteractionError(String(interactionError?.message || interactionError));
    }
  };

  const respondAgentInteraction = async (response) => {
    if (!activeExecutionId || !activeAgentInteraction) return;
    setAgentInteractionSubmitting(true);
    setAgentInteractionError("");
    try {
      const idempotencyKey = globalThis.crypto?.randomUUID?.()
        || `interaction-${Date.now()}-${activeAgentInteraction.interaction_id}`;
      const data = await fetchJson(
        `${baseUrl}/sessions/${sessionId}/executions/${encodeURIComponent(activeExecutionId)}`
        + `/interactions/${encodeURIComponent(activeAgentInteraction.interaction_id)}/responses`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            app_id: selectedAppId,
            user_id: userId,
            expected_version: activeAgentInteraction.version,
            idempotency_key: idempotencyKey,
            response,
          }),
        },
      );
      if (data.session_lane_state) {
        setSessionLaneStateBySession((previous) => ({
          ...previous,
          [activeThreadKey]: normalizeSessionLaneState(data.session_lane_state),
        }));
      }
      await refreshAgentInteraction(activeExecutionId);
    } catch (interactionError) {
      setAgentInteractionError(String(interactionError?.message || interactionError));
      const message = String(interactionError?.message || interactionError || "");
      if (message.includes("INTERACTION_VERSION_STALE") || message.includes("INTERACTION_CONFLICT")) {
        await refreshAgentInteraction(activeExecutionId);
      }
    } finally {
      setAgentInteractionSubmitting(false);
    }
  };

  const cancelAgentExecution = async () => {
    if (!activeExecutionId) return;
    setAgentInteractionSubmitting(true);
    setAgentInteractionError("");
    try {
      const data = await fetchJson(
        `${baseUrl}/sessions/${sessionId}/executions/${encodeURIComponent(activeExecutionId)}/cancel`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ app_id: selectedAppId, user_id: userId }),
        },
      );
      setAgentInteractionsBySession((previous) => ({ ...previous, [activeThreadKey]: [] }));
      if (data.session_lane_state) {
        setSessionLaneStateBySession((previous) => ({
          ...previous,
          [activeThreadKey]: normalizeSessionLaneState(data.session_lane_state),
        }));
      }
    } catch (interactionError) {
      setAgentInteractionError(String(interactionError?.message || interactionError));
    } finally {
      setAgentInteractionSubmitting(false);
    }
  };

  const sendStarterQuestionInNewSession = async (rawQuery) => {
    const nextSessionId = createSessionId();
    setSessionId(nextSessionId);
    setSessionTitleDraft("");
      setThreadsBySession((prev) => ({
        ...prev,
        [buildThreadKey(selectedAppId, nextSessionId)]: [],
      }));
      setApprovedContentBySession((prev) => ({
        ...prev,
        [buildThreadKey(selectedAppId, nextSessionId)]: [],
      }));
      setSelectedApprovedContentIdBySession((prev) => ({
        ...prev,
        [buildThreadKey(selectedAppId, nextSessionId)]: "",
      }));
      setSessionLaneStateBySession((prev) => ({
        ...prev,
        [buildThreadKey(selectedAppId, nextSessionId)]: {},
      }));
      setSessionUploadsBySession((prev) => ({
        ...prev,
        [buildThreadKey(selectedAppId, nextSessionId)]: [],
      }));
      setSelectedExportMessageIdsBySession((prev) => ({
        ...prev,
        [buildThreadKey(selectedAppId, nextSessionId)]: [],
      }));
    await sendQueryToSession(nextSessionId, rawQuery);
  };

  const uploadArtifactToSession = (file, operationId, onProgress, signal) => (
    uploadCanonicalArtifact(file, operationId, onProgress, "normal_query", signal)
  );

  const approveLatestAssistantMessage = async (message) => {
    if (!selectedAppId || !sessionId || !userId || !message?.content) {
      return;
    }
    const data = await fetchJson(`${baseUrl}/sessions/${sessionId}/approved-content`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        app_id: selectedAppId,
        user_id: userId,
        message_id: message.id || null,
        content_text: message.id ? null : message.content,
      }),
    });
    const approvedContent = Array.isArray(data.approved_content)
      ? data.approved_content
      : data.approved_content
        ? [data.approved_content]
        : [];
    setApprovedContentBySession((prev) => ({
      ...prev,
      [activeThreadKey]: approvedContent.length > 0
        ? [...(prev[activeThreadKey] || []), ...approvedContent]
        : prev[activeThreadKey] || [],
    }));
    const latestApprovedContentId =
      approvedContent[approvedContent.length - 1]?.approved_content_id
      || data.approved_content?.approved_content_id
      || "";
    if (latestApprovedContentId) {
      setSelectedApprovedContentIdBySession((prev) => ({
        ...prev,
        [activeThreadKey]: latestApprovedContentId,
      }));
    }
    if (data.summary_text) {
      setThreadsBySession((prev) => ({
        ...prev,
        [activeThreadKey]: [
          ...(prev[activeThreadKey] || []),
          {
            id: null,
            role: "assistant",
            content: data.summary_text,
            citations: [],
            missingInfoTypes: [],
            retrievalSummary: {
              approval_event: true,
              action_type: "approved_content_created",
              approved_content_id: latestApprovedContentId || null,
              reviewed_artifact: data.reviewed_artifact || null,
            },
            workflowProgress: {},
            turnExecutionPlan: {},
            sessionExecutionState: {},
          },
        ],
      }));
    }
    if (data.reviewed_artifact?.artifact_id) {
      await loadArtifactInventory(selectedAppId, sessionId, userId);
    }
    await loadSessions(selectedAppId, userId, includeArchivedSessions);
  };

  const selectApprovedContentForSession = (approvedContentId) => {
    if (!approvedContentId || approvedContentId === activeSelectedApprovedContentId) {
      return;
    }
    setSelectedApprovedContentIdBySession((prev) => ({
      ...prev,
      [activeThreadKey]: approvedContentId,
    }));
    const selectedItem = activeApprovedContent.find((item) => item.approved_content_id === approvedContentId);
    const summaryText = selectedItem?.revision_id
      ? `Selected approved revision \`${selectedItem.revision_id}\` for @exec.`
      : `Selected approved content \`${approvedContentId}\` for @exec.`;
    setThreadsBySession((prev) => ({
      ...prev,
      [activeThreadKey]: [
        ...(prev[activeThreadKey] || []),
        {
          id: null,
          role: "assistant",
          content: summaryText,
          citations: [],
          missingInfoTypes: [],
          retrievalSummary: {
            approval_event: true,
            action_type: "approved_content_selected",
            approved_content_id: approvedContentId,
          },
          workflowProgress: {},
          turnExecutionPlan: {},
          sessionExecutionState: {},
        },
      ],
    }));
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
      setApprovedContentBySession((prev) => {
        const next = { ...prev };
        delete next[buildThreadKey(selectedAppId, session.id)];
        return next;
      });
      setSelectedApprovedContentIdBySession((prev) => {
        const next = { ...prev };
        delete next[buildThreadKey(selectedAppId, session.id)];
        return next;
      });
      setSessionLaneStateBySession((prev) => {
        const next = { ...prev };
        delete next[buildThreadKey(selectedAppId, session.id)];
        return next;
      });
      setSessionUploadsBySession((prev) => {
        const next = { ...prev };
        delete next[buildThreadKey(selectedAppId, session.id)];
        return next;
      });
      setSelectedExportMessageIdsBySession((prev) => {
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

  const deleteArtifactFromSession = async (artifact) => {
    const artifactId = String(artifact?.artifact_id || "").trim();
    if (!artifactId || !selectedAppId || !sessionId || !userId) {
      return;
    }
    try {
      await fetchJson(
        `${baseUrl}/sessions/${sessionId}/artifacts/${encodeURIComponent(artifactId)}?app_id=${encodeURIComponent(selectedAppId)}&user_id=${encodeURIComponent(userId)}`,
        { method: "DELETE" },
      );
      await loadArtifactInventory(selectedAppId, sessionId, userId);
    } catch (e) {
      const message = artifactDeleteErrorMessage(e);
      setAppError(message);
      throw new Error(message);
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
    loadExecInventories();
  }, [baseUrl, selectedAppId]);

  useEffect(() => {
    if (!currentSession) {
      setExecArtifactInventoryLoading(false);
      setExecArtifactInventoryError("");
      setExecArtifactInventory([]);
      return;
    }
    loadArtifactInventory(selectedAppId, sessionId, userId);
  }, [baseUrl, selectedAppId, sessionId, userId, currentSession?.id]);

  useEffect(() => {
    if (!currentSession) {
      return;
    }
    void Promise.all([
      loadAgentSkillInventory("codex_cli", selectedAppId, sessionId, userId),
      loadAgentSkillInventory("openclaw_cli", selectedAppId, sessionId, userId),
    ]);
  }, [baseUrl, selectedAppId, sessionId, userId, currentSession?.id]);

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
    if (
      !["queued", "running"].includes(activeExecutionStatus)
      || !activeExecutionId
      || !selectedAppId
      || !sessionId
      || !userId
    ) {
      return undefined;
    }
    let cancelled = false;
    let timeout;
    const poll = async () => {
      try {
        const data = await fetchJson(
          `${baseUrl}/sessions/${sessionId}/executions/${encodeURIComponent(activeExecutionId)}`
          + `?app_id=${encodeURIComponent(selectedAppId)}&user_id=${encodeURIComponent(userId)}`,
        );
        if (!cancelled) {
          setSessionLaneStateBySession((prev) => ({
            ...prev,
            [activeThreadKey]: normalizeSessionLaneState(data.session_lane_state),
          }));
          const nextStatus = String(data.status_result?.status || "").toLowerCase();
          if (!["queued", "running"].includes(nextStatus)) {
            void loadArtifactInventory(selectedAppId, sessionId, userId);
          } else {
            timeout = window.setTimeout(poll, 1200);
          }
        }
      } catch (pollError) {
        if (!cancelled) {
          setAppError(String(pollError?.message || pollError));
        }
      }
    };
    timeout = window.setTimeout(poll, 1200);
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [
    activeExecutionId,
    activeExecutionStatus,
    activeThreadKey,
    baseUrl,
    selectedAppId,
    sessionId,
    userId,
  ]);

  useEffect(() => {
    if (!activeExecutionId || !selectedAppId || !sessionId || !userId) return undefined;
    let cancelled = false;
    let timeout;
    const poll = async () => {
      if (cancelled) return;
      await refreshAgentInteraction(activeExecutionId);
      const shouldContinue = activeAgentInteraction || [
        "queued",
        "running",
        "waiting",
        "waiting_for_input",
        "awaiting_input",
      ].includes(activeExecutionStatus);
      if (!cancelled && shouldContinue) {
        timeout = window.setTimeout(poll, 1500);
      }
    };
    void poll();
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [
    activeExecutionId,
    activeExecutionStatus,
    activeAgentInteraction?.interaction_id,
    activeAgentInteraction?.version,
    activeThreadKey,
  ]);

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
        setApprovedContentBySession((prev) => ({
          ...prev,
          [activeThreadKey]: Array.isArray(data.approved_content) ? data.approved_content : [],
        }));
        setSelectedApprovedContentIdBySession((prev) => {
          const approvedContent = Array.isArray(data.approved_content) ? data.approved_content : [];
          const currentSelection = prev[activeThreadKey] || "";
          const hasCurrentSelection = approvedContent.some(
            (item) => item.approved_content_id === currentSelection,
          );
          return {
            ...prev,
            [activeThreadKey]: hasCurrentSelection
              ? currentSelection
              : (approvedContent[approvedContent.length - 1]?.approved_content_id || ""),
          };
        });
        setSessionLaneStateBySession((prev) => ({
          ...prev,
          [activeThreadKey]: normalizeSessionLaneState(data.session_lane_state),
        }));
        setSessionUploadsBySession((prev) => ({
          ...prev,
          [activeThreadKey]: Array.isArray(data.session_uploads) ? data.session_uploads : [],
        }));
        setSelectedExportMessageIdsBySession((prev) => ({
          ...prev,
          [activeThreadKey]: prev[activeThreadKey] || [],
        }));
      } catch (e) {
        setThreadsBySession((prev) => ({
          ...prev,
          [activeThreadKey]: prev[activeThreadKey] || [],
        }));
        setApprovedContentBySession((prev) => ({
          ...prev,
          [activeThreadKey]: prev[activeThreadKey] || [],
        }));
        setSelectedApprovedContentIdBySession((prev) => ({
          ...prev,
          [activeThreadKey]: prev[activeThreadKey] || "",
        }));
        setSessionLaneStateBySession((prev) => ({
          ...prev,
          [activeThreadKey]: prev[activeThreadKey] || {},
        }));
        setSessionUploadsBySession((prev) => ({
          ...prev,
          [activeThreadKey]: prev[activeThreadKey] || [],
        }));
        setSelectedExportMessageIdsBySession((prev) => ({
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
              baseUrl={baseUrl}
              sessionId={sessionId}
              userId={userId}
              appId={selectedAppId}
              appName={activeAppDisplay.appName}
              starterQuestions={activeAppDisplay.starterQuestions}
              instructionUnderstandingState={instructionUnderstandingState}
              messages={activeMessages}
              approvedContent={activeApprovedContent}
              selectedApprovedContentId={activeSelectedApprovedContentId}
              sessionLaneState={activeSessionLaneState}
              workflowStatus={currentSession?.workflow_status || null}
              onSubmitQuery={(query) => sendQueryToSession(sessionId, query)}
              onSubmitStarterQuestion={sendStarterQuestionInNewSession}
              onAdvanceWorkflow={advanceWorkflowStep}
              onUploadArtifact={uploadArtifactToSession}
              onRetryArtifactUpload={retryCanonicalArtifact}
              onApproveLatestAssistantMessage={approveLatestAssistantMessage}
              onConfirmExecution={confirmExecutionForSession}
              agentInteraction={activeAgentInteraction}
              onRefreshAgentInteraction={refreshAgentInteraction}
              onRespondAgentInteraction={respondAgentInteraction}
              onCancelAgentExecution={cancelAgentExecution}
              agentInteractionSubmitting={agentInteractionSubmitting}
              agentInteractionError={agentInteractionError}
              onSelectApprovedContent={selectApprovedContentForSession}
              toolInventory={execToolInventory}
              skillInventory={execSkillInventory}
              agentSkillInventory={activeAgentSkillInventory}
              agentSkillInventoryLoading={activeAgentSkillInventoryLoading}
              agentSkillInventoryError={activeAgentSkillInventoryError}
              agentSkillProjectionStatusByBackend={activeAgentSkillProjectionStatusByBackend}
              artifactInventory={execArtifactInventory}
              artifactInventoryLoading={execArtifactInventoryLoading}
              artifactInventoryError={execArtifactInventoryError}
              onPrepareExecutionComposer={prepareExecutionComposer}
              onRefreshAgentSkills={refreshAgentSkills}
              onUploadExecutionInput={uploadExecutionInput}
              onRunExecutionComposer={runExecutionComposer}
              selectedExportMessageIds={activeSelectedExportMessageIds}
              onToggleMessageExportSelection={toggleMessageExportSelection}
              onExportSelectedMessages={exportSelectedMessages}
              onDeleteArtifact={deleteArtifactFromSession}
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




