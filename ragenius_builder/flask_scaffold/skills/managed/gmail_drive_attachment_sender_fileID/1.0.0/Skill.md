---
id: gmail_drive_attachment_sender_fileID
name: gmail-drive-attachment-sender-fileID
version: 1.0.0
description: Download a Google Drive file by file ID, store it as an app-scoped artifact, and create a Gmail draft with that file attached.
required_tools:
  - drive.download_file
  - gmail.create_draft_with_attachments
required_permissions:
  - external_api.read
  - artifact.write
  - artifact.read
  - external_api.write
---

# Gmail Drive Attachment Sender

Use this skill when the user wants to create a Gmail draft with an attachment sourced from Google Drive.

## Purpose

This skill follows the current RAGenius safe attachment boundary:

1. download or export a Google Drive file by `fileId`
2. save the file as an app-scoped artifact
3. create a Gmail draft with that artifact attached

This skill does not send the email immediately.

## Required Inputs

- `fileId`
- `to`
- `subject`
- `body`

## Optional Inputs

None.

## Input Contract

```json
{
  "fileId": "string",
  "to": "string",
  "subject": "string",
  "body": "string"
}

Execution Steps
1. Validate that fileId, to, subject, and body are present.
2. Call Google Drive download/export using the Drive MCP path.
3. Save the downloaded file as an app-scoped artifact.
4. Create a Gmail draft with the saved artifact attached.
5. Return draft metadata plus artifact/file metadata.

Output Contract
{
  "id": "string",
  "status": "string",
  "threadId": "string",
  "artifact_id": "string",
  "artifact_type": "string",
  "path": "string",
  "file_id": "string",
  "name": "string",
  "mime_type": "string"
}

Success Rules
Return:

- Gmail draft id
- draft status
- optional thread id
- artifact metadata
- Drive file metadata

Failure Rules
If validation fails:
- return a validation error
- do not fabricate results

If Drive download/export fails:
- return a file access or export failure
- do not continue to Gmail draft creation

If Gmail draft creation fails:
- return the Gmail failure
- do not claim success

Safety Rules
- Never use local filesystem paths as attachment input.
- Never expose credentials, OAuth tokens, internal URLs, or temporary download links.
- Only attach app-scoped artifacts created during the workflow.
- Do not send the message directly.
- Do not modify or delete Google Drive files.
