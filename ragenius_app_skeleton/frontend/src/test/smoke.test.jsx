import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

describe("frontend test harness", () => {
  it("renders a React element into the jsdom document", () => {
    render(<div>Frontend smoke test</div>);

    expect(screen.getByText("Frontend smoke test")).toBeInTheDocument();
  });
});
