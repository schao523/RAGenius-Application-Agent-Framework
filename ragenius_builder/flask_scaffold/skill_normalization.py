from __future__ import annotations

import json
import re
from typing import Any, Dict

from policy import get_template_family_policy
from storage import DatabaseStore


SAFE_TEMPLATE_TOOL_MAP = {
    "file_inspection_report": ["list_files", "save_artifact"],
    "retrieval_report": ["retrieve_documents", "save_artifact"],
    "metadata_search_report": ["search_metadata", "save_artifact"],
    "research_paper_search_operation": ["research_paper_search_tool"],
    "content_patch": ["read_file", "patch_file", "save_artifact"],
    "content_replace": ["read_file", "write_file", "save_artifact"],
    "gmail_read_operation": ["mcp.gmail.search_messages"],
    "gmail_draft_operation": ["mcp.gmail.create_draft"],
    "gmail_send_draft_operation": ["mcp.gmail.send_draft"],
    "gmail_send_message_operation": ["mcp.gmail.send_message"],
    "google_docs_read_operation": ["mcp.gdocs.search_documents"],
    "google_drive_read_operation": ["mcp.gdrive.search_files"],
    "google_drive_export_operation": [
        "mcp.gdrive.download_file_content",
        "save_artifact",
    ],
    "google_drive_to_gmail_attachment_draft_operation": [
        "mcp.gdrive.download_file_content",
        "save_artifact",
        "mcp.gmail.create_draft_with_attachments",
    ],
    "mcp_write_operation": ["mcp.cms.create_page"],
    "mcp_read_operation": ["mcp.cms.search_pages"],
    "adapter_build": ["site_build_adapter"],
    "adapter_transform": ["content_transform_adapter"],
    "notebooklm_list_notebooks_operation": ["adapter.notebooklm.list_notebooks"],
    "notebooklm_list_sources_operation": ["adapter.notebooklm.list_sources"],
    "notebooklm_ask_operation": ["adapter.notebooklm.ask"],
    "notebooklm_add_source_text_operation": ["adapter.notebooklm.add_source_text"],
    "notebooklm_add_source_url_operation": ["adapter.notebooklm.add_source_url"],
    "notebooklm_add_source_file_operation": ["adapter.notebooklm.add_source_file"],
    "notebooklm_generate_report_operation": ["adapter.notebooklm.generate_report"],
    "notebooklm_generate_slide_deck_operation": ["adapter.notebooklm.generate_slide_deck"],
    "notebooklm_generate_video_operation": ["adapter.notebooklm.generate_video"],
}

EXPLICIT_REQUIRED_TOOL_TEMPLATE_MAP = {
    ("research_paper_search_tool",): "research_paper_search_operation",
    ("mcp.gmail.search_messages",): "gmail_read_operation",
    ("mcp.gmail.create_draft",): "gmail_draft_operation",
    ("mcp.gmail.create_draft_with_attachments",): "gmail_attachment_draft_operation",
    ("mcp.gmail.send_draft",): "gmail_send_draft_operation",
    ("mcp.gmail.send_message",): "gmail_send_message_operation",
    ("mcp.gdocs.search_documents",): "google_docs_read_operation",
    ("mcp.gdrive.search_files",): "google_drive_read_operation",
    ("mcp.gdrive.download_file_content",): "google_drive_export_operation",
    (
        "mcp.gdrive.download_file_content",
        "mcp.gmail.create_draft_with_attachments",
    ): "google_drive_to_gmail_attachment_draft_operation",
    ("adapter.notebooklm.list_notebooks",): "notebooklm_list_notebooks_operation",
    ("adapter.notebooklm.list_sources",): "notebooklm_list_sources_operation",
    ("adapter.notebooklm.ask",): "notebooklm_ask_operation",
    ("adapter.notebooklm.add_source_text",): "notebooklm_add_source_text_operation",
    ("adapter.notebooklm.add_source_url",): "notebooklm_add_source_url_operation",
    ("adapter.notebooklm.add_source_file",): "notebooklm_add_source_file_operation",
    ("adapter.notebooklm.generate_report",): "notebooklm_generate_report_operation",
    ("adapter.notebooklm.generate_slide_deck",): "notebooklm_generate_slide_deck_operation",
    ("adapter.notebooklm.generate_video",): "notebooklm_generate_video_operation",
}

AUTHOR_TOOL_ALIAS_MAP = {
    "gmail.search_messages": "mcp.gmail.search_messages",
    "gmail.create_draft": "mcp.gmail.create_draft",
    "gmail.create_draft_with_attachments": "mcp.gmail.create_draft_with_attachments",
    "gmail.send_draft": "mcp.gmail.send_draft",
    "gmail.send_message": "mcp.gmail.send_message",
    "drive.search_files": "mcp.gdrive.search_files",
    "drive.download_file": "mcp.gdrive.download_file_content",
    "drive.download_file_content": "mcp.gdrive.download_file_content",
    "docs.search_documents": "mcp.gdocs.search_documents",
    "notebooklm.list_notebooks": "adapter.notebooklm.list_notebooks",
    "notebooklm.list_sources": "adapter.notebooklm.list_sources",
    "notebooklm.ask": "adapter.notebooklm.ask",
    "notebooklm.add_source_text": "adapter.notebooklm.add_source_text",
    "notebooklm.add_source_url": "adapter.notebooklm.add_source_url",
    "notebooklm.add_source_file": "adapter.notebooklm.add_source_file",
    "notebooklm.generate_report": "adapter.notebooklm.generate_report",
    "notebooklm.generate_slide_deck": "adapter.notebooklm.generate_slide_deck",
    "notebooklm.generate_video": "adapter.notebooklm.generate_video",
}


def _manifest_list(manifest: Dict[str, Any], key: str) -> list[str]:
    value = manifest.get(key, [])
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _resolve_required_tools(required_tools: list[str]) -> list[str]:
    resolved: list[str] = []
    for tool_name in required_tools:
        normalized = str(tool_name).strip()
        if not normalized:
            continue
        resolved.append(AUTHOR_TOOL_ALIAS_MAP.get(normalized, normalized))
    return resolved


def _extract_body(markdown: str) -> str:
    text = str(markdown or "").replace("\r\n", "\n").replace("\r", "\n")
    parts = text.split("\n---\n", 1)
    return parts[1] if len(parts) == 2 else text


def _extract_section(markdown: str, title: str) -> str | None:
    body = _extract_body(markdown)
    pattern = (
        rf"(?ms)^(?:##\s*{re.escape(title)}\s*$|{re.escape(title)}\s*$\n[-=]+\s*$)"
        rf"(.*?)(?=^(?:##\s+[^\n]+$|[^\n]+\n[-=]+\s*$)|\Z)"
    )
    match = re.search(pattern, body)
    if not match:
        return None
    return match.group(1).strip()


def _extract_json_code_block(section_text: str | None) -> Dict[str, Any] | None:
    if not section_text:
        return None
    match = re.search(r"```json\s*(\{.*?\})\s*```", section_text, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _notebooklm_reference_input_schema(
    properties: Dict[str, Any],
    required: list[str],
) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "notebookId": {"type": "string"},
            "notebookTitle": {"type": "string"},
            **properties,
        },
        "required": required,
        "anyOf": [
            {"required": ["notebookId"]},
            {"required": ["notebookTitle"]},
        ],
    }


def _input_schema_for(template_family: str) -> Dict[str, Any]:
    if template_family == "content_patch":
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "patch": {"type": "string"},
            },
            "required": ["path", "patch"],
        }

    if template_family == "content_replace":
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        }

    if template_family == "mcp_write_operation":
        return {
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
        }

    if template_family == "gmail_read_operation":
        return {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }

    if template_family == "gmail_draft_operation":
        return {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        }

    if template_family == "gmail_attachment_draft_operation":
        return {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "artifactIds": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
            },
            "required": ["to", "subject", "body", "artifactIds"],
        }

    if template_family == "gmail_send_draft_operation":
        return {
            "type": "object",
            "properties": {"draftId": {"type": "string"}},
            "required": ["draftId"],
        }

    if template_family == "gmail_send_message_operation":
        return {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        }

    if template_family == "google_docs_read_operation":
        return {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }

    if template_family == "google_drive_read_operation":
        return {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }

    if template_family == "google_drive_export_operation":
        return {
            "type": "object",
            "properties": {"fileId": {"type": "string"}},
            "required": ["fileId"],
        }

    if template_family == "google_drive_to_gmail_attachment_draft_operation":
        return {
            "type": "object",
            "properties": {
                "fileId": {"type": "string"},
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["fileId", "to", "subject", "body"],
        }

    if template_family == "mcp_read_operation":
        return {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }

    if template_family == "adapter_build":
        return {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        }

    if template_family == "adapter_transform":
        return {
            "type": "object",
            "properties": {"content": {"type": "string"}},
            "required": ["content"],
        }

    if template_family == "notebooklm_list_notebooks_operation":
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    if template_family == "notebooklm_list_sources_operation":
        return _notebooklm_reference_input_schema({}, [])

    if template_family == "notebooklm_ask_operation":
        return _notebooklm_reference_input_schema(
            {
                "question": {"type": "string"},
                "sourceIds": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "conversationId": {"type": "string"},
            },
            ["question"],
        )

    if template_family == "notebooklm_add_source_text_operation":
        return _notebooklm_reference_input_schema(
            {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "wait": {"type": "boolean", "default": False},
            },
            ["title", "content"],
        )

    if template_family == "notebooklm_add_source_url_operation":
        return _notebooklm_reference_input_schema(
            {
                "url": {"type": "string"},
                "wait": {"type": "boolean", "default": False},
            },
            ["url"],
        )

    if template_family == "notebooklm_add_source_file_operation":
        return _notebooklm_reference_input_schema(
            {
                "filePath": {"type": "string"},
                "title": {"type": "string"},
                "mimeType": {"type": "string"},
                "wait": {"type": "boolean", "default": False},
            },
            ["filePath"],
        )

    if template_family == "notebooklm_generate_report_operation":
        return _notebooklm_reference_input_schema(
            {
                "sourceIds": {"type": "array", "items": {"type": "string"}},
                "reportFormat": {"type": "string"},
                "language": {"type": "string", "default": "en"},
                "customPrompt": {"type": "string"},
                "extraInstructions": {"type": "string"},
                "waitForCompletion": {"type": "boolean", "default": True},
                "persistArtifacts": {"type": "boolean", "default": True},
            },
            [],
        )

    if template_family == "notebooklm_generate_slide_deck_operation":
        return _notebooklm_reference_input_schema(
            {
                "sourceIds": {"type": "array", "items": {"type": "string"}},
                "language": {"type": "string", "default": "en"},
                "instructions": {"type": "string"},
                "slideFormat": {"type": "string"},
                "slideLength": {"type": "string"},
                "outputFormat": {
                    "type": "string",
                    "enum": ["pdf", "pptx"],
                    "default": "pdf",
                },
                "waitForCompletion": {"type": "boolean", "default": True},
                "persistArtifacts": {"type": "boolean", "default": True},
            },
            [],
        )

    if template_family == "notebooklm_generate_video_operation":
        return _notebooklm_reference_input_schema(
            {
                "sourceIds": {"type": "array", "items": {"type": "string"}},
                "language": {"type": "string", "default": "en"},
                "instructions": {"type": "string"},
                "videoFormat": {"type": "string"},
                "videoStyle": {"type": "string"},
                "stylePrompt": {"type": "string"},
                "waitForCompletion": {"type": "boolean", "default": True},
                "persistArtifacts": {"type": "boolean", "default": True},
            },
            [],
        )

    if template_family == "retrieval_report":
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 5,
                },
            },
            "required": ["query"],
        }

    if template_family == "metadata_search_report":
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 25,
                    "default": 10,
                },
            },
            "required": ["query"],
        }

    if template_family == "research_paper_search_operation":
        return {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 5,
                },
                "source": {
                    "type": "string",
                    "enum": ["auto", "arxiv", "semantic-scholar"],
                    "default": "auto",
                },
            },
            "required": ["topic"],
        }

    return {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }


def _output_schema_for(template_family: str) -> Dict[str, Any]:
    if template_family in {
        "gmail_read_operation",
        "google_docs_read_operation",
        "google_drive_read_operation",
        "mcp_read_operation",
    }:
        return {
            "type": "object",
            "properties": {
                "results": {
                    "type": "array",
                    "items": {"type": "object"},
                }
            },
            "required": ["results"],
        }

    if template_family == "gmail_draft_operation":
        return {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "status": {"type": "string"},
                "threadId": {"type": "string"},
            },
            "required": ["id", "status"],
        }

    if template_family == "gmail_attachment_draft_operation":
        return {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "status": {"type": "string"},
                "threadId": {"type": "string"},
            },
            "required": ["id", "status"],
        }

    if template_family == "gmail_send_draft_operation":
        return {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "status": {"type": "string"},
                "threadId": {"type": "string"},
            },
            "required": ["id", "status"],
        }

    if template_family == "gmail_send_message_operation":
        return {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "status": {"type": "string"},
                "threadId": {"type": "string"},
            },
            "required": ["id", "status"],
        }

    if template_family == "mcp_write_operation":
        return {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "title": {"type": "string"},
            },
            "required": ["id", "title"],
        }

    if template_family == "google_drive_export_operation":
        return {
            "type": "object",
            "properties": {
                "artifact_id": {"type": "string"},
                "artifact_type": {"type": "string"},
                "path": {"type": "string"},
                "file_id": {"type": "string"},
                "name": {"type": "string"},
                "mime_type": {"type": "string"},
            },
            "required": ["artifact_id", "artifact_type", "path", "file_id"],
        }

    if template_family == "google_drive_to_gmail_attachment_draft_operation":
        return {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "status": {"type": "string"},
                "threadId": {"type": "string"},
                "artifact_id": {"type": "string"},
                "artifact_type": {"type": "string"},
                "path": {"type": "string"},
                "file_id": {"type": "string"},
                "name": {"type": "string"},
                "mime_type": {"type": "string"},
            },
            "required": ["id", "status", "artifact_id", "file_id"],
        }

    if template_family in {"adapter_build", "adapter_transform"}:
        return {
            "type": "object",
            "properties": {"output": {"type": "string"}},
            "required": ["output"],
        }

    if template_family == "notebooklm_list_notebooks_operation":
        return {
            "type": "object",
            "properties": {
                "notebooks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "title": {"type": "string"},
                            "sources_count": {"type": "integer"},
                        },
                        "required": ["id", "title", "sources_count"],
                    },
                }
            },
            "required": ["notebooks"],
        }

    if template_family == "notebooklm_list_sources_operation":
        return {
            "type": "object",
            "properties": {
                "sources": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "title": {"type": "string"},
                            "kind": {"type": "string"},
                            "status": {"type": ["string", "null"]},
                        },
                        "required": ["id", "title", "kind"],
                    },
                }
            },
            "required": ["sources"],
        }

    if template_family == "notebooklm_ask_operation":
        return {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "conversation_id": {"type": "string"},
                "references": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source_id": {"type": "string"},
                            "title": {"type": "string"},
                        },
                        "required": ["source_id", "title"],
                    },
                },
                "turn_number": {"type": ["integer", "null"]},
            },
            "required": ["answer", "conversation_id", "references"],
        }

    if template_family in {
        "notebooklm_add_source_text_operation",
        "notebooklm_add_source_url_operation",
        "notebooklm_add_source_file_operation",
    }:
        return {
            "type": "object",
            "properties": {
                "notebook_id": {"type": "string"},
                "source": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "title": {"type": "string"},
                        "kind": {"type": "string"},
                        "status": {"type": "string"},
                    },
                    "required": ["id", "title", "kind"],
                },
            },
            "required": ["notebook_id", "source"],
        }

    if template_family == "notebooklm_generate_report_operation":
        return {
            "type": "object",
            "properties": {
                "notebook_id": {"type": "string"},
                "artifact_kind": {"type": "string"},
                "task_id": {"type": "string"},
                "status": {"type": "string"},
                "error": {"type": "string"},
                "error_code": {"type": "string"},
                "content_markdown": {"type": "string"},
                "download_path": {"type": "string"},
                "mime_type": {"type": "string"},
            },
            "required": ["notebook_id", "artifact_kind", "task_id", "status"],
        }

    if template_family == "notebooklm_generate_slide_deck_operation":
        return {
            "type": "object",
            "properties": {
                "notebook_id": {"type": "string"},
                "artifact_kind": {"type": "string"},
                "task_id": {"type": "string"},
                "status": {"type": "string"},
                "error": {"type": "string"},
                "error_code": {"type": "string"},
                "output_format": {"type": "string"},
                "download_path": {"type": "string"},
                "mime_type": {"type": "string"},
            },
            "required": ["notebook_id", "artifact_kind", "task_id", "status"],
        }

    if template_family == "notebooklm_generate_video_operation":
        return {
            "type": "object",
            "properties": {
                "notebook_id": {"type": "string"},
                "artifact_kind": {"type": "string"},
                "task_id": {"type": "string"},
                "status": {"type": "string"},
                "error": {"type": "string"},
                "error_code": {"type": "string"},
                "download_path": {"type": "string"},
                "mime_type": {"type": "string"},
            },
            "required": ["notebook_id", "artifact_kind", "task_id", "status"],
        }

    if template_family == "research_paper_search_operation":
        return {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "source": {"type": "string"},
                "papers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "link": {"type": "string"},
                            "year": {"type": "integer"},
                            "authors": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "summary": {"type": "string"},
                            "why_it_matters": {"type": "string"},
                        },
                        "required": [
                            "title",
                            "link",
                            "year",
                            "authors",
                            "summary",
                            "why_it_matters",
                        ],
                    },
                },
            },
            "required": ["topic", "source", "papers"],
        }

    return {
        "type": "object",
        "properties": {
            "artifact_id": {"type": "string"},
        },
        "required": ["artifact_id"],
    }


def _workflow_for(template_family: str) -> Dict[str, Any]:
    if template_family == "content_patch":
        return {
            "steps": [
                {
                    "id": "read_file",
                    "type": "tool_call",
                    "toolId": "read_file",
                    "inputMapping": {"path": "$.input.path"},
                    "outputMapping": {"content": "$.output.content"},
                    "on": {"success": "apply_patch"},
                },
                {
                    "id": "apply_patch",
                    "type": "tool_call",
                    "toolId": "patch_file",
                    "inputMapping": {
                        "path": "$.input.path",
                        "patch": "$.input.patch",
                        "format": "unified_diff",
                    },
                    "outputMapping": {
                        "path": "$.output.path",
                        "updated": "$.output.updated",
                        "summary": "$.output.summary",
                    },
                    "on": {"success": "save_report"},
                },
                {
                    "id": "save_report",
                    "type": "tool_call",
                    "toolId": "save_artifact",
                    "inputMapping": {
                        "artifact_type": "mutation_report",
                        "name": "patch-result",
                        "content": "$.steps.apply_patch.output",
                    },
                    "outputMapping": {"artifact_id": "$.output.artifact_id"},
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    if template_family == "gmail_read_operation":
        return {
            "steps": [
                {
                    "id": "search_messages",
                    "type": "service_call",
                    "serviceId": "mcp.gmail.search_messages",
                    "inputMapping": {"query": "$.input.query"},
                    "outputMapping": {"results": "$.output.results"},
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    if template_family == "gmail_draft_operation":
        return {
            "steps": [
                {
                    "id": "create_draft",
                    "type": "service_call",
                    "serviceId": "mcp.gmail.create_draft",
                    "inputMapping": {
                        "to": "$.input.to",
                        "subject": "$.input.subject",
                        "body": "$.input.body",
                    },
                    "outputMapping": {
                        "id": "$.output.id",
                        "status": "$.output.status",
                        "threadId": "$.output.threadId",
                    },
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    if template_family == "gmail_attachment_draft_operation":
        return {
            "steps": [
                {
                    "id": "create_draft_with_attachments",
                    "type": "service_call",
                    "serviceId": "mcp.gmail.create_draft_with_attachments",
                    "inputMapping": {
                        "to": "$.input.to",
                        "subject": "$.input.subject",
                        "body": "$.input.body",
                        "artifactIds": "$.input.artifactIds",
                    },
                    "outputMapping": {
                        "id": "$.output.id",
                        "status": "$.output.status",
                        "threadId": "$.output.threadId",
                    },
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    if template_family == "gmail_send_draft_operation":
        return {
            "steps": [
                {
                    "id": "send_draft",
                    "type": "service_call",
                    "serviceId": "mcp.gmail.send_draft",
                    "inputMapping": {"draftId": "$.input.draftId"},
                    "outputMapping": {
                        "id": "$.output.id",
                        "status": "$.output.status",
                        "threadId": "$.output.threadId",
                    },
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    if template_family == "gmail_send_message_operation":
        return {
            "steps": [
                {
                    "id": "send_message",
                    "type": "service_call",
                    "serviceId": "mcp.gmail.send_message",
                    "inputMapping": {
                        "to": "$.input.to",
                        "subject": "$.input.subject",
                        "body": "$.input.body",
                    },
                    "outputMapping": {
                        "id": "$.output.id",
                        "status": "$.output.status",
                        "threadId": "$.output.threadId",
                    },
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    if template_family == "google_docs_read_operation":
        return {
            "steps": [
                {
                    "id": "search_documents",
                    "type": "service_call",
                    "serviceId": "mcp.gdocs.search_documents",
                    "inputMapping": {"query": "$.input.query"},
                    "outputMapping": {"results": "$.output.results"},
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    if template_family == "google_drive_read_operation":
        return {
            "steps": [
                {
                    "id": "search_files",
                    "type": "service_call",
                    "serviceId": "mcp.gdrive.search_files",
                    "inputMapping": {"query": "$.input.query"},
                    "outputMapping": {"results": "$.output.results"},
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    if template_family == "google_drive_export_operation":
        return {
            "steps": [
                {
                    "id": "download_file_content",
                    "type": "service_call",
                    "serviceId": "mcp.gdrive.download_file_content",
                    "inputMapping": {"fileId": "$.input.fileId"},
                    "outputMapping": {
                        "file_id": "$.output.file_id",
                        "name": "$.output.name",
                        "mime_type": "$.output.mime_type",
                        "content": "$.output.content",
                        "content_encoding": "$.output.content_encoding",
                    },
                    "on": {"success": "save_artifact"},
                },
                {
                    "id": "save_artifact",
                    "type": "tool_call",
                    "toolId": "save_artifact",
                    "inputMapping": {
                        "artifact_type": "google_drive_export",
                        "name": "$.steps.download_file_content.output.name",
                        "content": "$.steps.download_file_content.output",
                    },
                    "outputMapping": {
                        "artifact_id": "$.output.artifact_id",
                        "path": "$.output.path",
                        "artifact_type": "$.output.artifact_type",
                        "file_id": "$.steps.download_file_content.output.file_id",
                        "name": "$.steps.download_file_content.output.name",
                        "mime_type": "$.steps.download_file_content.output.mime_type",
                    },
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    if template_family == "google_drive_to_gmail_attachment_draft_operation":
        return {
            "steps": [
                {
                    "id": "download_file_content",
                    "type": "service_call",
                    "serviceId": "mcp.gdrive.download_file_content",
                    "inputMapping": {"fileId": "$.input.fileId"},
                    "outputMapping": {
                        "file_id": "$.output.file_id",
                        "name": "$.output.name",
                        "mime_type": "$.output.mime_type",
                        "content": "$.output.content",
                        "content_encoding": "$.output.content_encoding",
                    },
                    "on": {"success": "save_artifact"},
                },
                {
                    "id": "save_artifact",
                    "type": "tool_call",
                    "toolId": "save_artifact",
                    "inputMapping": {
                        "artifact_type": "google_drive_export",
                        "name": "$.steps.download_file_content.output.name",
                        "content": "$.steps.download_file_content.output",
                    },
                    "outputMapping": {
                        "artifact_id": "$.output.artifact_id",
                        "path": "$.output.path",
                        "artifact_type": "$.output.artifact_type",
                        "file_id": "$.steps.download_file_content.output.file_id",
                        "name": "$.steps.download_file_content.output.name",
                        "mime_type": "$.steps.download_file_content.output.mime_type",
                    },
                    "on": {"success": "create_draft_with_attachments"},
                },
                {
                    "id": "create_draft_with_attachments",
                    "type": "service_call",
                    "serviceId": "mcp.gmail.create_draft_with_attachments",
                    "inputMapping": {
                        "to": "$.input.to",
                        "subject": "$.input.subject",
                        "body": "$.input.body",
                        "artifactIds": ["$.steps.save_artifact.output.artifact_id"],
                    },
                    "outputMapping": {
                        "id": "$.output.id",
                        "status": "$.output.status",
                        "threadId": "$.output.threadId",
                        "artifact_id": "$.steps.save_artifact.output.artifact_id",
                        "artifact_type": "$.steps.save_artifact.output.artifact_type",
                        "path": "$.steps.save_artifact.output.path",
                        "file_id": "$.steps.save_artifact.output.file_id",
                        "name": "$.steps.save_artifact.output.name",
                        "mime_type": "$.steps.save_artifact.output.mime_type",
                    },
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    if template_family == "content_replace":
        return {
            "steps": [
                {
                    "id": "read_file",
                    "type": "tool_call",
                    "toolId": "read_file",
                    "inputMapping": {"path": "$.input.path"},
                    "outputMapping": {"content": "$.output.content"},
                    "on": {"success": "write_file"},
                },
                {
                    "id": "write_file",
                    "type": "tool_call",
                    "toolId": "write_file",
                    "inputMapping": {
                        "path": "$.input.path",
                        "content": "$.input.content",
                        "if_exists": "overwrite",
                    },
                    "outputMapping": {
                        "path": "$.output.path",
                        "bytes_written": "$.output.bytes_written",
                        "updated": "$.output.updated",
                    },
                    "on": {"success": "save_report"},
                },
                {
                    "id": "save_report",
                    "type": "tool_call",
                    "toolId": "save_artifact",
                    "inputMapping": {
                        "artifact_type": "mutation_report",
                        "name": "write-result",
                        "content": "$.steps.write_file.output",
                    },
                    "outputMapping": {"artifact_id": "$.output.artifact_id"},
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    if template_family == "mcp_write_operation":
        return {
            "steps": [
                {
                    "id": "create_page",
                    "type": "tool_call",
                    "toolId": "mcp.cms.create_page",
                    "inputMapping": {"title": "$.input.title"},
                    "outputMapping": {
                        "id": "$.output.id",
                        "title": "$.output.title",
                    },
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    if template_family == "mcp_read_operation":
        return {
            "steps": [
                {
                    "id": "search_pages",
                    "type": "tool_call",
                    "toolId": "mcp.cms.search_pages",
                    "inputMapping": {"query": "$.input.query"},
                    "outputMapping": {"results": "$.output.results"},
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    if template_family == "adapter_build":
        return {
            "steps": [
                {
                    "id": "run_build",
                    "type": "tool_call",
                    "toolId": "site_build_adapter",
                    "inputMapping": {"path": "$.input.path"},
                    "outputMapping": {"output": "$.output.output"},
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    if template_family == "adapter_transform":
        return {
            "steps": [
                {
                    "id": "run_transform",
                    "type": "tool_call",
                    "toolId": "content_transform_adapter",
                    "inputMapping": {"content": "$.input.content"},
                    "outputMapping": {"output": "$.output.output"},
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    if template_family == "notebooklm_list_notebooks_operation":
        return {
            "steps": [
                {
                    "id": "list_notebooks",
                    "type": "service_call",
                    "serviceId": "adapter.notebooklm.list_notebooks",
                    "inputMapping": {},
                    "outputMapping": {"notebooks": "$.output.notebooks"},
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    if template_family == "notebooklm_list_sources_operation":
        return {
            "steps": [
                {
                    "id": "list_sources",
                    "type": "service_call",
                    "serviceId": "adapter.notebooklm.list_sources",
                    "inputMapping": {
                        "notebookId": "$.input.notebookId",
                        "notebookTitle": "$.input.notebookTitle",
                    },
                    "outputMapping": {"sources": "$.output.sources"},
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    if template_family == "notebooklm_ask_operation":
        return {
            "steps": [
                {
                    "id": "ask_notebooklm",
                    "type": "service_call",
                    "serviceId": "adapter.notebooklm.ask",
                    "inputMapping": {
                        "notebookId": "$.input.notebookId",
                        "notebookTitle": "$.input.notebookTitle",
                        "question": "$.input.question",
                        "sourceIds": "$.input.sourceIds",
                        "conversationId": "$.input.conversationId",
                    },
                    "outputMapping": {
                        "answer": "$.output.answer",
                        "conversation_id": "$.output.conversation_id",
                        "references": "$.output.references",
                        "turn_number": "$.output.turn_number",
                    },
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    if template_family == "notebooklm_add_source_text_operation":
        return {
            "steps": [
                {
                    "id": "add_source_text",
                    "type": "service_call",
                    "serviceId": "adapter.notebooklm.add_source_text",
                    "inputMapping": {
                        "notebookId": "$.input.notebookId",
                        "notebookTitle": "$.input.notebookTitle",
                        "title": "$.input.title",
                        "content": "$.input.content",
                        "wait": "$.input.wait",
                    },
                    "outputMapping": {
                        "notebook_id": "$.output.notebook_id",
                        "source": "$.output.source",
                    },
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    if template_family == "notebooklm_add_source_url_operation":
        return {
            "steps": [
                {
                    "id": "add_source_url",
                    "type": "service_call",
                    "serviceId": "adapter.notebooklm.add_source_url",
                    "inputMapping": {
                        "notebookId": "$.input.notebookId",
                        "notebookTitle": "$.input.notebookTitle",
                        "url": "$.input.url",
                        "wait": "$.input.wait",
                    },
                    "outputMapping": {
                        "notebook_id": "$.output.notebook_id",
                        "source": "$.output.source",
                    },
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    if template_family == "notebooklm_add_source_file_operation":
        return {
            "steps": [
                {
                    "id": "add_source_file",
                    "type": "service_call",
                    "serviceId": "adapter.notebooklm.add_source_file",
                    "inputMapping": {
                        "notebookId": "$.input.notebookId",
                        "notebookTitle": "$.input.notebookTitle",
                        "filePath": "$.input.filePath",
                        "title": "$.input.title",
                        "mimeType": "$.input.mimeType",
                        "wait": "$.input.wait",
                    },
                    "outputMapping": {
                        "notebook_id": "$.output.notebook_id",
                        "source": "$.output.source",
                    },
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    if template_family == "notebooklm_generate_report_operation":
        return {
            "steps": [
                {
                    "id": "generate_report",
                    "type": "service_call",
                    "serviceId": "adapter.notebooklm.generate_report",
                    "inputMapping": {
                        "notebookId": "$.input.notebookId",
                        "notebookTitle": "$.input.notebookTitle",
                        "sourceIds": "$.input.sourceIds",
                        "reportFormat": "$.input.reportFormat",
                        "language": "$.input.language",
                        "customPrompt": "$.input.customPrompt",
                        "extraInstructions": "$.input.extraInstructions",
                        "waitForCompletion": "$.input.waitForCompletion",
                        "persistArtifacts": "$.input.persistArtifacts",
                    },
                    "outputMapping": {
                        "notebook_id": "$.output.notebook_id",
                        "artifact_kind": "$.output.artifact_kind",
                        "task_id": "$.output.task_id",
                        "status": "$.output.status",
                        "error": "$.output.error",
                        "error_code": "$.output.error_code",
                        "content_markdown": "$.output.content_markdown",
                        "download_path": "$.output.download_path",
                        "mime_type": "$.output.mime_type",
                    },
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    if template_family == "notebooklm_generate_slide_deck_operation":
        return {
            "steps": [
                {
                    "id": "generate_slide_deck",
                    "type": "service_call",
                    "serviceId": "adapter.notebooklm.generate_slide_deck",
                    "inputMapping": {
                        "notebookId": "$.input.notebookId",
                        "notebookTitle": "$.input.notebookTitle",
                        "sourceIds": "$.input.sourceIds",
                        "language": "$.input.language",
                        "instructions": "$.input.instructions",
                        "slideFormat": "$.input.slideFormat",
                        "slideLength": "$.input.slideLength",
                        "outputFormat": "$.input.outputFormat",
                        "waitForCompletion": "$.input.waitForCompletion",
                        "persistArtifacts": "$.input.persistArtifacts",
                    },
                    "outputMapping": {
                        "notebook_id": "$.output.notebook_id",
                        "artifact_kind": "$.output.artifact_kind",
                        "task_id": "$.output.task_id",
                        "status": "$.output.status",
                        "error": "$.output.error",
                        "error_code": "$.output.error_code",
                        "output_format": "$.output.output_format",
                        "download_path": "$.output.download_path",
                        "mime_type": "$.output.mime_type",
                    },
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    if template_family == "notebooklm_generate_video_operation":
        return {
            "steps": [
                {
                    "id": "generate_video",
                    "type": "service_call",
                    "serviceId": "adapter.notebooklm.generate_video",
                    "inputMapping": {
                        "notebookId": "$.input.notebookId",
                        "notebookTitle": "$.input.notebookTitle",
                        "sourceIds": "$.input.sourceIds",
                        "language": "$.input.language",
                        "instructions": "$.input.instructions",
                        "videoFormat": "$.input.videoFormat",
                        "videoStyle": "$.input.videoStyle",
                        "stylePrompt": "$.input.stylePrompt",
                        "waitForCompletion": "$.input.waitForCompletion",
                        "persistArtifacts": "$.input.persistArtifacts",
                    },
                    "outputMapping": {
                        "notebook_id": "$.output.notebook_id",
                        "artifact_kind": "$.output.artifact_kind",
                        "task_id": "$.output.task_id",
                        "status": "$.output.status",
                        "error": "$.output.error",
                        "error_code": "$.output.error_code",
                        "download_path": "$.output.download_path",
                        "mime_type": "$.output.mime_type",
                    },
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    if template_family == "retrieval_report":
        return {
            "steps": [
                {
                    "id": "retrieve_documents",
                    "type": "tool_call",
                    "toolId": "retrieve_documents",
                    "inputMapping": {
                        "query": "$.input.query",
                        "top_k": "$.input.top_k",
                    },
                    "outputMapping": {"items": "$.output.items"},
                    "on": {"success": "save_report"},
                },
                {
                    "id": "save_report",
                    "type": "tool_call",
                    "toolId": "save_artifact",
                    "inputMapping": {
                        "artifact_type": "retrieval_report",
                        "name": "retrieval-summary",
                        "content": "$.steps.retrieve_documents.output.items",
                    },
                    "outputMapping": {"artifact_id": "$.output.artifact_id"},
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    if template_family == "metadata_search_report":
        return {
            "steps": [
                {
                    "id": "search_metadata",
                    "type": "tool_call",
                    "toolId": "search_metadata",
                    "inputMapping": {
                        "query": "$.input.query",
                        "limit": "$.input.limit",
                    },
                    "outputMapping": {"items": "$.output.items"},
                    "on": {"success": "save_report"},
                },
                {
                    "id": "save_report",
                    "type": "tool_call",
                    "toolId": "save_artifact",
                    "inputMapping": {
                        "artifact_type": "metadata_search_report",
                        "name": "metadata-summary",
                        "content": "$.steps.search_metadata.output.items",
                    },
                    "outputMapping": {"artifact_id": "$.output.artifact_id"},
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    if template_family == "research_paper_search_operation":
        return {
            "steps": [
                {
                    "id": "search_papers",
                    "type": "tool_call",
                    "toolId": "research_paper_search_tool",
                    "inputMapping": {
                        "topic": "$.input.topic",
                        "limit": "$.input.limit",
                        "source": "$.input.source",
                    },
                    "outputMapping": {
                        "topic": "$.output.topic",
                        "source": "$.output.source",
                        "papers": "$.output.papers",
                    },
                    "on": {"success": "finish"},
                },
                {"id": "finish", "type": "end"},
            ]
        }

    return {
        "steps": [
            {
                "id": "list_files",
                "type": "tool_call",
                "toolId": "list_files",
                "inputMapping": {"path": "$.input.path"},
                "outputMapping": {"entries": "$.output.entries"},
                "on": {"success": "save_report"},
            },
            {
                "id": "save_report",
                "type": "tool_call",
                "toolId": "save_artifact",
                "inputMapping": {
                    "artifact_type": "file_inventory",
                    "name": "file-inventory",
                    "content": "$.steps.list_files.output.entries",
                },
                "outputMapping": {"artifact_id": "$.output.artifact_id"},
                "on": {"success": "finish"},
            },
            {"id": "finish", "type": "end"},
        ]
    }


def normalize_skill_markdown(markdown: str) -> Dict[str, Any]:
    manifest = DatabaseStore._normalize_skill_manifest(
        DatabaseStore._parse_skill_manifest(markdown)
    )
    lowered = markdown.lower()
    explicit_input_schema = _extract_json_code_block(
        _extract_section(markdown, "Input Schema")
    )
    explicit_output_schema = _extract_json_code_block(
        _extract_section(markdown, "Expected Output")
    )
    required_tools = _manifest_list(manifest, "required_tools")
    resolved_required_tools = _resolve_required_tools(required_tools)

    explicit_template = EXPLICIT_REQUIRED_TOOL_TEMPLATE_MAP.get(tuple(resolved_required_tools))

    if explicit_template:
        template_family = explicit_template
    elif "list files" in lowered or "inspect a workspace path" in lowered:
        template_family = "file_inspection_report"
    elif "apply a patch" in lowered or "patch the file" in lowered:
        template_family = "content_patch"
    elif "replace the file" in lowered or "write the updated file" in lowered:
        template_family = "content_replace"
    elif "gmail" in lowered and "attach" in lowered and "draft" in lowered:
        template_family = "gmail_attachment_draft_operation"
    elif "gmail" in lowered and "send" in lowered and "draft" in lowered:
        template_family = "gmail_send_draft_operation"
    elif "gmail" in lowered and "send" in lowered:
        template_family = "gmail_send_message_operation"
    elif "gmail" in lowered and "draft" in lowered:
        template_family = "gmail_draft_operation"
    elif "gmail" in lowered and ("search" in lowered or "messages" in lowered):
        template_family = "gmail_read_operation"
    elif "google docs" in lowered and (
        "search" in lowered or "list" in lowered or "documents" in lowered
    ):
        template_family = "google_docs_read_operation"
    elif "google drive" in lowered and "gmail" in lowered and "attach" in lowered and "draft" in lowered:
        template_family = "google_drive_to_gmail_attachment_draft_operation"
    elif "google drive" in lowered and (
        "download" in lowered or "export" in lowered or "read" in lowered
    ):
        template_family = "google_drive_export_operation"
    elif "google drive" in lowered and (
        "search" in lowered or "list" in lowered or "files" in lowered
    ):
        template_family = "google_drive_read_operation"
    elif "mcp provider" in lowered and "create a page" in lowered:
        template_family = "mcp_write_operation"
    elif "mcp provider" in lowered and "search" in lowered:
        template_family = "mcp_read_operation"
    elif "adapter" in lowered and "build" in lowered:
        template_family = "adapter_build"
    elif "adapter" in lowered and "transform" in lowered:
        template_family = "adapter_transform"
    elif "retrieve" in lowered and "documents" in lowered:
        template_family = "retrieval_report"
    elif "metadata" in lowered:
        template_family = "metadata_search_report"
    else:
        template_family = "unsupported"

    policy = get_template_family_policy(template_family)
    candidate_tools = list(
        policy.get("inferred_tools", SAFE_TEMPLATE_TOOL_MAP.get(template_family, []))
    )
    if candidate_tools:
        manifest_policy_class = str(manifest.get("permission_class", "")).strip()
        policy_class = manifest_policy_class or str(
            policy.get("policy_class", "review_required")
        )
        auto_finalize = bool(policy.get("auto_finalize", False))
        required_permissions = list(policy.get("required_permissions", []))
    else:
        policy_class = "unsupported"
        auto_finalize = False
        required_permissions = []

    return {
        "name": str(manifest.get("name", "")).strip(),
        "description": str(manifest.get("description", "")).strip(),
        "template_family": template_family,
        "candidate_tools": candidate_tools,
        "required_tools": candidate_tools,
        "required_permissions": list(_manifest_list(manifest, "required_permissions") or required_permissions),
        "input_schema": explicit_input_schema or _input_schema_for(template_family)
        if candidate_tools
        else {},
        "output_schema": explicit_output_schema or _output_schema_for(template_family)
        if candidate_tools
        else {},
        "workflow_definition": _workflow_for(template_family)
        if candidate_tools
        else {},
        "policy_class": policy_class,
        "confidence": 0.95 if candidate_tools else 0.0,
        "auto_finalize": auto_finalize,
    }
