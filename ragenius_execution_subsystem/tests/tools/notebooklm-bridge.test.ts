import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { describe, it } from "node:test";

import { resolveNotebookLmBridgeScript } from "../../src/core/tools/providers/notebooklm-bridge.js";

describe("notebooklm bridge path resolution", () => {
  it("resolves the default bridge script to an existing file", () => {
    const resolved = resolveNotebookLmBridgeScript("scripts/notebooklm_bridge.py");

    assert.equal(path.isAbsolute(resolved), true);
    assert.equal(fs.existsSync(resolved), true);
    assert.equal(path.basename(resolved), "notebooklm_bridge.py");
  });
});
