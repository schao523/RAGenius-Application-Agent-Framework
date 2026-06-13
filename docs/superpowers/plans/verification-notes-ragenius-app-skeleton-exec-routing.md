# RAGenius App Skeleton `@exec` Verification Notes

## Automated Verification

Run:

```powershell
python -m pytest ragenius_app_skeleton/backend/tests -q
```

Expected:

- `12 passed`
- normal non-`@exec` chat turns still route through the existing planner/chat pipeline
- explicit `@exec skill ...` turns do not invoke the normal planner path
- explicit `@exec status ...` turns do not invoke the normal planner path

## Manual Scenarios

1. Start a normal chat session and send a normal revision turn.
   - Expected: existing planner/chat behavior remains unchanged.

2. In the same session, send:

```text
@exec skill notebooklm_generate_video notebookTitle="GPT Application Designer" waitForCompletion=false
```

   - Expected: app creates or reuses an approved-content snapshot, builds an execution intent, and submits to `ragenius_execution_subsystem`.

3. In the same session, send:

```text
@exec status <execution_id>
```

   - Expected: app returns execution status without touching the normal planner path.

4. Return to a normal non-`@exec` chat turn after an execution override.
   - Expected: ordinary planner-based content flow still works and session continuity remains intact.
