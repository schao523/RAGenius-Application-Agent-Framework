import { AppError } from "../../errors/app-error.js";
import type { ToolDefinition } from "../tool.types.js";

export interface RagAdapterProvider {
  providerType: "rag_adapter";
  execute(
    tool: ToolDefinition,
    input: Record<string, unknown>,
    options?: {
      appId: string;
      sessionId?: string;
      confirmed?: boolean;
      executionId?: string | null;
      skillId?: string;
    }
  ): Promise<Record<string, unknown>>;
}

export class MockRagAdapterProvider implements RagAdapterProvider {
  readonly providerType = "rag_adapter";

  async execute(
    tool: ToolDefinition,
    input: Record<string, unknown>,
    _options?: {
      appId: string;
      sessionId?: string;
      confirmed?: boolean;
      executionId?: string | null;
      skillId?: string;
    }
  ): Promise<Record<string, unknown>> {
    if (tool.id === "search_metadata") {
      return {
        items: [
          {
            document_id: "doc-metadata-1",
            title: `Metadata result for ${String(input.query)}`,
            tags: []
          }
        ]
      };
    }

    if (tool.id !== "rag_retrieval_tool" && tool.id !== "retrieve_documents") {
      throw new AppError({
        code: "RAG_TOOL_NOT_IMPLEMENTED",
        message: "The requested RAG adapter tool is not implemented.",
        errorClass: "tool",
        httpStatus: 502,
        details: { tool_id: tool.id },
        recoverable: false,
        suggestedAction:
          "Use rag_retrieval_tool or retrieve_documents for MVP retrieval."
      });
    }

    if ("operation" in input && input.operation !== "retrieve") {
      throw new AppError({
        code: "RAG_MUTATION_FORBIDDEN",
        message: "RAG adapter tools are read-only.",
        errorClass: "permission",
        httpStatus: 403,
        details: { operation: input.operation },
        recoverable: false,
        suggestedAction: "Use retrieval-only RAG access."
      });
    }

    return {
      items: [
        {
          title: "RAG Overview",
          content: `Context for query: ${String(input.query)}`,
          metadata: {
            topK: input.top_k ?? input.topK ?? 3
          }
        }
      ]
    };
  }
}
