---
name: notebooklm-video-generator
description: Use NotebookLM tools to create a video from a selected notebook project.
version: 1.0
author: openclaw

capabilities:
  - name: generate_notebooklm_video
    description: Create a NotebookLM video from a selected notebook using the provided video instructions.

tools:
  - adapter.notebooklm.generate_video

permissions:
  - external_api.write

permission_class: review_required

execution:
  timeout: 300

metadata:
  pattern:
    - tool-wrapper
    - pipeline
  author_alias: notebooklm.generate_video
  domain: notebooklm
---

Skill Instructions
==================

Use this skill when the user wants to create a NotebookLM video from a selected notebook project.

Required Inputs
---------------

The user must provide:

- `instructions`
- either `notebookTitle` or `notebookId`

If both `notebookId` and `notebookTitle` are provided, pass both to the tool. Runtime will prefer `notebookId`.

Optional Inputs
---------------

- `sourceIds`
- `language`
- `videoFormat`
- `videoStyle`
- `stylePrompt`
- `waitForCompletion`
- `persistArtifacts`

Defaults
--------

If not provided:

- `language`: `en`
- `waitForCompletion`: `true`
- `persistArtifacts`: `true`

Input Schema
------------

```json
{
  "type": "object",
  "properties": {
    "notebookId": { "type": "string" },
    "notebookTitle": { "type": "string" },
    "instructions": { "type": "string" },
    "sourceIds": {
      "type": "array",
      "items": { "type": "string" }
    },
    "language": { "type": "string", "default": "en" },
    "videoFormat": { "type": "string" },
    "videoStyle": { "type": "string" },
    "stylePrompt": { "type": "string" },
    "waitForCompletion": { "type": "boolean", "default": true },
    "persistArtifacts": { "type": "boolean", "default": true }
  },
  "required": ["instructions"],
  "anyOf": [
    { "required": ["notebookId"] },
    { "required": ["notebookTitle"] }
  ]
}
```

Workflow
1. Validate that instructions is present.
2. Validate that either notebookTitle or notebookId is present.
3. Build the tool input without rewriting the user’s instructions.
4. Call adapter.notebooklm.generate_video.
5. Return the task/result metadata exactly and clearly.

Tool Call

Call:

adapter.notebooklm.generate_video

Effective payload:

{
  "notebookId": "string",
  "notebookTitle": "string",
  "sourceIds": ["string"],
  "language": "string",
  "instructions": "string",
  "videoFormat": "string",
  "videoStyle": "string",
  "stylePrompt": "string",
  "waitForCompletion": true,
  "persistArtifacts": true
}

Expected Output

Return:

{
  "notebook_id": "string",
  "artifact_kind": "video",
  "task_id": "string",
  "status": "string",
  "error": "string|null",
  "error_code": "string|null",
  "download_path": "string",
  "mime_type": "string"
}

Error Handling
- If neither notebookTitle nor notebookId is provided, ask for one.
- If instructions is missing, ask for the video instructions.
- If title resolution is ambiguous, return an error and ask the user to provide notebookId.
- If generation fails, return status, error, and error_code.
- If generation is still running, return task_id and current status.


Safety Rules
- Treat this as a write-side external action.
- Require review before execution.
- Do not modify notebook content, sources, or settings.
- Do not rewrite or expand the user’s instructions.
- Do not expose credentials, internal headers, or account/session data.