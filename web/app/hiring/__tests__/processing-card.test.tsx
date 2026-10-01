// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ProcessingCard } from "../processing-card";

describe("ProcessingCard", () => {
  it("shows the finished checklist and the pool summary", () => {
    render(<ProcessingCard processing={{ stage: "complete", matched_count: 23, requested_count: 5 }} status="open" onRetry={vi.fn()} />);
    expect(screen.getByText(/Requirements extracted/)).toBeTruthy();
    expect(screen.getByText(/Candidate matching completed/)).toBeTruthy();
    expect(screen.getByText(/23 candidates matched/)).toBeTruthy();
    expect(screen.getByText(/Requested: 5/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /run matching/i })).toBeNull();
  });
  it("shows progress while matching", () => {
    render(<ProcessingCard processing={{ stage: "matching", matched_count: 0, requested_count: 5 }} status="open" onRetry={vi.fn()} />);
    expect(screen.getByText(/Matching candidates/)).toBeTruthy();
  });
  it("offers a retry when processing failed", () => {
    const retry = vi.fn();
    render(<ProcessingCard processing={{ stage: "failed", matched_count: 0, requested_count: null }} status="open" onRetry={retry} />);
    screen.getByRole("button", { name: /retry/i }).click();
    expect(retry).toHaveBeenCalled();
  });
});
