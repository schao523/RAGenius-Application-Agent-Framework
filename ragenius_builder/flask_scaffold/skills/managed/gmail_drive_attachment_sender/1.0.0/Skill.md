---

id: gmail_drive_attachment_sender

name: gmail-drive-attachment-sender

version: 1.0.0

description: Find files from Google Drive using file ID or exact filename, download or export them, attach them to Gmail messages, and send emails automatically using Gmail MCP and Drive MCP.

required_tools:

- gmail_mcp
- drive_mcp

required_permissions:

- gmail.send
- drive.readonly

execution_timeout: 120

execution_mode: deterministic

interaction_mode: fail_fast

patterns:

- tool-wrapper
- pipeline

category: communication

tags:

- gmail
- google-drive
- attachments
- email
- automation

inputs:

required:
- recipients
- subject
- body
- attachments
- send_instruction

optional:
- cc
- bcc
- export_format
- html_body
- reply_to

outputs:

success:
- status
- message_id
- recipients
- attachments
- warnings

failure:
- status
- error_code
- details
- retryable

---

# Skill Instructions

## Purpose

Send Gmail emails with attachments retrieved from Google Drive.

This skill executes deterministically.

All required inputs must already be provided.

No clarification or discovery workflow is used.

## Use Cases

Use this skill when the user wants to:

- send an email with one or more Google Drive attachments
- send files from Drive directly through Gmail
- automate attachment retrieval before email sending
- send exported Google Docs, Sheets, or Slides

Do NOT use this skill for:

- inbox management
- Drive uploads
- Drive permission management
- file deletion
- draft-only workflows
- conversational email composition

# Execution Rules

Execution is sequential.

Do not skip steps.

Stop immediately on validation failures.

Return structured errors.

# Input Requirements

Required:

- recipient email address or recipient list
- subject
- email body
- attachment references
- explicit send instruction

Attachment references may be:

- Drive file ID
- exact filename
- array of filenames
- array of file IDs

Optional:

- cc recipients
- bcc recipients
- export preferences
- HTML email body
- reply-to address

# Validation Rules

Validate before execution.

Recipient Validation:

- must exist
- must be valid email format
- remove duplicates

Attachment Validation:

- attachment references required
- file names require exact matching
- file IDs preferred
- folders are invalid

Message Validation:

- subject required
- body required
- explicit send intent required

If validation fails:

Return:

status: failed

error_code: validation_failed

retryable: true

# Execution Pipeline

## Step 1 — Parse Inputs

Extract:

- recipients
- cc
- bcc
- subject
- body
- attachments
- export preferences

Normalize:

- recipient arrays
- attachment arrays
- whitespace
- duplicate addresses

## Step 2 — Locate Drive Files

Use Drive MCP.

Search priority:

1. file ID lookup
2. exact filename lookup

Rules:

- exact filename matching only
- partial matches rejected
- multiple matches rejected

If no file found:

Return:

status: failed

error_code: drive_file_not_found

retryable: true

If multiple matches:

Return:

status: failed

error_code: ambiguous_file_match

retryable: true

## Step 3 — Validate Files

Validate:

- accessible
- downloadable
- not folder
- Gmail-compatible size
- exportable if Google-native

Reject:

- inaccessible files
- unsupported file objects
- oversized attachments

## Step 4 — Download or Export

Use Drive MCP.

Default exports:

Google Docs:

- PDF

Google Sheets:

- XLSX

Google Slides:

- PDF

Download attachments.

Never expose:

- access tokens
- temporary URLs
- internal identifiers
- filesystem paths

## Step 5 — Compose Email

Create Gmail payload.

Include:

- To
- CC
- BCC
- Subject
- Body
- Attachments

Validate:

- payload size
- attachment count
- recipient count

## Step 6 — Send Email

Use Gmail MCP.

Attach downloaded files.

Send immediately.

No confirmation step.

## Step 7 — Return Results

Success Format:

status: sent

message_id:

recipients:

attachments:

warnings:

Failure Format:

status: failed

error_code:

details:

retryable:

# Error Handling

Missing Inputs:

error_code:
missing_required_input

Drive File Missing:

error_code:
drive_file_not_found

Multiple Matches:

error_code:
ambiguous_file_match

Export Failure:

error_code:
attachment_export_failed

Authorization Failure:

error_code:
authorization_required

Gmail Send Failure:

error_code:
gmail_send_failed

# Safety Rules

Never:

- expose credentials
- expose OAuth tokens
- expose internal file URLs
- expose temporary download links
- modify Drive files
- delete Drive files

Always:

- use read-only Drive access
- validate recipients
- validate attachments
- fail safely

# Non-Goals

This skill does NOT:

- manage inbox messages
- upload files to Drive
- edit documents
- create Drive files
- search broadly across Drive using fuzzy matching
- ask follow-up questions

# Examples

Example 1:

Input:

to:

- [finance@example.com](mailto:finance@example.com)

subject:
May Invoice

body:
Please review attached invoice.

attachments:

- invoice-may-2026.pdf

send_instruction:
send_now

Behavior:

- locate file
- download file
- attach file
- send email

Example 2:

Input:

recipients:

- [team@example.com](mailto:team@example.com)

subject:
Quarterly Presentation

body:
Presentation attached.

attachments:

- 1B4CXYZFILEID

send_instruction:
send_now

Behavior:

- locate file by ID
- export if needed
- attach
- send
