# Artifact-First Chat Reuse GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the visible duplicate chat reuse paths with an artifact-first GUI where chat contents become reusable artifacts and Execution Composer consumes those artifacts.

**Architecture:** Keep existing backend and execution contracts compatible while changing the user-facing app flow. The frontend renames and consolidates chat reuse controls, Artifact Library remains the reusable artifact inventory, Execution Composer remains the artifact consumption surface, and Approved Content is demoted to a legacy compatibility disclosure instead of a primary panel.

**Tech Stack:** React, Vitest, Testing Library, existing `ragenius_app_skeleton` backend routes, existing `ragenius_execution_subsystem` artifact picker metadata.

---

## Source Documents

- Contract: `docs/artifact-first-chat-reuse-gui-contract.md`
- GUI design: `docs/artifact-first-chat-reuse-gui-design.md`
- Existing artifact library contract: `docs/artifact-library-contract.md`

## File Map

### Frontend Components

- Modify: `ragenius_app_skeleton/frontend/src/App.jsx`
  - Owns chat shell layout, selected message state, artifact export request, approved content state, Execution Composer opening, Artifact Library opening.
- Modify: `ragenius_app_skeleton/frontend/src/components/ChatMessageCard.jsx`
  - Owns per-turn actions and selected state badges.
- Modify: `ragenius_app_skeleton/frontend/src/components/ArtifactLibrary.jsx`
  - Owns artifact card actions and recommendation-to-composer flow.
- Modify: `ragenius_app_skeleton/frontend/src/components/ExecutionComposer.jsx`
  - Owns artifact field selectors and selected artifact removal.
- Modify: `ragenius_app_skeleton/frontend/src/components/ApprovedContentPanel.jsx`
  - Owns legacy approved-content disclosure during migration.

### Frontend Tests

- Modify: `ragenius_app_skeleton/frontend/src/App.test.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ChatMessageCard.test.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ArtifactLibrary.test.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ExecutionComposer.test.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ApprovedContentPanel.test.jsx`

### Backend And Execution

- Prefer no backend schema changes in the first GUI pass.
- Keep existing `POST /sessions/{session_id}/exports` as the artifact creation path.
- Keep existing approved-content endpoints and `approvedContentId` behavior for compatibility.
- Add reviewed artifact metadata later only if backend already exposes a safe metadata update path; otherwise create a separate backend plan before changing storage.

---

## Implementation Strategy

Use a safe incremental rollout:

1. Rename user-facing reuse copy without changing data contracts.
2. Improve artifact creation confirmation actions.
3. Demote Approved Content UI while preserving state and tests.
4. Keep Execution Composer and Artifact Library behavior stable.
5. Add reviewed-artifact behavior only after the base one-path UX is working.

This avoids breaking existing execution flows while removing the main user confusion.

---

## Task 1: Rename Chat Reuse Actions

**Files:**

- Modify: `ragenius_app_skeleton/frontend/src/components/ChatMessageCard.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ChatMessageCard.test.jsx`

- [ ] **Step 1: Write failing tests for reuse labels**

In `ChatMessageCard.test.jsx`, update or add assertions that expect the artifact-first copy:

```jsx
expect(screen.getByRole("button", { name: /select for reuse/i })).toBeInTheDocument();
expect(screen.queryByRole("button", { name: /select export/i })).not.toBeInTheDocument();
```

For selected state:

```jsx
expect(screen.getByRole("button", { name: /unselect reuse/i })).toBeInTheDocument();
expect(screen.getByText(/selected for reuse/i)).toBeInTheDocument();
```

- [ ] **Step 2: Run the focused test and verify failure**

Run from `ragenius_app_skeleton/frontend`:

```powershell
npm test -- ChatMessageCard.test.jsx
```

Expected failure: tests still find `Select Export`, `Unselect Export`, or `Selected for export`.

- [ ] **Step 3: Rename visible copy in `ChatMessageCard.jsx`**

Change selected badge:

```jsx
{selectedForExport && <span style={{ ...styles.pill, ...styles.statusOk }}>Selected for reuse</span>}
```

Change card title:

```jsx
title={exportSelectable ? "Click to select this message for reuse." : undefined}
```

Change action button:

```jsx
{selectedForExport ? "Unselect Reuse" : "Select for Reuse"}
```

Do not rename the internal prop names yet. Keeping `selectedForExport` and `onToggleSelectedForExport` avoids broad churn in this phase.

- [ ] **Step 4: Run focused test**

Run:

```powershell
npm test -- ChatMessageCard.test.jsx
```

Expected: PASS.

- [ ] **Step 5: Run related suite**

Run:

```powershell
npm test -- ChatMessageCard.test.jsx App.test.jsx
```

Expected: PASS.

---

## Task 2: Rename Bottom Action To Create Reuse Artifact

**Files:**

- Modify: `ragenius_app_skeleton/frontend/src/App.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/App.test.jsx`

- [ ] **Step 1: Write failing tests for bottom action copy**

In `App.test.jsx`, update tests that inspect the chat action bar to expect:

```jsx
expect(screen.getByRole("button", { name: /create reuse artifact \(0\)/i })).toBeDisabled();
```

When selected messages exist:

```jsx
expect(screen.getByRole("button", { name: /create reuse artifact \(1\)/i })).toBeEnabled();
```

For loading state:

```jsx
expect(screen.getByRole("button", { name: /creating reuse artifact/i })).toBeDisabled();
```

- [ ] **Step 2: Run failing app test**

Run from `ragenius_app_skeleton/frontend`:

```powershell
npm test -- App.test.jsx
```

Expected failure: old `Save Selected Chat` copy is still rendered.

- [ ] **Step 3: Rename visible copy in `App.jsx`**

Change the selected export button copy:

```jsx
{exportingSelection ? "Creating Reuse Artifact..." : `Create Reuse Artifact (${exportSelectionCount})`}
```

Keep the internal function name `exportSelectedMessages` for this task. It still calls the export endpoint, and renaming internals can happen in a cleanup task after behavior is stable.

- [ ] **Step 4: Add disabled helper text only when needed**

If the design needs a visible empty-state hint, add a compact helper near the button:

```jsx
{exportSelectionCount === 0 && (
  <span style={styles.small}>Select one or more chat turns to create a reusable artifact.</span>
)}
```

Do not add the helper if it crowds the action bar in the current layout. The disabled button label is sufficient for the first pass.

- [ ] **Step 5: Run app tests**

Run:

```powershell
npm test -- App.test.jsx
```

Expected: PASS.

---

## Task 3: Add Artifact Creation Confirmation Actions

**Files:**

- Modify: `ragenius_app_skeleton/frontend/src/App.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ChatMessageCard.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ChatMessageCard.test.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/App.test.jsx`

- [ ] **Step 1: Write failing test for confirmation action rendering**

In `ChatMessageCard.test.jsx`, create an execution/export artifact turn with:

```jsx
const message = {
  role: "assistant",
  content: "Created reuse artifact: Chat Export - Bible observation questions.md",
  retrievalSummary: {
    execution_override: true,
    command: "export",
    artifact_export: true,
    export_artifact: {
      artifact_id: "artifact_1",
      display_name: "Chat Export - Bible observation questions.md",
      artifact_type: "chat_export",
      routes: {
        open: "/sessions/session-1/artifacts/artifact_1/file",
        preview: "/sessions/session-1/artifacts/artifact_1/preview",
      },
      capabilities: {
        can_open: true,
        can_preview: true,
        can_reuse: true,
      },
    },
  },
};
```

Assert that the card shows:

```jsx
expect(screen.getByRole("button", { name: /use in execution composer/i })).toBeInTheDocument();
expect(screen.getByRole("button", { name: /view in artifact library/i })).toBeInTheDocument();
expect(screen.getByRole("link", { name: /open artifact/i })).toBeInTheDocument();
```

- [ ] **Step 2: Run failing test**

Run:

```powershell
npm test -- ChatMessageCard.test.jsx
```

Expected failure: confirmation actions do not exist yet.

- [ ] **Step 3: Add optional callbacks to `ChatMessageCard.jsx`**

Extend props:

```jsx
onUseArtifactInComposer,
onViewArtifactLibrary,
baseUrl,
```

Normalize artifact route links using the same route pattern as Artifact Library:

```jsx
function resolveRouteHref(baseUrl, routePath) {
  const normalizedBaseUrl = String(baseUrl || "").trim();
  const normalizedRoutePath = String(routePath || "").trim();
  if (!normalizedBaseUrl || !normalizedRoutePath) {
    return "";
  }
  try {
    return new URL(normalizedRoutePath, normalizedBaseUrl).toString();
  } catch {
    return "";
  }
}
```

- [ ] **Step 4: Render artifact confirmation actions**

Inside the `executionArtifacts.map` block, replace raw `file:///` opening behavior for export artifacts with backend routes when present:

```jsx
const openRoute = artifact.routes?.open || artifact.open_url || "";
const openHref = resolveRouteHref(baseUrl, openRoute);
```

Render:

```jsx
{artifact.artifact_id && onUseArtifactInComposer && (
  <button type="button" style={styles.inlineActionButton} onClick={() => onUseArtifactInComposer(artifact)}>
    Use in Execution Composer
  </button>
)}
{onViewArtifactLibrary && (
  <button type="button" style={styles.inlineActionButton} onClick={onViewArtifactLibrary}>
    View in Artifact Library
  </button>
)}
{openHref && (
  <a href={openHref} style={styles.inlineActionButton}>
    Open Artifact
  </a>
)}
```

Keep legacy raw-path display only in debug/inspector paths after the route-based action is available.

- [ ] **Step 5: Wire callbacks from `App.jsx`**

When rendering `ChatMessageCard`, pass:

```jsx
baseUrl={baseUrl}
onUseArtifactInComposer={(artifact) => {
  setArtifactSuggestionForComposer(artifact);
  setArtifactPreferredTargetIdForComposer("");
  setShowArtifactLibrary(true);
  setShowExecutionComposer(true);
}}
onViewArtifactLibrary={() => setShowArtifactLibrary(true)}
```

- [ ] **Step 6: Refresh artifacts after export creation**

In `exportSelectedMessages`, after a successful response and before clearing selection, call:

```jsx
await loadArtifactInventory(selectedAppId, sessionId, userId);
```

This ensures the created artifact appears in Artifact Library immediately.

- [ ] **Step 7: Run focused tests**

Run:

```powershell
npm test -- ChatMessageCard.test.jsx App.test.jsx
```

Expected: PASS.

---

## Task 4: Demote Approved Content Panel To Legacy Disclosure

**Files:**

- Modify: `ragenius_app_skeleton/frontend/src/components/ApprovedContentPanel.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ApprovedContentPanel.test.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/App.jsx`

- [ ] **Step 1: Write tests for collapsed legacy behavior**

In `ApprovedContentPanel.test.jsx`, add a test with existing approved content:

```jsx
expect(screen.getByText(/legacy approved content/i)).toBeInTheDocument();
expect(screen.queryByText(/selected revision: rev_1/i)).not.toBeInTheDocument();
```

Then click `Show`:

```jsx
fireEvent.click(screen.getByRole("button", { name: /show legacy approved content/i }));
expect(screen.getByText(/selected revision: rev_1/i)).toBeInTheDocument();
```

- [ ] **Step 2: Run failing approved-content test**

Run:

```powershell
npm test -- ApprovedContentPanel.test.jsx
```

Expected failure: panel is currently expanded and still labeled `Approved Content`.

- [ ] **Step 3: Add collapsed state to `ApprovedContentPanel.jsx`**

Add state:

```jsx
const [showLegacyPanel, setShowLegacyPanel] = useState(false);
```

Render compact disclosure when `items.length > 0 && !showLegacyPanel`:

```jsx
return (
  <section style={styles.approvedContentShell}>
    <div style={styles.approvedContentHeader}>
      <div>
        <div style={styles.sidebarSectionTitle}>Legacy Approved Content</div>
        <div style={styles.small}>A legacy approved revision is selected for older @exec flows.</div>
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
```

When expanded, use the existing full panel content but rename the title to:

```jsx
Legacy Approved Content
```

And selected badge to:

```jsx
Legacy selected for @exec
```

- [ ] **Step 4: Keep empty no-approved-content state compact**

When no approved content exists, either render nothing or a compact migration note. Prefer rendering nothing in the main chat UI to reduce clutter:

```jsx
if (items.length === 0) {
  return null;
}
```

Only do this if existing tests are updated to assert that no panel appears with empty approved content.

- [ ] **Step 5: Run tests**

Run:

```powershell
npm test -- ApprovedContentPanel.test.jsx App.test.jsx
```

Expected: PASS.

---

## Task 5: Replace Approve This Reply With Mark Reviewed Copy

**Files:**

- Modify: `ragenius_app_skeleton/frontend/src/components/ChatMessageCard.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ChatMessageCard.test.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/App.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/App.test.jsx`

- [ ] **Step 1: Write failing tests for Mark Reviewed copy**

In `ChatMessageCard.test.jsx`, update approval action expectation:

```jsx
expect(screen.getByRole("button", { name: /mark reviewed/i })).toBeInTheDocument();
expect(screen.queryByRole("button", { name: /approve this reply/i })).not.toBeInTheDocument();
```

- [ ] **Step 2: Run failing test**

Run:

```powershell
npm test -- ChatMessageCard.test.jsx
```

Expected failure: button still says `Approve This Reply`.

- [ ] **Step 3: Rename action copy only**

In `ChatMessageCard.jsx`, change:

```jsx
Mark Reviewed
```

Keep the callback name `onApproveMessage` for this phase because it still writes legacy approved content. Add an inline comment at the call site in `App.jsx`:

```jsx
// Mark Reviewed still writes legacy approved content until reviewed artifacts are implemented.
onApproveMessage={message.role === "assistant" ? approveMessage : null}
```

- [ ] **Step 4: Update approval-event confirmation copy**

In `approveLatestAssistantMessage` or the approval summary response handling, keep backend `summary_text` if supplied. If frontend creates fallback text, use:

```text
Marked reply as reviewed for legacy @exec compatibility.
```

- [ ] **Step 5: Run tests**

Run:

```powershell
npm test -- ChatMessageCard.test.jsx App.test.jsx ApprovedContentPanel.test.jsx
```

Expected: PASS.

---

## Task 6: Ensure Execution Composer Artifact UX Remains Stable

**Files:**

- Modify if needed: `ragenius_app_skeleton/frontend/src/components/ExecutionComposer.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ExecutionComposer.test.jsx`

- [ ] **Step 1: Add regression test for selected artifact removal**

In `ExecutionComposer.test.jsx`, assert that a compatible preselected artifact renders a `Remove` button and that clicking it clears selected state:

```jsx
fireEvent.click(screen.getByRole("button", { name: /remove chat export/i }));
expect(screen.getByText(/no artifact selected/i)).toBeInTheDocument();
```

- [ ] **Step 2: Add regression test for empty compatible selector**

Assert:

```jsx
expect(screen.getByText("Available artifacts")).toBeInTheDocument();
expect(screen.getByText(/no compatible artifacts are loaded for this field/i)).toBeInTheDocument();
```

- [ ] **Step 3: Run focused composer tests**

Run:

```powershell
npm test -- ExecutionComposer.test.jsx
```

Expected: PASS. If it fails, fix only the artifact selector or remove behavior; do not change execution command serialization in this task.

---

## Task 7: Artifact Library Card Badge And Action Cleanup

**Files:**

- Modify: `ragenius_app_skeleton/frontend/src/components/ArtifactLibrary.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ArtifactLibrary.test.jsx`

- [ ] **Step 1: Add test for reviewed badge support**

Use an artifact fixture:

```jsx
{
  artifact_id: "artifact_reviewed",
  artifact_type: "chat_export",
  artifact_type_label: "Chat Export",
  display_name: "Chat Export - Bible observation questions.md",
  summary: "Chat export from 2 selected messages.",
  reviewed: true,
  consumption: { default_mode: "file_backed", supported_modes: ["file_backed", "inline_text"] },
  capabilities: { can_open: true, can_preview: true, can_delete: true, can_reuse: true },
  routes: { open: "/artifact/file", preview: "/artifact/preview", delete: "/artifact" },
}
```

Assert:

```jsx
expect(screen.getByText(/reviewed/i)).toBeInTheDocument();
expect(screen.getByText(/file backed/i)).toBeInTheDocument();
```

- [ ] **Step 2: Run failing artifact library test**

Run:

```powershell
npm test -- ArtifactLibrary.test.jsx
```

Expected failure if reviewed badge is not yet rendered.

- [ ] **Step 3: Normalize reviewed metadata**

In `normalizeArtifacts`, add:

```jsx
reviewed: item.reviewed === true || item?.metadata?.reviewed === true,
reviewed_at: String(item.reviewed_at || item?.metadata?.reviewed_at || "").trim(),
reviewed_by: String(item.reviewed_by || item?.metadata?.reviewed_by || "").trim(),
```

- [ ] **Step 4: Render badges**

In the artifact card summary area, render:

```jsx
{artifact.reviewed && <span style={{ ...styles.pill, ...styles.statusOk }}>Reviewed</span>}
{artifact.consumption?.default_mode && (
  <span style={styles.pill}>{formatConsumptionMode(artifact.consumption.default_mode)}</span>
)}
```

- [ ] **Step 5: Run artifact library tests**

Run:

```powershell
npm test -- ArtifactLibrary.test.jsx
```

Expected: PASS.

---

## Task 8: App Integration Tests For One Reuse Path

**Files:**

- Modify: `ragenius_app_skeleton/frontend/src/App.test.jsx`

- [ ] **Step 1: Add integration test for artifact-first flow labels**

Render the app with a non-empty chat session and assert:

```jsx
expect(screen.getByRole("button", { name: /select for reuse/i })).toBeInTheDocument();
expect(screen.getByRole("button", { name: /create reuse artifact/i })).toBeInTheDocument();
expect(screen.queryByRole("button", { name: /save selected chat/i })).not.toBeInTheDocument();
expect(screen.queryByRole("button", { name: /approve this reply/i })).not.toBeInTheDocument();
```

- [ ] **Step 2: Add integration test for artifact confirmation action**

Mock export response:

```json
{
  "summary_text": "Created reuse artifact: Chat Export - Bible observation questions.md",
  "export_result": {
    "execution_id": "execution_1",
    "status": "completed",
    "result": {
      "artifact_id": "artifact_1",
      "file_path": "storage/artifacts/app/chat_export/artifact_1.md"
    }
  },
  "export_artifact": {
    "artifact_id": "artifact_1",
    "name": "Chat Export - Bible observation questions.md",
    "display_name": "Chat Export - Bible observation questions.md"
  }
}
```

Assert:

```jsx
expect(await screen.findByText(/created reuse artifact/i)).toBeInTheDocument();
expect(screen.getByRole("button", { name: /use in execution composer/i })).toBeInTheDocument();
```

- [ ] **Step 3: Run app tests**

Run:

```powershell
npm test -- App.test.jsx
```

Expected: PASS.

---

## Task 9: Full Frontend Verification

**Files:**

- No code changes expected.

- [ ] **Step 1: Run focused suites**

Run from `ragenius_app_skeleton/frontend`:

```powershell
npm test -- App.test.jsx ChatMessageCard.test.jsx ArtifactLibrary.test.jsx ExecutionComposer.test.jsx ApprovedContentPanel.test.jsx
```

Expected: all listed tests pass.

- [ ] **Step 2: Run broader frontend tests if time permits**

Run:

```powershell
npm test
```

Expected: all frontend tests pass. If unrelated tests fail, capture the failing test names and error summaries before deciding whether to patch.

- [ ] **Step 3: Manual GUI smoke test**

With the app running:

1. Open a session with assistant messages.
2. Confirm chat card shows `Select for Reuse`.
3. Select one message.
4. Confirm bottom button shows `Create Reuse Artifact (1)`.
5. Create the artifact.
6. Confirm the confirmation turn shows `Use in Execution Composer`.
7. Click it.
8. Confirm Execution Composer opens outside the sticky chat input and carries the artifact when compatible.
9. Open Artifact Library.
10. Confirm artifact has a friendly name and no raw id in the primary card title.

---

## Deferred Work

The following work is intentionally not included in this GUI-first implementation plan:

- Replacing the approved-content backend model with reviewed artifact storage.
- Removing `approvedContentId` from execution request schemas.
- Adding cross-session artifact reuse.
- Changing `rag_subsystem`.
- Moving any end-user chat flow into Builder.

Create a separate backend migration plan before removing approved-content APIs or storage.

---

## Self-Review

### Spec Coverage

- One primary reuse path: covered by Tasks 1, 2, 3, and 8.
- Artifact Library as reuse surface: covered by Tasks 3 and 7.
- Execution Composer artifact selection and removal: covered by Task 6.
- Approved Content demotion: covered by Tasks 4 and 5.
- Backward compatibility: preserved by keeping internal approved-content callbacks and `approvedContentId` behavior.
- Layout constraint: already patched before this plan; Task 9 manual smoke test verifies it stays correct.

### Placeholder Scan

No placeholder sections are used. Deferred work is explicitly scoped out and requires a separate plan.

### Type And Name Consistency

The plan intentionally keeps existing internal names such as `selectedForExport`, `onToggleSelectedForExport`, and `exportSelectedMessages` during the first GUI pass. User-facing labels change first; internal cleanup can happen later after behavior is stable.

