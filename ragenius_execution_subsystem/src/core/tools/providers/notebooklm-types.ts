export type NotebookLmOperation =
  | "list_notebooks"
  | "get_notebook"
  | "list_sources"
  | "ask"
  | "poll_artifact_task"
  | "add_source_text"
  | "add_source_file"
  | "add_source_url"
  | "generate_slide_deck"
  | "generate_report"
  | "generate_video";

export interface NotebookLmBridgeRequest {
  operation: NotebookLmOperation;
  arguments: Record<string, unknown>;
}

export interface NotebookLmBridgeSuccessResponse {
  ok: true;
  result: Record<string, unknown>;
}

export interface NotebookLmBridgeErrorPayload {
  code: string;
  message: string;
  details?: unknown;
  recoverable: boolean;
  suggested_action: string;
}

export interface NotebookLmBridgeErrorResponse {
  ok: false;
  error: NotebookLmBridgeErrorPayload;
}

export type NotebookLmBridgeResponse =
  | NotebookLmBridgeSuccessResponse
  | NotebookLmBridgeErrorResponse;
