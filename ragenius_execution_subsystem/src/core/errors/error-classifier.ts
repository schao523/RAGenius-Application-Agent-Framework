import { ZodError } from "zod";

import { AppError } from "./app-error.js";

export function toAppError(error: unknown): AppError {
  if (error instanceof AppError) {
    return error;
  }

  if (error instanceof ZodError) {
    const issue = error.issues[0];
    return new AppError({
      code: "VALIDATION_ERROR",
      message: "Invalid execution request.",
      errorClass: "validation",
      httpStatus: 400,
      details: issue
        ? {
            path: issue.path.join("."),
            issue: issue.message
          }
        : undefined,
      recoverable: true,
      suggestedAction: "Provide a valid execution request payload."
    });
  }

  if (error instanceof Error) {
    return new AppError({
      code: "INTERNAL_ERROR",
      message: "An unexpected error occurred.",
      errorClass: "workflow",
      httpStatus: 500,
      details: undefined,
      recoverable: false,
      suggestedAction: "Retry later or inspect server logs."
    });
  }

  return new AppError({
    code: "UNKNOWN_ERROR",
    message: "An unknown error occurred.",
    errorClass: "workflow",
    httpStatus: 500,
    details: undefined,
    recoverable: false,
    suggestedAction: "Retry later or inspect server logs."
  });
}
