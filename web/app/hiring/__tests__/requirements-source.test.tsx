// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { SourceLine } from "../requirements";

afterEach(cleanup);

describe("who proposed the requirements", () => {
  it("names the local model and that nothing applies until a person approves", () => {
    render(<SourceLine source={{ model: "ollama:qwen2.5:3b-instruct", prompt_version: "requirements-llm-v1", fallback: false }} />);
    expect(screen.getByText(/Proposed by local AI model \(qwen2\.5:3b-instruct\), from the job description only/)).toBeTruthy();
    expect(screen.getByText(/the pool stays provisional, and nothing can be shortlisted or shared, until a person approves them/)).toBeTruthy();
  });
  it("says so when the model was not used, and never claims the AI proposed them", () => {
    render(<SourceLine source={{ model: "deterministic-requirement-parser", prompt_version: "requirements-v1", fallback: true }} />);
    expect(screen.getByRole("status").textContent).toMatch(/AI model was unavailable, so the automatic text reader proposed these/);
    expect(screen.queryByText(/local AI model/)).toBeNull();
  });
  it("says why the model did not answer when the description was too long", () => {
    render(<SourceLine source={{ model: "deterministic-requirement-parser", prompt_version: "requirements-v1", fallback: true, fallback_reason: "description_too_long" }} />);
    expect(screen.getByRole("status").textContent).toMatch(/longer than the AI model reads, so the automatic text reader proposed these\. Review them before approving/);
    expect(screen.queryByText(/was unavailable/)).toBeNull();
  });
  it("names the text reader when it is the configured reader", () => {
    render(<SourceLine source={{ model: "deterministic-requirement-parser", prompt_version: "requirements-v1", fallback: false }} />);
    expect(screen.getByText(/Proposed by the automatic text reader/)).toBeTruthy();
  });
  it("shows nothing before extraction has run", () => {
    const { container } = render(<SourceLine source={null} />);
    expect(container.textContent).toBe("");
  });
  it("says nothing was proposed when the fallback reader found nothing", () => {
    render(<SourceLine source={{ model: "deterministic-requirement-parser", prompt_version: "requirements-v1", fallback: true }} proposed={0} />);
    const line = screen.getByRole("status").textContent ?? "";
    expect(line).toMatch(/proposed nothing/);
    expect(line).not.toMatch(/proposed these/);
  });
});
