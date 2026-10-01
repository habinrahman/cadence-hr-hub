// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, ConnectionError } from "@/lib/errors";
import type { DemoStatus } from "@/lib/api";

const api = vi.hoisted(() => ({
  checkApiReachable: vi.fn(),
  getDemoStatus: vi.fn(),
  resetDemoData: vi.fn(),
  uploadDocument: vi.fn(),
}));
vi.mock("@/lib/api", () => api);
vi.mock("next/link", () => ({ default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a> }));

import { DemoData, formatElapsed } from "../demo-data";
import { RESET_PHRASE, ResetPanel, phraseMatches } from "../reset-panel";

const status = (over: Partial<DemoStatus> = {}): DemoStatus => ({
  documents: 0,
  documents_by_status: {},
  identity_outcomes: {},
  candidates: 0,
  pending_reviews: 0,
  needs_ocr: 0,
  quarantined: 0,
  failed: 0,
  processing: 0,
  open_jobs: 0,
  hiring_requests: 0,
  matches: 0,
  shortlisted: 0,
  shares: 0,
  last_reset_at: null,
  quarantine_records: 0,
  ...over,
});

beforeEach(() => {
  api.checkApiReachable.mockReset();
  api.checkApiReachable.mockResolvedValue(undefined);
  api.getDemoStatus.mockReset();
  api.resetDemoData.mockReset();
  api.uploadDocument.mockReset();
});
afterEach(cleanup);

describe("Set up Candidate Repository page", () => {
  it("shows the counts the system reports and nothing hard-coded", async () => {
    api.getDemoStatus.mockResolvedValue(
      status({
        documents: 137,
        candidates: 91,
        pending_reviews: 13,
        needs_ocr: 4,
        quarantined: 2,
        failed: 1,
        identity_outcomes: { new: 91, duplicate: 6 },
      }),
    );
    render(<DemoData />);
    expect((await screen.findAllByText("137")).length).toBe(2);
    for (const n of ["91", "13", "4", "2", "1"]) expect(screen.getAllByText(n).length).toBeGreaterThan(0);
    expect(screen.getByText("New candidate")).toBeTruthy();
    expect(screen.getByText("Duplicate")).toBeTruthy();
    expect(screen.queryByText("488")).toBeNull();
    expect(screen.getByText("No files selected")).toBeTruthy();
  });

  it("shows the empty workspace after a reset", async () => {
    api.getDemoStatus.mockResolvedValue(status({ last_reset_at: "2026-09-30T11:00:00Z" }));
    render(<DemoData />);
    await screen.findByText(/Last reset:/);
    expect(screen.getAllByText("0").length).toBeGreaterThanOrEqual(6);
    expect(screen.getAllByText(/Candidate Repository/).length).toBeGreaterThan(1);
  });

  it("says plainly when the demo tools are not available", async () => {
    api.getDemoStatus.mockRejectedValue(new ApiError(404, "Not Found"));
    render(<DemoData />);
    await screen.findByText(/ENVIRONMENT=local/);
  });

  it("uploads the chosen files, ignores system files, reports failures and then finishes", async () => {
    let current = status();
    api.getDemoStatus.mockImplementation(async () => current);
    api.uploadDocument.mockImplementation(async (f: File) => {
      if (f.name === "bad.txt") throw new ApiError(415, "unsupported_file");
      return { id: f.name, status: "received", created: true };
    });
    render(<DemoData />);
    await screen.findByText("No files selected");
    const input = screen.getByLabelText("Choose CV files") as HTMLInputElement;
    const chosen = [new File(["a"], "a.pdf"), new File(["b"], "b.pdf"), new File(["c"], "bad.txt"), new File(["d"], ".DS_Store")];
    fireEvent.change(input, { target: { files: chosen } });
    await screen.findByText(/3 CVs selected/);
    expect(screen.getByText(/1 system file ignored/)).toBeTruthy();
    current = status({ documents: 2, candidates: 2, documents_by_status: { profiled: 2 } });
    fireEvent.click(screen.getByRole("button", { name: /Import CVs/ }));
    await screen.findByText(/1 file did not upload/);
    expect(screen.getByText(/bad\.txt/)).toBeTruthy();
    expect(screen.getAllByText(/File type not supported/).length).toBeGreaterThan(0);
    expect(api.uploadDocument).toHaveBeenCalledTimes(3);
    // One file was rejected, so the upload is finished but must not claim a clean "Import complete".
    await waitFor(() => expect(screen.getByText(/Finished with 1 file not uploaded/)).toBeTruthy(), { timeout: 4000 });
    expect(screen.queryByText("Import complete")).toBeNull();
  });

  const chooseFiles = async (names: string[]) => {
    await screen.findByText("No files selected");
    const input = screen.getByLabelText("Choose CV files") as HTMLInputElement;
    fireEvent.change(input, { target: { files: names.map((n) => new File(["x"], n)) } });
    await screen.findByText(new RegExp(`${names.length} CVs? selected`));
  };

  it("never says ingestion is complete when the API cannot be reached and every upload fails", async () => {
    // The workspace already holds 472 documents, as in the reported judging-day screen.
    api.getDemoStatus.mockResolvedValue(status({ documents: 472, candidates: 409, pending_reviews: 56, documents_by_status: { profiled: 472 } }));
    api.uploadDocument.mockRejectedValue(new ConnectionError("http://localhost:8000"));
    render(<DemoData />);
    await chooseFiles(["a.pdf", "b.pdf", "c.pdf"]);
    fireEvent.click(screen.getByRole("button", { name: /Import CVs/ }));
    await screen.findByText(/Upload failed\. The server accepted none of these files\./);
    expect(screen.queryByText("Import complete")).toBeNull();
    expect(screen.queryByText(/Network error/)).toBeNull();
    expect(screen.getByText(/3 × Could not reach the API at http:\/\/localhost:8000/)).toBeTruthy();
    expect(screen.getByText(/No request reached the server/)).toBeTruthy();
    // The upload counts are about this batch only; the existing totals are labelled as the whole database.
    const mine = screen.getByLabelText("Counts for this upload only");
    expect(mine.textContent).toMatch(/CVs selected3/);
    expect(mine.textContent).toMatch(/Accepted as new0/);
    expect(mine.textContent).toMatch(/Upload failed3/);
    expect(screen.getByText("Candidate Repository")).toBeTruthy();
    expect(screen.getByText(/do not show whether this upload worked/)).toBeTruthy();
    expect(screen.getAllByText("472").length).toBeGreaterThan(0);
  });

  it("checks the API first and uploads nothing when it is unreachable", async () => {
    api.getDemoStatus.mockResolvedValue(status());
    api.checkApiReachable.mockRejectedValue(new ConnectionError("http://localhost:8000", "the request was blocked or got no response"));
    render(<DemoData />);
    await chooseFiles(["a.pdf", "b.pdf"]);
    fireEvent.click(screen.getByRole("button", { name: /Import CVs/ }));
    await screen.findByText(/The API is not reachable\. Nothing was uploaded\./);
    expect(api.uploadDocument).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("This upload")).toBeNull();
    expect(screen.queryByText("Import complete")).toBeNull();
    // The files stay selected, so the same click works once the API is back.
    expect(screen.getByText(/2 CVs selected/)).toBeTruthy();
    api.checkApiReachable.mockResolvedValue(undefined);
    api.uploadDocument.mockImplementation(async (f: File) => ({ id: f.name, status: "received", created: true }));
    fireEvent.click(screen.getByRole("button", { name: /Import CVs/ }));
    await waitFor(() => expect(api.uploadDocument).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByText(/The API is not reachable/)).toBeNull());
  });

  it("retries only the failed files after an outage and then reports a complete, accurate upload", async () => {
    api.getDemoStatus.mockResolvedValue(status());
    let up = false;
    api.uploadDocument.mockImplementation(async (f: File) => {
      if (!up) throw new ConnectionError("http://localhost:8000");
      return { id: f.name, status: "received", created: true };
    });
    render(<DemoData />);
    await chooseFiles(["a.pdf", "b.pdf", "c.pdf", "d.pdf", "e.pdf"]);
    fireEvent.click(screen.getByRole("button", { name: /Import CVs/ }));
    await screen.findByText(/Upload failed\. The server accepted none/);
    up = true;
    api.uploadDocument.mockClear();
    fireEvent.click(screen.getByRole("button", { name: /Retry 5 failed files/ }));
    await waitFor(() => expect(screen.getByText("Import complete")).toBeTruthy(), { timeout: 4000 });
    expect(api.uploadDocument).toHaveBeenCalledTimes(5);
    const mine = screen.getByLabelText("Counts for this upload only");
    expect(mine.textContent).toMatch(/CVs selected5/);
    expect(mine.textContent).toMatch(/Accepted as new5/);
    expect(mine.textContent).toMatch(/Upload failed0/);
    expect(screen.queryByText(/did not upload/)).toBeNull();
  });

  it("separates already-on-record files from new ones and still completes", async () => {
    api.getDemoStatus.mockResolvedValue(status({ documents: 4 }));
    api.uploadDocument.mockImplementation(async (f: File) => ({ id: f.name, status: "profiled", created: f.name !== "old.pdf" }));
    render(<DemoData />);
    await chooseFiles(["new.pdf", "old.pdf"]);
    fireEvent.click(screen.getByRole("button", { name: /Import CVs/ }));
    await waitFor(() => expect(screen.getByText("Import complete")).toBeTruthy(), { timeout: 4000 });
    const mine = screen.getByLabelText("Counts for this upload only");
    expect(mine.textContent).toMatch(/Accepted as new1/);
    expect(mine.textContent).toMatch(/Already on record1/);
  });
});

describe("Reset candidate repository", () => {
  it("only accepts the exact phrase", () => {
    expect(RESET_PHRASE).toBe("RESET");
    expect(phraseMatches("RESET")).toBe(true);
    expect(phraseMatches("  RESET ")).toBe(true);
    expect(phraseMatches("reset")).toBe(false);
    expect(phraseMatches("RESE")).toBe(false);
    expect(phraseMatches("")).toBe(false);
  });

  it("keeps the confirm button disabled until RESET is typed, then resets once", async () => {
    api.resetDemoData.mockResolvedValue({ reset_at: "2026-09-30T12:00:00Z" });
    const done = vi.fn();
    render(<ResetPanel lastResetAt={null} disabled={false} onDone={done} />);
    fireEvent.click(screen.getByRole("button", { name: /Reset candidate repository…/ }));
    const confirm = screen.getByRole("button", { name: "Reset candidate repository" }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    const box = screen.getByLabelText(/Type RESET to confirm/);
    fireEvent.change(box, { target: { value: "reset" } });
    expect(confirm.disabled).toBe(true);
    fireEvent.change(box, { target: { value: "RESET" } });
    expect(confirm.disabled).toBe(false);
    fireEvent.click(confirm);
    await waitFor(() => expect(done).toHaveBeenCalledTimes(1));
    expect(api.resetDemoData).toHaveBeenCalledTimes(1);
    await screen.findByText(/Last reset:/);
  });

  it("cancel resets nothing, and the trigger is disabled while an upload is running", () => {
    const { rerender } = render(<ResetPanel lastResetAt={null} disabled={false} onDone={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /Reset candidate repository…/ }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(api.resetDemoData).not.toHaveBeenCalled();
    rerender(<ResetPanel lastResetAt={null} disabled onDone={vi.fn()} />);
    expect((screen.getByRole("button", { name: /Reset candidate repository…/ }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("formatElapsed", () => {
  it("prints seconds and minutes from the measured milliseconds", () => {
    expect(formatElapsed(0)).toBe("0 s");
    expect(formatElapsed(42_400)).toBe("42 s");
    expect(formatElapsed(125_000)).toBe("2 min 05 s");
  });
});
