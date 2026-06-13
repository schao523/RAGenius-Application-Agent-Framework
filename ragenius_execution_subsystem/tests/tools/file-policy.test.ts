import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { AppError } from "../../src/core/errors/app-error.js";
import { FilePolicy } from "../../src/core/tools/providers/file-policy.js";

describe("file policy", () => {
  it("rejects reads outside configured allowed roots", () => {
    const policy = new FilePolicy({
      allowedRoots: ["D:/GitHub/Codex-RAGenius-System/docs"],
      maxReadBytes: 4096
    });

    assert.throws(
      () => policy.resolveReadablePath("C:/Windows/System32/drivers/etc/hosts"),
      (error: unknown) =>
        error instanceof AppError &&
        error.code === "FILESYSTEM_PATH_NOT_ALLOWED"
    );
  });

  it("rejects writes outside configured mutation roots", () => {
    const policy = new FilePolicy({
      allowedRoots: ["D:/GitHub/Codex-RAGenius-System"],
      mutationRoots: ["D:/GitHub/Codex-RAGenius-System/docs"],
      maxReadBytes: 4096,
      maxWriteBytes: 8192,
      maxPatchBytes: 8192
    });

    assert.throws(
      () =>
        (policy as FilePolicy & { resolveWritablePath: (p: string) => string }).resolveWritablePath(
          "D:/GitHub/Codex-RAGenius-System/README.md"
        ),
      (error: unknown) =>
        error instanceof AppError &&
        error.code === "FILESYSTEM_PATH_NOT_ALLOWED"
    );
  });
});
