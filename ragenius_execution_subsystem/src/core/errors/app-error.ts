import type { ErrorClass, NormalizedError } from "../../api/schemas/common-response.schema.js";

export interface AppErrorOptions {
  code: string;
  message: string;
  errorClass: ErrorClass;
  httpStatus: number;
  details?: unknown;
  recoverable: boolean;
  suggestedAction: string;
}

export class AppError extends Error {
  readonly code: string;
  readonly errorClass: ErrorClass;
  readonly httpStatus: number;
  readonly details?: unknown;
  readonly recoverable: boolean;
  readonly suggestedAction: string;

  constructor(options: AppErrorOptions) {
    super(options.message);
    this.name = "AppError";
    this.code = options.code;
    this.errorClass = options.errorClass;
    this.httpStatus = options.httpStatus;
    this.details = options.details;
    this.recoverable = options.recoverable;
    this.suggestedAction = options.suggestedAction;
  }

  toNormalizedError(): NormalizedError {
    return {
      code: this.code,
      message: this.message,
      details: this.details,
      recoverable: this.recoverable,
      suggested_action: this.suggestedAction
    };
  }
}
