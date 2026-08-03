# RAGenius Tools Inventory

Generated from the execution subsystem `/v1/tools/inventory` contract.
Use this file as designer-facing reference when creating Builder-managed skills.

Total tools: 27

## `adapter.notebooklm.add_source_file`

- Name: NotebookLM Add Source File
- Family: `adapter`
- Provider: `notebooklm`
- Enabled: `yes`
- Permission scopes: `external_api.write`
- Policy class: `review_required`
- Side effects: `write`
- Timeout ms: `120000`
- Fallback strategy: `-`

### Input Schema

```json
{
  "properties": {
    "filePath": {
      "type": "string"
    },
    "mimeType": {
      "type": "string"
    },
    "notebookId": {
      "type": "string"
    },
    "notebookTitle": {
      "type": "string"
    },
    "title": {
      "type": "string"
    },
    "wait": {
      "type": "boolean"
    }
  },
  "required": [
    "filePath"
  ],
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "notebook_id": {
      "type": "string"
    },
    "source": {
      "properties": {
        "id": {
          "type": "string"
        },
        "kind": {
          "type": "string"
        },
        "status": {
          "type": "string"
        },
        "title": {
          "type": "string"
        }
      },
      "required": [
        "id",
        "title",
        "kind"
      ],
      "type": "object"
    }
  },
  "required": [
    "notebook_id",
    "source"
  ],
  "type": "object"
}
```

### Metadata

```json
{
  "artifactPicker": {
    "accepted_artifact_types": [
      "chat_export"
    ],
    "enabled": true,
    "field_name": "filePath",
    "max_artifact_count": 1,
    "required_consumption_mode": "file_backed",
    "selection_mode": "single"
  },
  "policyClass": "review_required",
  "providerId": "notebooklm",
  "safePhase": 3
}
```

## `adapter.notebooklm.add_source_text`

- Name: NotebookLM Add Source Text
- Family: `adapter`
- Provider: `notebooklm`
- Enabled: `yes`
- Permission scopes: `external_api.write`
- Policy class: `review_required`
- Side effects: `write`
- Timeout ms: `30000`
- Fallback strategy: `-`

### Input Schema

```json
{
  "properties": {
    "content": {
      "type": "string"
    },
    "notebookId": {
      "type": "string"
    },
    "notebookTitle": {
      "type": "string"
    },
    "title": {
      "type": "string"
    },
    "wait": {
      "type": "boolean"
    }
  },
  "required": [
    "title",
    "content"
  ],
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "notebook_id": {
      "type": "string"
    },
    "source": {
      "properties": {
        "id": {
          "type": "string"
        },
        "kind": {
          "type": "string"
        },
        "status": {
          "type": "string"
        },
        "title": {
          "type": "string"
        }
      },
      "required": [
        "id",
        "title",
        "kind"
      ],
      "type": "object"
    }
  },
  "required": [
    "notebook_id",
    "source"
  ],
  "type": "object"
}
```

### Metadata

```json
{
  "policyClass": "review_required",
  "providerId": "notebooklm",
  "safePhase": 3
}
```

## `adapter.notebooklm.add_source_url`

- Name: NotebookLM Add Source URL
- Family: `adapter`
- Provider: `notebooklm`
- Enabled: `yes`
- Permission scopes: `external_api.write`
- Policy class: `review_required`
- Side effects: `write`
- Timeout ms: `30000`
- Fallback strategy: `-`

### Input Schema

```json
{
  "properties": {
    "notebookId": {
      "type": "string"
    },
    "notebookTitle": {
      "type": "string"
    },
    "url": {
      "type": "string"
    },
    "wait": {
      "type": "boolean"
    }
  },
  "required": [
    "url"
  ],
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "notebook_id": {
      "type": "string"
    },
    "source": {
      "properties": {
        "id": {
          "type": "string"
        },
        "kind": {
          "type": "string"
        },
        "status": {
          "type": "string"
        },
        "title": {
          "type": "string"
        }
      },
      "required": [
        "id",
        "title",
        "kind"
      ],
      "type": "object"
    }
  },
  "required": [
    "notebook_id",
    "source"
  ],
  "type": "object"
}
```

### Metadata

```json
{
  "policyClass": "review_required",
  "providerId": "notebooklm",
  "safePhase": 3
}
```

## `adapter.notebooklm.ask`

- Name: NotebookLM Ask
- Family: `adapter`
- Provider: `notebooklm`
- Enabled: `yes`
- Permission scopes: `external_api.read`
- Policy class: `review_required`
- Side effects: `read_only`
- Timeout ms: `20000`
- Fallback strategy: `-`

### Input Schema

```json
{
  "properties": {
    "conversationId": {
      "type": "string"
    },
    "notebookId": {
      "type": "string"
    },
    "notebookTitle": {
      "type": "string"
    },
    "question": {
      "type": "string"
    },
    "sourceIds": {
      "items": {
        "type": "string"
      },
      "type": "array"
    }
  },
  "required": [
    "question"
  ],
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "answer": {
      "type": "string"
    },
    "conversation_id": {
      "type": "string"
    },
    "references": {
      "items": {
        "properties": {
          "source_id": {
            "type": "string"
          },
          "title": {
            "type": "string"
          }
        },
        "required": [
          "source_id",
          "title"
        ],
        "type": "object"
      },
      "type": "array"
    },
    "turn_number": {
      "type": "number"
    }
  },
  "required": [
    "answer",
    "conversation_id",
    "references",
    "turn_number"
  ],
  "type": "object"
}
```

### Metadata

```json
{
  "policyClass": "review_required",
  "providerId": "notebooklm",
  "safePhase": 3
}
```

## `adapter.notebooklm.generate_report`

- Name: NotebookLM Generate Report
- Family: `adapter`
- Provider: `notebooklm`
- Enabled: `yes`
- Permission scopes: `external_api.write`
- Policy class: `review_required`
- Side effects: `write`
- Timeout ms: `180000`
- Fallback strategy: `-`

### Input Schema

```json
{
  "properties": {
    "customPrompt": {
      "type": "string"
    },
    "extraInstructions": {
      "type": "string"
    },
    "language": {
      "type": "string"
    },
    "notebookId": {
      "type": "string"
    },
    "notebookTitle": {
      "type": "string"
    },
    "persistArtifacts": {
      "type": "boolean"
    },
    "reportFormat": {
      "type": "string"
    },
    "sourceIds": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "waitForCompletion": {
      "type": "boolean"
    }
  },
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "artifact_kind": {
      "const": "report"
    },
    "artifacts": {
      "items": {
        "properties": {
          "app_id": {
            "type": "string"
          },
          "artifact_id": {
            "type": "string"
          },
          "artifact_type": {
            "type": "string"
          },
          "created_at": {
            "type": "string"
          },
          "display_name": {
            "type": "string"
          },
          "file_path": {
            "type": "string"
          },
          "mime_type": {
            "type": "string"
          },
          "path": {
            "type": "string"
          },
          "provider_origin": {
            "type": "string"
          },
          "size_bytes": {
            "type": "number"
          },
          "source_skill_id": {
            "type": "string"
          },
          "source_tool_id": {
            "type": "string"
          },
          "status": {
            "type": "string"
          },
          "summary": {
            "type": "string"
          }
        },
        "required": [
          "artifact_id",
          "artifact_type",
          "display_name",
          "app_id",
          "created_at",
          "provider_origin",
          "path",
          "status"
        ],
        "type": "object"
      },
      "type": "array"
    },
    "content_markdown": {
      "type": "string"
    },
    "download_path": {
      "type": "string"
    },
    "error": {
      "type": "string"
    },
    "error_code": {
      "type": "string"
    },
    "mime_type": {
      "type": "string"
    },
    "notebook_id": {
      "type": "string"
    },
    "status": {
      "type": "string"
    },
    "task_id": {
      "type": "string"
    }
  },
  "required": [
    "notebook_id",
    "artifact_kind",
    "task_id",
    "status"
  ],
  "type": "object"
}
```

### Metadata

```json
{
  "policyClass": "review_required",
  "providerId": "notebooklm",
  "safePhase": 3
}
```

## `adapter.notebooklm.generate_slide_deck`

- Name: NotebookLM Generate Slide Deck
- Family: `adapter`
- Provider: `notebooklm`
- Enabled: `yes`
- Permission scopes: `external_api.write`
- Policy class: `review_required`
- Side effects: `write`
- Timeout ms: `240000`
- Fallback strategy: `-`

### Input Schema

```json
{
  "properties": {
    "instructions": {
      "type": "string"
    },
    "language": {
      "type": "string"
    },
    "notebookId": {
      "type": "string"
    },
    "notebookTitle": {
      "type": "string"
    },
    "outputFormat": {
      "enum": [
        "pdf",
        "pptx"
      ],
      "type": "string"
    },
    "persistArtifacts": {
      "type": "boolean"
    },
    "slideFormat": {
      "type": "string"
    },
    "slideLength": {
      "type": "string"
    },
    "sourceIds": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "waitForCompletion": {
      "type": "boolean"
    }
  },
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "artifact_kind": {
      "const": "slide_deck"
    },
    "artifacts": {
      "items": {
        "properties": {
          "app_id": {
            "type": "string"
          },
          "artifact_id": {
            "type": "string"
          },
          "artifact_type": {
            "type": "string"
          },
          "created_at": {
            "type": "string"
          },
          "display_name": {
            "type": "string"
          },
          "file_path": {
            "type": "string"
          },
          "mime_type": {
            "type": "string"
          },
          "path": {
            "type": "string"
          },
          "provider_origin": {
            "type": "string"
          },
          "size_bytes": {
            "type": "number"
          },
          "source_skill_id": {
            "type": "string"
          },
          "source_tool_id": {
            "type": "string"
          },
          "status": {
            "type": "string"
          },
          "summary": {
            "type": "string"
          }
        },
        "required": [
          "artifact_id",
          "artifact_type",
          "display_name",
          "app_id",
          "created_at",
          "provider_origin",
          "path",
          "status"
        ],
        "type": "object"
      },
      "type": "array"
    },
    "download_path": {
      "type": "string"
    },
    "error": {
      "type": "string"
    },
    "error_code": {
      "type": "string"
    },
    "mime_type": {
      "type": "string"
    },
    "notebook_id": {
      "type": "string"
    },
    "output_format": {
      "type": "string"
    },
    "status": {
      "type": "string"
    },
    "task_id": {
      "type": "string"
    }
  },
  "required": [
    "notebook_id",
    "artifact_kind",
    "task_id",
    "status"
  ],
  "type": "object"
}
```

### Metadata

```json
{
  "policyClass": "review_required",
  "providerId": "notebooklm",
  "safePhase": 3
}
```

## `adapter.notebooklm.generate_video`

- Name: NotebookLM Generate Video
- Family: `adapter`
- Provider: `notebooklm`
- Enabled: `yes`
- Permission scopes: `external_api.write`
- Policy class: `review_required`
- Side effects: `write`
- Timeout ms: `240000`
- Fallback strategy: `-`

### Input Schema

```json
{
  "properties": {
    "instructions": {
      "type": "string"
    },
    "language": {
      "type": "string"
    },
    "notebookId": {
      "type": "string"
    },
    "notebookTitle": {
      "type": "string"
    },
    "persistArtifacts": {
      "type": "boolean"
    },
    "sourceIds": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "stylePrompt": {
      "type": "string"
    },
    "videoFormat": {
      "type": "string"
    },
    "videoStyle": {
      "type": "string"
    },
    "waitForCompletion": {
      "type": "boolean"
    }
  },
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "artifact_kind": {
      "const": "video"
    },
    "artifacts": {
      "items": {
        "properties": {
          "app_id": {
            "type": "string"
          },
          "artifact_id": {
            "type": "string"
          },
          "artifact_type": {
            "type": "string"
          },
          "created_at": {
            "type": "string"
          },
          "display_name": {
            "type": "string"
          },
          "file_path": {
            "type": "string"
          },
          "mime_type": {
            "type": "string"
          },
          "path": {
            "type": "string"
          },
          "provider_origin": {
            "type": "string"
          },
          "size_bytes": {
            "type": "number"
          },
          "source_skill_id": {
            "type": "string"
          },
          "source_tool_id": {
            "type": "string"
          },
          "status": {
            "type": "string"
          },
          "summary": {
            "type": "string"
          }
        },
        "required": [
          "artifact_id",
          "artifact_type",
          "display_name",
          "app_id",
          "created_at",
          "provider_origin",
          "path",
          "status"
        ],
        "type": "object"
      },
      "type": "array"
    },
    "download_path": {
      "type": "string"
    },
    "error": {
      "type": "string"
    },
    "error_code": {
      "type": "string"
    },
    "mime_type": {
      "type": "string"
    },
    "notebook_id": {
      "type": "string"
    },
    "status": {
      "type": "string"
    },
    "task_id": {
      "type": "string"
    }
  },
  "required": [
    "notebook_id",
    "artifact_kind",
    "task_id",
    "status"
  ],
  "type": "object"
}
```

### Metadata

```json
{
  "policyClass": "review_required",
  "providerId": "notebooklm",
  "safePhase": 3
}
```

## `adapter.notebooklm.list_notebooks`

- Name: NotebookLM List Notebooks
- Family: `adapter`
- Provider: `notebooklm`
- Enabled: `yes`
- Permission scopes: `external_api.read`
- Policy class: `review_required`
- Side effects: `read_only`
- Timeout ms: `10000`
- Fallback strategy: `-`

### Input Schema

```json
{
  "properties": {},
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "notebooks": {
      "items": {
        "properties": {
          "id": {
            "type": "string"
          },
          "sources_count": {
            "type": "number"
          },
          "title": {
            "type": "string"
          }
        },
        "required": [
          "id",
          "title",
          "sources_count"
        ],
        "type": "object"
      },
      "type": "array"
    }
  },
  "required": [
    "notebooks"
  ],
  "type": "object"
}
```

### Metadata

```json
{
  "policyClass": "review_required",
  "providerId": "notebooklm",
  "safePhase": 3
}
```

## `adapter.notebooklm.list_sources`

- Name: NotebookLM List Sources
- Family: `adapter`
- Provider: `notebooklm`
- Enabled: `yes`
- Permission scopes: `external_api.read`
- Policy class: `review_required`
- Side effects: `read_only`
- Timeout ms: `10000`
- Fallback strategy: `-`

### Input Schema

```json
{
  "properties": {
    "notebookId": {
      "type": "string"
    },
    "notebookTitle": {
      "type": "string"
    }
  },
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "sources": {
      "items": {
        "properties": {
          "id": {
            "type": "string"
          },
          "kind": {
            "type": "string"
          },
          "status": {
            "type": "string"
          },
          "title": {
            "type": "string"
          }
        },
        "required": [
          "id",
          "title",
          "kind"
        ],
        "type": "object"
      },
      "type": "array"
    }
  },
  "required": [
    "sources"
  ],
  "type": "object"
}
```

### Metadata

```json
{
  "policyClass": "review_required",
  "providerId": "notebooklm",
  "safePhase": 3
}
```

## `adapter.notebooklm.poll_artifact_task`

- Name: NotebookLM Poll Artifact Task
- Family: `adapter`
- Provider: `notebooklm`
- Enabled: `yes`
- Permission scopes: `external_api.read`
- Policy class: `external_read`
- Side effects: `read_only`
- Timeout ms: `30000`
- Fallback strategy: `-`

### Input Schema

```json
{
  "properties": {
    "artifactKind": {
      "enum": [
        "report",
        "slide_deck",
        "video"
      ],
      "type": "string"
    },
    "downloadIfComplete": {
      "type": "boolean"
    },
    "notebookId": {
      "type": "string"
    },
    "notebookTitle": {
      "type": "string"
    },
    "outputFormat": {
      "enum": [
        "pdf",
        "pptx"
      ],
      "type": "string"
    },
    "taskId": {
      "type": "string"
    }
  },
  "required": [
    "taskId",
    "artifactKind"
  ],
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "artifact_kind": {
      "enum": [
        "report",
        "slide_deck",
        "video"
      ],
      "type": "string"
    },
    "download_path": {
      "type": "string"
    },
    "error": {
      "type": "string"
    },
    "error_code": {
      "type": "string"
    },
    "mime_type": {
      "type": "string"
    },
    "notebook_id": {
      "type": "string"
    },
    "output_format": {
      "type": "string"
    },
    "status": {
      "type": "string"
    },
    "task_id": {
      "type": "string"
    }
  },
  "required": [
    "notebook_id",
    "artifact_kind",
    "task_id",
    "status"
  ],
  "type": "object"
}
```

### Metadata

```json
{
  "policyClass": "external_read",
  "providerId": "notebooklm",
  "safePhase": 1
}
```

## `content_transform_adapter`

- Name: Content Transform Adapter
- Family: `adapter`
- Provider: `custom_adapter`
- Enabled: `yes`
- Permission scopes: `adapter.execute`
- Policy class: `review_required`
- Side effects: `read_only`
- Timeout ms: `2000`
- Fallback strategy: `-`

### Input Schema

```json
{
  "properties": {
    "content": {
      "type": "string"
    }
  },
  "required": [
    "content"
  ],
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "output": {
      "type": "string"
    }
  },
  "required": [
    "output"
  ],
  "type": "object"
}
```

### Metadata

```json
{
  "policyClass": "review_required",
  "safePhase": 3
}
```

## `list_files`

- Name: List Files
- Family: `local`
- Provider: `filesystem`
- Enabled: `yes`
- Permission scopes: `filesystem.read`
- Policy class: `safe_read`
- Side effects: `read_only`
- Timeout ms: `5000`
- Fallback strategy: `-`

### Input Schema

```json
{
  "properties": {
    "depth": {
      "type": "number"
    },
    "glob": {
      "type": "string"
    },
    "include_dirs": {
      "type": "boolean"
    },
    "path": {
      "type": "string"
    },
    "recursive": {
      "type": "boolean"
    }
  },
  "required": [
    "path"
  ],
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "entries": {
      "items": {
        "properties": {
          "modified_at": {
            "type": "string"
          },
          "name": {
            "type": "string"
          },
          "path": {
            "type": "string"
          },
          "size_bytes": {
            "type": "number"
          },
          "type": {
            "enum": [
              "file",
              "directory"
            ],
            "type": "string"
          }
        },
        "required": [
          "path",
          "name",
          "type"
        ],
        "type": "object"
      },
      "type": "array"
    },
    "path": {
      "type": "string"
    }
  },
  "required": [
    "path",
    "entries"
  ],
  "type": "object"
}
```

### Metadata

```json
{
  "policyClass": "safe_read",
  "safePhase": 1
}
```

## `load_artifact`

- Name: Load Artifact
- Family: `local`
- Provider: `artifact_store`
- Enabled: `yes`
- Permission scopes: `artifact.read`
- Policy class: `artifact_safe`
- Side effects: `read_only`
- Timeout ms: `2000`
- Fallback strategy: `-`

### Input Schema

```json
{
  "properties": {
    "artifact_id": {
      "type": "string"
    }
  },
  "required": [
    "artifact_id"
  ],
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "app_id": {
      "type": "string"
    },
    "artifact_id": {
      "type": "string"
    },
    "artifact_type": {
      "type": "string"
    },
    "content": {
      "_def": {
        "typeName": "ZodUnknown"
      },
      "_unknown": true,
      "~standard": {
        "vendor": "zod",
        "version": 1
      }
    },
    "created_at": {
      "type": "string"
    },
    "created_by_execution_id": {
      "type": "string"
    },
    "created_by_turn_id": {
      "type": "string"
    },
    "display_name": {
      "type": "string"
    },
    "file_path": {
      "type": "string"
    },
    "mime_type": {
      "type": "string"
    },
    "path": {
      "type": "string"
    },
    "provider_origin": {
      "const": "local"
    },
    "size_bytes": {
      "type": "number"
    },
    "source_skill_id": {
      "type": "string"
    },
    "source_tool_id": {
      "type": "string"
    },
    "status": {
      "const": "ready"
    },
    "storage_file_name": {
      "type": "string"
    },
    "summary": {
      "type": "string"
    }
  },
  "required": [
    "artifact_id",
    "artifact_type",
    "path",
    "display_name",
    "app_id",
    "created_at",
    "provider_origin",
    "status",
    "content"
  ],
  "type": "object"
}
```

### Metadata

```json
{
  "policyClass": "artifact_safe",
  "safePhase": 1
}
```

## `mcp.gdrive.download_file_content`

- Name: Google Drive Download File
- Family: `mcp`
- Provider: `gdrive`
- Enabled: `yes`
- Permission scopes: `external_api.read`
- Policy class: `-`
- Side effects: `read_only`
- Timeout ms: `10000`
- Fallback strategy: `rest_api`

### Input Schema

```json
{
  "description": "Defines a request to download a file's content.",
  "properties": {
    "exportMimeType": {
      "description": "Optional. For Google native files, the MIME type to export the file to, ignored otherwise. Defaults to text if not specified.",
      "type": "string"
    },
    "fileId": {
      "description": "Required. The ID of the file to retrieve.",
      "type": "string"
    }
  },
  "required": [
    "fileId"
  ],
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "content": {
      "type": "string"
    },
    "content_encoding": {
      "type": "string"
    },
    "file_id": {
      "type": "string"
    },
    "mime_type": {
      "type": "string"
    },
    "name": {
      "type": "string"
    }
  },
  "required": [
    "file_id",
    "name",
    "mime_type",
    "content"
  ],
  "type": "object"
}
```

### Metadata

```json
{
  "capabilityVariant": "default",
  "providerId": "gdrive",
  "remoteDescription": "Call this tool to download the content of a Drive file as a base64 encoded string.\n\nIf the file is a Google Drive first-party mime type, the `exportMimeType` field is required and will determine the format of the downloaded file.\n\nIf the file is not found, try using other tools like `search_files` to find the file the user is requesting.\n\nIf the user wants a natural language representation of their Drive content, use the `read_file_content` tool (`read_file_content` should be smaller and easier to parse).\n",
  "remoteInputSchema": {
    "description": "Defines a request to download a file's content.",
    "properties": {
      "exportMimeType": {
        "description": "Optional. For Google native files, the MIME type to export the file to, ignored otherwise. Defaults to text if not specified.",
        "type": "string"
      },
      "fileId": {
        "description": "Required. The ID of the file to retrieve.",
        "type": "string"
      }
    },
    "required": [
      "fileId"
    ],
    "type": "object"
  },
  "remoteTitle": null,
  "remoteToolName": "download_file_content"
}
```

## `mcp.gdrive.search_files`

- Name: Google Drive Search
- Family: `mcp`
- Provider: `gdrive`
- Enabled: `yes`
- Permission scopes: `external_api.read`
- Policy class: `-`
- Side effects: `read_only`
- Timeout ms: `10000`
- Fallback strategy: `-`

### Input Schema

```json
{
  "description": "Request to search files.",
  "properties": {
    "excludeContentSnippets": {
      "description": "If true, the content snippet will be excluded from the response.",
      "type": "boolean"
    },
    "pageSize": {
      "description": "The maximum number of files to return in each page.",
      "format": "int32",
      "type": "integer"
    },
    "pageToken": {
      "description": "The page token to use for pagination.",
      "type": "string"
    },
    "query": {
      "description": "The search query.",
      "type": "string"
    }
  },
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "results": {
      "items": {
        "properties": {
          "id": {
            "type": "string"
          },
          "name": {
            "type": "string"
          }
        },
        "required": [
          "id"
        ],
        "type": "object"
      },
      "type": "array"
    }
  },
  "required": [
    "results"
  ],
  "type": "object"
}
```

### Metadata

```json
{
  "capabilityVariant": "default",
  "providerId": "gdrive",
  "remoteDescription": "Search for Drive files using a structured query (syntax: `query_term operator values`).\nCombine clauses with `and`, `or`, `not`, and parentheses. String values must be single-quoted; escape embedded quotes as `\\'`. \n\nQuery terms & operators:\n\n - `title` (ops: contains, =, !=) \u2014 file title\n - `fullText` (ops: contains) \u2014 title or body text\n - `mimeType` (ops: contains, =, !=) \u2014 MIME type\n - `modifiedTime`, `viewedByMeTime`, `createdTime` (ops: `<=`, `<`, `=`, `!=`, `>`, `>=`). Use RFC 3339 UTC, e.g., `2012-06-04T12:00:00-08:00`. Date types not comparable.\n - `parentId` (ops: `=`, `!=`). Use `'root'` for the user's \"My Drive\".\n - `owner` (ops: `=`, `!=`). Use `'me'` for the requesting user.\n - `sharedWithMe` (ops: `=`, `!=`). Values: `true` or `false`.\n\nOther operators: `and`, `or`, `not`.\n\nExamples:\n\n - `title contains 'hello' and title contains 'goodbye'`\n - `modifiedTime > '2024-01-01T00:00:00Z' and (mimeType contains 'image/' or mimeType contains 'video/')`\n - `parentId = '1234567'`\n - `fullText contains 'hello'`\n - `owner = 'test@example.org'`\n - `sharedWithMe = true`\n - `owner = 'me'` (for files owned by the user)\n\nUse `next_page_token` to paginate. An empty response means no more results.\n",
  "remoteInputSchema": {
    "description": "Request to search files.",
    "properties": {
      "excludeContentSnippets": {
        "description": "If true, the content snippet will be excluded from the response.",
        "type": "boolean"
      },
      "pageSize": {
        "description": "The maximum number of files to return in each page.",
        "format": "int32",
        "type": "integer"
      },
      "pageToken": {
        "description": "The page token to use for pagination.",
        "type": "string"
      },
      "query": {
        "description": "The search query.",
        "type": "string"
      }
    },
    "type": "object"
  },
  "remoteTitle": null,
  "remoteToolName": "search_files"
}
```

## `mcp.gmail.create_draft`

- Name: Gmail Create Draft
- Family: `mcp`
- Provider: `gmail`
- Enabled: `yes`
- Permission scopes: `external_api.write`
- Policy class: `-`
- Side effects: `write`
- Timeout ms: `10000`
- Fallback strategy: `rest_api`

### Input Schema

```json
{
  "$defs": {
    "Attachment": {
      "description": "Represents an attachment to be included in an email.",
      "properties": {
        "content": {
          "description": "Required. The base64-encoded content of the attachment.",
          "format": "byte",
          "type": "string"
        },
        "filename": {
          "description": "Optional. The name of the file to be attached, e.g. \"invoice.pdf\". For inline attachments, this is used for Content-ID generation. For regular attachments, filename is used to specify the filename to email clients. If not provided, the attachment may be received with no name.",
          "type": "string"
        },
        "id": {
          "description": "Optional. Output only. When present, contains the ID of an external attachment that can be retrieved in a separate `GetMessageAttachment` request.",
          "readOnly": true,
          "type": "string"
        },
        "inline": {
          "description": "Optional. If true, this attachment is handled as inline. An inline attachment is a content that is intended to be displayed within the body of an HTML email, as opposed to being listed as a separate file for download. If false or absent, defaults to false, and it's treated as a regular attachment.",
          "type": "boolean"
        },
        "mimeType": {
          "description": "Optional. The field representing a content or media type must use IANA MIME type, https://www.iana.org/assignments/media-types/media-types.xhtml. If not provided, defaults to \"application/octet-stream\".",
          "type": "string"
        }
      },
      "type": "object"
    }
  },
  "description": "Request message for CreateDraft RPC.",
  "properties": {
    "attachments": {
      "description": "Optional. The attachments to include in the email. The combined size of attachments in the message cannot exceed 25MB. If you need to send files larger than 25MB, upload the file to Drive first and then insert the Drive link into body or html_body.",
      "items": {
        "$ref": "#/$defs/Attachment"
      },
      "type": "array"
    },
    "bcc": {
      "description": "Optional. The blind carbon copy recipients of the email draft. Each string MUST be a valid plain email address (e.g., \"user@example.com\"). The \"Name \" format is NOT supported by this tool.",
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "body": {
      "description": "Optional. The main body content of the email draft. If html_body is also provided, this field is treated as the plain-text alternative.",
      "type": "string"
    },
    "cc": {
      "description": "Optional. The carbon copy recipients of the email draft. Each string MUST be a valid plain email address (e.g., \"user@example.com\"). The \"Name \" format is NOT supported by this tool.",
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "htmlBody": {
      "description": "The HTML content of the email draft. If provided, this will be used as the rich-text version of the email.",
      "type": "string"
    },
    "replyToMessageId": {
      "description": "Optional. The ID of the message to reply to. If provided, this will be used as the reply-to message ID for the email draft, and the `body` and `html_body` will be appended to the original message body.",
      "type": "string"
    },
    "subject": {
      "description": "Optional. The subject line of the email. Defaults to empty if not provided.",
      "type": "string"
    },
    "to": {
      "description": "Required. The primary recipients of the email draft. Each string MUST be a valid plain email address (e.g., \"user@example.com\"). The \"Name \" format is NOT supported by this tool.",
      "items": {
        "type": "string"
      },
      "type": "array"
    }
  },
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "id": {
      "type": "string"
    },
    "status": {
      "type": "string"
    },
    "threadId": {
      "type": "string"
    }
  },
  "required": [
    "id",
    "status"
  ],
  "type": "object"
}
```

### Metadata

```json
{
  "capabilityVariant": "default",
  "providerId": "gmail",
  "remoteDescription": "Creates a new draft email in the authenticated user's Gmail account.\n\nThis tool takes recipient addresses, a subject, and body content as inputs. It returns the ID of the created Gmail draft. If the draft is created as a reply to an existing message, the ID of the original message should be passed to the tool in the replyToMessageId field. Creating drafts with attachments is not supported yet.\n",
  "remoteInputSchema": {
    "$defs": {
      "Attachment": {
        "description": "Represents an attachment to be included in an email.",
        "properties": {
          "content": {
            "description": "Required. The base64-encoded content of the attachment.",
            "format": "byte",
            "type": "string"
          },
          "filename": {
            "description": "Optional. The name of the file to be attached, e.g. \"invoice.pdf\". For inline attachments, this is used for Content-ID generation. For regular attachments, filename is used to specify the filename to email clients. If not provided, the attachment may be received with no name.",
            "type": "string"
          },
          "id": {
            "description": "Optional. Output only. When present, contains the ID of an external attachment that can be retrieved in a separate `GetMessageAttachment` request.",
            "readOnly": true,
            "type": "string"
          },
          "inline": {
            "description": "Optional. If true, this attachment is handled as inline. An inline attachment is a content that is intended to be displayed within the body of an HTML email, as opposed to being listed as a separate file for download. If false or absent, defaults to false, and it's treated as a regular attachment.",
            "type": "boolean"
          },
          "mimeType": {
            "description": "Optional. The field representing a content or media type must use IANA MIME type, https://www.iana.org/assignments/media-types/media-types.xhtml. If not provided, defaults to \"application/octet-stream\".",
            "type": "string"
          }
        },
        "type": "object"
      }
    },
    "description": "Request message for CreateDraft RPC.",
    "properties": {
      "attachments": {
        "description": "Optional. The attachments to include in the email. The combined size of attachments in the message cannot exceed 25MB. If you need to send files larger than 25MB, upload the file to Drive first and then insert the Drive link into body or html_body.",
        "items": {
          "$ref": "#/$defs/Attachment"
        },
        "type": "array"
      },
      "bcc": {
        "description": "Optional. The blind carbon copy recipients of the email draft. Each string MUST be a valid plain email address (e.g., \"user@example.com\"). The \"Name \" format is NOT supported by this tool.",
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "body": {
        "description": "Optional. The main body content of the email draft. If html_body is also provided, this field is treated as the plain-text alternative.",
        "type": "string"
      },
      "cc": {
        "description": "Optional. The carbon copy recipients of the email draft. Each string MUST be a valid plain email address (e.g., \"user@example.com\"). The \"Name \" format is NOT supported by this tool.",
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "htmlBody": {
        "description": "The HTML content of the email draft. If provided, this will be used as the rich-text version of the email.",
        "type": "string"
      },
      "replyToMessageId": {
        "description": "Optional. The ID of the message to reply to. If provided, this will be used as the reply-to message ID for the email draft, and the `body` and `html_body` will be appended to the original message body.",
        "type": "string"
      },
      "subject": {
        "description": "Optional. The subject line of the email. Defaults to empty if not provided.",
        "type": "string"
      },
      "to": {
        "description": "Required. The primary recipients of the email draft. Each string MUST be a valid plain email address (e.g., \"user@example.com\"). The \"Name \" format is NOT supported by this tool.",
        "items": {
          "type": "string"
        },
        "type": "array"
      }
    },
    "type": "object"
  },
  "remoteTitle": null,
  "remoteToolName": "create_draft"
}
```

## `mcp.gmail.create_draft_with_attachments`

- Name: Gmail Create Draft With Attachments
- Family: `mcp`
- Provider: `gmail`
- Enabled: `yes`
- Permission scopes: `external_api.write`, `artifact.read`
- Policy class: `-`
- Side effects: `write`
- Timeout ms: `10000`
- Fallback strategy: `rest_api`

### Input Schema

```json
{
  "$defs": {
    "Attachment": {
      "description": "Represents an attachment to be included in an email.",
      "properties": {
        "content": {
          "description": "Required. The base64-encoded content of the attachment.",
          "format": "byte",
          "type": "string"
        },
        "filename": {
          "description": "Optional. The name of the file to be attached, e.g. \"invoice.pdf\". For inline attachments, this is used for Content-ID generation. For regular attachments, filename is used to specify the filename to email clients. If not provided, the attachment may be received with no name.",
          "type": "string"
        },
        "id": {
          "description": "Optional. Output only. When present, contains the ID of an external attachment that can be retrieved in a separate `GetMessageAttachment` request.",
          "readOnly": true,
          "type": "string"
        },
        "inline": {
          "description": "Optional. If true, this attachment is handled as inline. An inline attachment is a content that is intended to be displayed within the body of an HTML email, as opposed to being listed as a separate file for download. If false or absent, defaults to false, and it's treated as a regular attachment.",
          "type": "boolean"
        },
        "mimeType": {
          "description": "Optional. The field representing a content or media type must use IANA MIME type, https://www.iana.org/assignments/media-types/media-types.xhtml. If not provided, defaults to \"application/octet-stream\".",
          "type": "string"
        }
      },
      "type": "object"
    }
  },
  "description": "Request message for CreateDraft RPC.",
  "properties": {
    "attachments": {
      "description": "Optional. The attachments to include in the email. The combined size of attachments in the message cannot exceed 25MB. If you need to send files larger than 25MB, upload the file to Drive first and then insert the Drive link into body or html_body.",
      "items": {
        "$ref": "#/$defs/Attachment"
      },
      "type": "array"
    },
    "bcc": {
      "description": "Optional. The blind carbon copy recipients of the email draft. Each string MUST be a valid plain email address (e.g., \"user@example.com\"). The \"Name \" format is NOT supported by this tool.",
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "body": {
      "description": "Optional. The main body content of the email draft. If html_body is also provided, this field is treated as the plain-text alternative.",
      "type": "string"
    },
    "cc": {
      "description": "Optional. The carbon copy recipients of the email draft. Each string MUST be a valid plain email address (e.g., \"user@example.com\"). The \"Name \" format is NOT supported by this tool.",
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "htmlBody": {
      "description": "The HTML content of the email draft. If provided, this will be used as the rich-text version of the email.",
      "type": "string"
    },
    "replyToMessageId": {
      "description": "Optional. The ID of the message to reply to. If provided, this will be used as the reply-to message ID for the email draft, and the `body` and `html_body` will be appended to the original message body.",
      "type": "string"
    },
    "subject": {
      "description": "Optional. The subject line of the email. Defaults to empty if not provided.",
      "type": "string"
    },
    "to": {
      "description": "Required. The primary recipients of the email draft. Each string MUST be a valid plain email address (e.g., \"user@example.com\"). The \"Name \" format is NOT supported by this tool.",
      "items": {
        "type": "string"
      },
      "type": "array"
    }
  },
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "id": {
      "type": "string"
    },
    "status": {
      "type": "string"
    },
    "threadId": {
      "type": "string"
    }
  },
  "required": [
    "id",
    "status"
  ],
  "type": "object"
}
```

### Metadata

```json
{
  "capabilityVariant": "with_attachments",
  "providerId": "gmail",
  "remoteDescription": "Creates a new draft email in the authenticated user's Gmail account.\n\nThis tool takes recipient addresses, a subject, and body content as inputs. It returns the ID of the created Gmail draft. If the draft is created as a reply to an existing message, the ID of the original message should be passed to the tool in the replyToMessageId field. Creating drafts with attachments is not supported yet.\n",
  "remoteInputSchema": {
    "$defs": {
      "Attachment": {
        "description": "Represents an attachment to be included in an email.",
        "properties": {
          "content": {
            "description": "Required. The base64-encoded content of the attachment.",
            "format": "byte",
            "type": "string"
          },
          "filename": {
            "description": "Optional. The name of the file to be attached, e.g. \"invoice.pdf\". For inline attachments, this is used for Content-ID generation. For regular attachments, filename is used to specify the filename to email clients. If not provided, the attachment may be received with no name.",
            "type": "string"
          },
          "id": {
            "description": "Optional. Output only. When present, contains the ID of an external attachment that can be retrieved in a separate `GetMessageAttachment` request.",
            "readOnly": true,
            "type": "string"
          },
          "inline": {
            "description": "Optional. If true, this attachment is handled as inline. An inline attachment is a content that is intended to be displayed within the body of an HTML email, as opposed to being listed as a separate file for download. If false or absent, defaults to false, and it's treated as a regular attachment.",
            "type": "boolean"
          },
          "mimeType": {
            "description": "Optional. The field representing a content or media type must use IANA MIME type, https://www.iana.org/assignments/media-types/media-types.xhtml. If not provided, defaults to \"application/octet-stream\".",
            "type": "string"
          }
        },
        "type": "object"
      }
    },
    "description": "Request message for CreateDraft RPC.",
    "properties": {
      "attachments": {
        "description": "Optional. The attachments to include in the email. The combined size of attachments in the message cannot exceed 25MB. If you need to send files larger than 25MB, upload the file to Drive first and then insert the Drive link into body or html_body.",
        "items": {
          "$ref": "#/$defs/Attachment"
        },
        "type": "array"
      },
      "bcc": {
        "description": "Optional. The blind carbon copy recipients of the email draft. Each string MUST be a valid plain email address (e.g., \"user@example.com\"). The \"Name \" format is NOT supported by this tool.",
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "body": {
        "description": "Optional. The main body content of the email draft. If html_body is also provided, this field is treated as the plain-text alternative.",
        "type": "string"
      },
      "cc": {
        "description": "Optional. The carbon copy recipients of the email draft. Each string MUST be a valid plain email address (e.g., \"user@example.com\"). The \"Name \" format is NOT supported by this tool.",
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "htmlBody": {
        "description": "The HTML content of the email draft. If provided, this will be used as the rich-text version of the email.",
        "type": "string"
      },
      "replyToMessageId": {
        "description": "Optional. The ID of the message to reply to. If provided, this will be used as the reply-to message ID for the email draft, and the `body` and `html_body` will be appended to the original message body.",
        "type": "string"
      },
      "subject": {
        "description": "Optional. The subject line of the email. Defaults to empty if not provided.",
        "type": "string"
      },
      "to": {
        "description": "Required. The primary recipients of the email draft. Each string MUST be a valid plain email address (e.g., \"user@example.com\"). The \"Name \" format is NOT supported by this tool.",
        "items": {
          "type": "string"
        },
        "type": "array"
      }
    },
    "type": "object"
  },
  "remoteTitle": null,
  "remoteToolName": "create_draft"
}
```

## `mock_video_generation_tool`

- Name: Mock Video Generation Tool
- Family: `api`
- Provider: `api`
- Enabled: `yes`
- Permission scopes: `external_api.write`
- Policy class: `-`
- Side effects: `write`
- Timeout ms: `10`
- Fallback strategy: `-`

### Input Schema

```json
{
  "properties": {
    "context": {
      "_def": {
        "typeName": "ZodUnknown"
      },
      "_unknown": true,
      "~standard": {
        "vendor": "zod",
        "version": 1
      }
    },
    "duration": {
      "type": "number"
    },
    "prompt": {
      "type": "string"
    }
  },
  "required": [
    "prompt",
    "duration"
  ],
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "file_id": {
      "type": "string"
    },
    "summary": {
      "type": "string"
    },
    "title": {
      "type": "string"
    }
  },
  "required": [
    "title",
    "summary",
    "file_id"
  ],
  "type": "object"
}
```

## `patch_file`

- Name: Patch File
- Family: `local`
- Provider: `filesystem`
- Enabled: `yes`
- Permission scopes: `filesystem.patch`
- Policy class: `mutation`
- Side effects: `write`
- Timeout ms: `3000`
- Fallback strategy: `-`

### Input Schema

```json
{
  "properties": {
    "format": {
      "const": "unified_diff"
    },
    "patch": {
      "type": "string"
    },
    "path": {
      "type": "string"
    }
  },
  "required": [
    "path",
    "patch"
  ],
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "path": {
      "type": "string"
    },
    "summary": {
      "type": "string"
    },
    "updated": {
      "type": "boolean"
    }
  },
  "required": [
    "path",
    "updated",
    "summary"
  ],
  "type": "object"
}
```

### Metadata

```json
{
  "policyClass": "mutation",
  "safePhase": 2
}
```

## `rag_retrieval_tool`

- Name: RAG Retrieval Tool
- Family: `rag_adapter`
- Provider: `rag_subsystem`
- Enabled: `yes`
- Permission scopes: `rag.read`
- Policy class: `-`
- Side effects: `read_only`
- Timeout ms: `1000`
- Fallback strategy: `-`

### Input Schema

```json
{
  "properties": {
    "operation": {
      "type": "string"
    },
    "query": {
      "type": "string"
    },
    "topK": {
      "type": "number"
    }
  },
  "required": [
    "query"
  ],
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "items": {
      "items": {
        "properties": {
          "content": {
            "type": "string"
          },
          "metadata": {
            "_def": {
              "keyType": {
                "_def": {
                  "checks": [],
                  "coerce": false,
                  "typeName": "ZodString"
                },
                "~standard": {
                  "vendor": "zod",
                  "version": 1
                }
              },
              "typeName": "ZodRecord",
              "valueType": {
                "_def": {
                  "typeName": "ZodUnknown"
                },
                "_unknown": true,
                "~standard": {
                  "vendor": "zod",
                  "version": 1
                }
              }
            },
            "~standard": {
              "vendor": "zod",
              "version": 1
            }
          },
          "title": {
            "type": "string"
          }
        },
        "required": [
          "title",
          "content",
          "metadata"
        ],
        "type": "object"
      },
      "type": "array"
    }
  },
  "required": [
    "items"
  ],
  "type": "object"
}
```

## `read_file`

- Name: Read File
- Family: `local`
- Provider: `filesystem`
- Enabled: `yes`
- Permission scopes: `filesystem.read`
- Policy class: `safe_read`
- Side effects: `read_only`
- Timeout ms: `2000`
- Fallback strategy: `-`

### Input Schema

```json
{
  "properties": {
    "encoding": {
      "type": "string"
    },
    "max_bytes": {
      "type": "number"
    },
    "path": {
      "type": "string"
    }
  },
  "required": [
    "path"
  ],
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "content": {
      "type": "string"
    },
    "path": {
      "type": "string"
    },
    "size_bytes": {
      "type": "number"
    },
    "truncated": {
      "type": "boolean"
    }
  },
  "required": [
    "path",
    "content",
    "truncated",
    "size_bytes"
  ],
  "type": "object"
}
```

### Metadata

```json
{
  "policyClass": "safe_read",
  "safePhase": 1
}
```

## `research_paper_search_tool`

- Name: Research Paper Search Tool
- Family: `api`
- Provider: `research_paper`
- Enabled: `yes`
- Permission scopes: `external_api.read`
- Policy class: `-`
- Side effects: `read_only`
- Timeout ms: `20000`
- Fallback strategy: `-`

### Input Schema

```json
{
  "properties": {
    "limit": {
      "type": "number"
    },
    "source": {
      "enum": [
        "auto",
        "arxiv",
        "semantic-scholar"
      ],
      "type": "string"
    },
    "topic": {
      "type": "string"
    }
  },
  "required": [
    "topic"
  ],
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "papers": {
      "items": {
        "properties": {
          "authors": {
            "items": {
              "type": "string"
            },
            "type": "array"
          },
          "link": {
            "type": "string"
          },
          "summary": {
            "type": "string"
          },
          "title": {
            "type": "string"
          },
          "why_it_matters": {
            "type": "string"
          },
          "year": {
            "type": "number"
          }
        },
        "required": [
          "title",
          "link",
          "year",
          "authors",
          "summary",
          "why_it_matters"
        ],
        "type": "object"
      },
      "type": "array"
    },
    "source": {
      "type": "string"
    },
    "topic": {
      "type": "string"
    }
  },
  "required": [
    "topic",
    "source",
    "papers"
  ],
  "type": "object"
}
```

## `retrieve_documents`

- Name: Retrieve Documents
- Family: `rag_adapter`
- Provider: `rag_subsystem`
- Enabled: `yes`
- Permission scopes: `rag.read`
- Policy class: `safe_read`
- Side effects: `read_only`
- Timeout ms: `2000`
- Fallback strategy: `-`

### Input Schema

```json
{
  "properties": {
    "filters": {
      "_def": {
        "keyType": {
          "_def": {
            "checks": [],
            "coerce": false,
            "typeName": "ZodString"
          },
          "~standard": {
            "vendor": "zod",
            "version": 1
          }
        },
        "typeName": "ZodRecord",
        "valueType": {
          "_def": {
            "typeName": "ZodUnknown"
          },
          "_unknown": true,
          "~standard": {
            "vendor": "zod",
            "version": 1
          }
        }
      },
      "~standard": {
        "vendor": "zod",
        "version": 1
      }
    },
    "query": {
      "type": "string"
    },
    "top_k": {
      "type": "number"
    }
  },
  "required": [
    "query"
  ],
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "items": {
      "items": {
        "properties": {
          "content": {
            "type": "string"
          },
          "metadata": {
            "_def": {
              "keyType": {
                "_def": {
                  "checks": [],
                  "coerce": false,
                  "typeName": "ZodString"
                },
                "~standard": {
                  "vendor": "zod",
                  "version": 1
                }
              },
              "typeName": "ZodRecord",
              "valueType": {
                "_def": {
                  "typeName": "ZodUnknown"
                },
                "_unknown": true,
                "~standard": {
                  "vendor": "zod",
                  "version": 1
                }
              }
            },
            "~standard": {
              "vendor": "zod",
              "version": 1
            }
          },
          "title": {
            "type": "string"
          }
        },
        "required": [
          "title",
          "content",
          "metadata"
        ],
        "type": "object"
      },
      "type": "array"
    }
  },
  "required": [
    "items"
  ],
  "type": "object"
}
```

### Metadata

```json
{
  "policyClass": "safe_read",
  "safePhase": 1
}
```

## `save_artifact`

- Name: Save Artifact
- Family: `local`
- Provider: `artifact_store`
- Enabled: `yes`
- Permission scopes: `artifact.write`
- Policy class: `artifact_safe`
- Side effects: `read_only`
- Timeout ms: `2000`
- Fallback strategy: `-`

### Input Schema

```json
{
  "properties": {
    "artifact_type": {
      "type": "string"
    },
    "content": {
      "_def": {
        "typeName": "ZodUnknown"
      },
      "_unknown": true,
      "~standard": {
        "vendor": "zod",
        "version": 1
      }
    },
    "content_hash": {
      "type": "string"
    },
    "display_name": {
      "type": "string"
    },
    "format": {
      "type": "string"
    },
    "name": {
      "type": "string"
    },
    "review_source": {
      "type": "string"
    },
    "reviewed": {
      "type": "boolean"
    },
    "reviewed_at": {
      "type": "string"
    },
    "reviewed_by": {
      "type": "string"
    },
    "source_message_ids": {
      "items": {
        "type": "string"
      },
      "type": "array"
    }
  },
  "required": [
    "artifact_type",
    "name",
    "content"
  ],
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "app_id": {
      "type": "string"
    },
    "artifact_id": {
      "type": "string"
    },
    "artifact_type": {
      "type": "string"
    },
    "content_hash": {
      "type": "string"
    },
    "created_at": {
      "type": "string"
    },
    "created_by_execution_id": {
      "type": "string"
    },
    "created_by_turn_id": {
      "type": "string"
    },
    "display_name": {
      "type": "string"
    },
    "file_path": {
      "type": "string"
    },
    "mime_type": {
      "type": "string"
    },
    "path": {
      "type": "string"
    },
    "provider_origin": {
      "const": "local"
    },
    "review_source": {
      "type": "string"
    },
    "reviewed": {
      "type": "boolean"
    },
    "reviewed_at": {
      "type": "string"
    },
    "reviewed_by": {
      "type": "string"
    },
    "size_bytes": {
      "type": "number"
    },
    "source_message_ids": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "source_skill_id": {
      "type": "string"
    },
    "source_tool_id": {
      "type": "string"
    },
    "status": {
      "const": "ready"
    },
    "storage_file_name": {
      "type": "string"
    },
    "summary": {
      "type": "string"
    }
  },
  "required": [
    "artifact_id",
    "path",
    "artifact_type",
    "display_name",
    "app_id",
    "created_at",
    "provider_origin",
    "status"
  ],
  "type": "object"
}
```

### Metadata

```json
{
  "policyClass": "artifact_safe",
  "safePhase": 1
}
```

## `search_metadata`

- Name: Search Metadata
- Family: `rag_adapter`
- Provider: `rag_subsystem`
- Enabled: `yes`
- Permission scopes: `metadata.read`
- Policy class: `safe_read`
- Side effects: `read_only`
- Timeout ms: `2000`
- Fallback strategy: `-`

### Input Schema

```json
{
  "properties": {
    "filters": {
      "_def": {
        "keyType": {
          "_def": {
            "checks": [],
            "coerce": false,
            "typeName": "ZodString"
          },
          "~standard": {
            "vendor": "zod",
            "version": 1
          }
        },
        "typeName": "ZodRecord",
        "valueType": {
          "_def": {
            "typeName": "ZodUnknown"
          },
          "_unknown": true,
          "~standard": {
            "vendor": "zod",
            "version": 1
          }
        }
      },
      "~standard": {
        "vendor": "zod",
        "version": 1
      }
    },
    "limit": {
      "type": "number"
    },
    "query": {
      "type": "string"
    }
  },
  "required": [
    "query"
  ],
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "items": {
      "items": {
        "properties": {
          "document_id": {
            "type": "string"
          },
          "tags": {
            "items": {
              "type": "string"
            },
            "type": "array"
          },
          "title": {
            "type": "string"
          }
        },
        "required": [
          "document_id",
          "title",
          "tags"
        ],
        "type": "object"
      },
      "type": "array"
    }
  },
  "required": [
    "items"
  ],
  "type": "object"
}
```

### Metadata

```json
{
  "policyClass": "safe_read",
  "safePhase": 1
}
```

## `site_build_adapter`

- Name: Site Build Adapter
- Family: `adapter`
- Provider: `custom_adapter`
- Enabled: `yes`
- Permission scopes: `adapter.execute`
- Policy class: `review_required`
- Side effects: `write`
- Timeout ms: `5000`
- Fallback strategy: `-`

### Input Schema

```json
{
  "properties": {
    "path": {
      "type": "string"
    }
  },
  "required": [
    "path"
  ],
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "output": {
      "type": "string"
    }
  },
  "required": [
    "output"
  ],
  "type": "object"
}
```

### Metadata

```json
{
  "policyClass": "review_required",
  "safePhase": 3
}
```

## `write_file`

- Name: Write File
- Family: `local`
- Provider: `filesystem`
- Enabled: `yes`
- Permission scopes: `filesystem.write`
- Policy class: `mutation`
- Side effects: `write`
- Timeout ms: `3000`
- Fallback strategy: `-`

### Input Schema

```json
{
  "properties": {
    "content": {
      "type": "string"
    },
    "encoding": {
      "type": "string"
    },
    "if_exists": {
      "const": "overwrite"
    },
    "path": {
      "type": "string"
    }
  },
  "required": [
    "path",
    "content"
  ],
  "type": "object"
}
```

### Output Schema

```json
{
  "properties": {
    "bytes_written": {
      "type": "number"
    },
    "path": {
      "type": "string"
    },
    "updated": {
      "type": "boolean"
    }
  },
  "required": [
    "path",
    "bytes_written",
    "updated"
  ],
  "type": "object"
}
```

### Metadata

```json
{
  "policyClass": "mutation",
  "safePhase": 2
}
```
