import { AppError } from "../../errors/app-error.js";

export interface McpHttpConnectionConfig {
  authToken?: string;
  baseUrl: string;
}

export interface McpRemoteTool {
  name: string;
  title?: string;
  description?: string;
  inputSchema?: Record<string, unknown>;
}

interface JsonRpcSuccess<T> {
  id?: string | number | null;
  jsonrpc: "2.0";
  result: T;
}

interface JsonRpcFailure {
  error: {
    code: number;
    message: string;
    data?: unknown;
  };
  id?: string | number | null;
  jsonrpc: "2.0";
}

type JsonRpcResponse<T> = JsonRpcSuccess<T> | JsonRpcFailure;

interface InitializeResult {
  capabilities?: Record<string, unknown>;
  protocolVersion?: string;
  serverInfo?: Record<string, unknown>;
}

interface ListToolsResult {
  tools?: McpRemoteTool[];
}

interface CallToolResult {
  content?: Array<Record<string, unknown>>;
  isError?: boolean;
  structuredContent?: Record<string, unknown>;
}

const MCP_PROTOCOL_VERSION = "2025-06-18";

function isJsonRpcFailure<T>(
  response: JsonRpcResponse<T>
): response is JsonRpcFailure {
  return "error" in response;
}

export class McpHttpClient {
  private nextRequestId = 1;
  private sessionId: string | undefined;

  constructor(private readonly config: McpHttpConnectionConfig) {}

  async initialize(): Promise<InitializeResult> {
    const result = await this.request<InitializeResult>("initialize", {
      capabilities: {},
      clientInfo: {
        name: "ragenius_execution_subsystem",
        version: "0.1.0"
      },
      protocolVersion: MCP_PROTOCOL_VERSION
    });

    await this.notify("notifications/initialized", {});
    return result;
  }

  async listTools(): Promise<McpRemoteTool[]> {
    const result = await this.request<ListToolsResult>("tools/list", {});
    return Array.isArray(result.tools) ? result.tools : [];
  }

  async callTool(
    name: string,
    args: Record<string, unknown>
  ): Promise<Record<string, unknown>> {
    const result = await this.request<CallToolResult>("tools/call", {
      arguments: args,
      name
    });

    if (result.isError) {
      throw new AppError({
        code: "MCP_TOOL_CALL_FAILED",
        message: "The remote MCP tool returned an error.",
        errorClass: "tool",
        httpStatus: 502,
        details: { tool_name: name, result: result.content ?? result.structuredContent },
        recoverable: true,
        suggestedAction: "Inspect the remote MCP tool response and retry later."
      });
    }

    if (
      result.structuredContent &&
      typeof result.structuredContent === "object" &&
      !Array.isArray(result.structuredContent)
    ) {
      return result.structuredContent;
    }

    if (Array.isArray(result.content)) {
      return { content: result.content };
    }

    return {};
  }

  private async notify(
    method: string,
    params: Record<string, unknown>
  ): Promise<void> {
    await this.post(method, {
      jsonrpc: "2.0",
      method,
      params
    });
  }

  private async request<T>(
    method: string,
    params: Record<string, unknown>
  ): Promise<T> {
    const response = await this.post(method, {
      id: this.nextRequestId++,
      jsonrpc: "2.0",
      method,
      params
    });
    const payload = (await response.json()) as JsonRpcResponse<T>;

    if (isJsonRpcFailure(payload)) {
      throw new AppError({
        code: "MCP_TOOL_CALL_FAILED",
        message: "The remote MCP server returned a protocol error.",
        errorClass: "tool",
        httpStatus: 502,
        details: {
          method,
          mcp_error_code: payload.error.code,
          mcp_error_message: payload.error.message
        },
        recoverable: true,
        suggestedAction: "Inspect the remote MCP server response and retry later."
      });
    }

    return payload.result;
  }

  private async post(
    method: string,
    payload: Record<string, unknown>
  ): Promise<Response> {
    const headers = new Headers({
      Accept: "application/json, text/event-stream",
      "Content-Type": "application/json",
      "Mcp-Method": method,
      "Mcp-Protocol-Version": MCP_PROTOCOL_VERSION
    });

    if (this.config.authToken) {
      headers.set("Authorization", `Bearer ${this.config.authToken}`);
    }

    if (this.sessionId) {
      headers.set("Mcp-Session-Id", this.sessionId);
    }

    let response: Response;
    try {
      response = await fetch(this.config.baseUrl, {
        body: JSON.stringify(payload),
        headers,
        method: "POST"
      });
    } catch (error) {
      throw new AppError({
        code: "MCP_TRANSPORT_FAILED",
        message: "The remote MCP provider could not be reached.",
        errorClass: "tool",
        httpStatus: 502,
        details: { base_url: this.config.baseUrl },
        recoverable: true,
        suggestedAction: "Verify the MCP endpoint and network connectivity."
      });
    }

    const sessionId = response.headers.get("Mcp-Session-Id");
    if (sessionId) {
      this.sessionId = sessionId;
    }

    if (response.status === 401 || response.status === 403) {
      const responseBody = await response.text().catch(() => "");
      throw new AppError({
        code: "MCP_PROVIDER_AUTH_FAILED",
        message: "The remote MCP provider rejected authentication.",
        errorClass: "tool",
        httpStatus: 502,
        details: {
          base_url: this.config.baseUrl,
          status: response.status,
          response_body: responseBody
        },
        recoverable: false,
        suggestedAction: "Refresh the shared OAuth token and retry."
      });
    }

    if (!response.ok) {
      const responseBody = await response.text().catch(() => "");
      throw new AppError({
        code: "MCP_TRANSPORT_FAILED",
        message: "The remote MCP provider returned an HTTP error.",
        errorClass: "tool",
        httpStatus: 502,
        details: {
          base_url: this.config.baseUrl,
          status: response.status,
          response_body: responseBody
        },
        recoverable: true,
        suggestedAction: "Inspect the MCP endpoint and retry later."
      });
    }

    return response;
  }
}
