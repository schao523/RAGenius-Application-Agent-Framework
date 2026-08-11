import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ArtifactUploadControl from "./ArtifactUploadControl";

describe("ArtifactUploadControl", () => {
  it("uploads once, shows phases, and returns the ready artifact", async () => {
    const onReady = vi.fn();
    const onUpload = vi.fn().mockImplementation(async (_file, _operationId, onProgress) => {
      onProgress({ percent: 50 });
      return { status: "ready", artifact: { artifact_id: "artifact-1", display_name: "notes.txt" } };
    });
    render(<ArtifactUploadControl onUpload={onUpload} onReady={onReady} />);

    const file = new File(["notes"], "notes.txt", { type: "text/plain" });
    await act(async () => fireEvent.change(screen.getByLabelText("Upload artifact"), {
      target: { files: [file] },
    }));

    expect(onUpload).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Ready")).toBeInTheDocument();
    expect(onReady).toHaveBeenCalledWith(expect.objectContaining({ artifact_id: "artifact-1" }));
  });

  it("shows a safe retry action without rendering raw response JSON", async () => {
    const onUpload = vi.fn()
      .mockRejectedValueOnce(new Error('{"detail":{"token":"secret"}}'))
      .mockResolvedValueOnce({ status: "ready", artifact: { artifact_id: "artifact-1" } });
    render(<ArtifactUploadControl onUpload={onUpload} onReady={vi.fn()} />);

    const file = new File(["notes"], "notes.txt", { type: "text/plain" });
    await act(async () => fireEvent.change(screen.getByLabelText("Upload artifact"), {
      target: { files: [file] },
    }));
    expect(await screen.findByText("Upload failed. Retry this file.")).toBeInTheDocument();
    expect(screen.queryByText(/secret/)).toBeNull();

    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Retry upload" })));
    await waitFor(() => expect(onUpload).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("Ready")).toBeInTheDocument();
  });

  it("cancels an active transfer and clears the local file", async () => {
    const onUpload = vi.fn((_file, _operationId, _onProgress, signal) => (
      new Promise((_resolve, reject) => signal.addEventListener("abort", () => reject(
        Object.assign(new Error("cancelled"), { name: "AbortError" }),
      )))
    ));
    render(<ArtifactUploadControl onUpload={onUpload} />);
    const file = new File(["notes"], "notes.txt", { type: "text/plain" });
    fireEvent.change(screen.getByLabelText("Upload artifact"), { target: { files: [file] } });

    fireEvent.click(await screen.findByRole("button", { name: "Cancel upload" }));

    await waitFor(() => expect(screen.queryByText(/notes\.txt/)).toBeNull());
    expect(screen.getByText("Upload cancelled.")).toBeInTheDocument();
  });
});
