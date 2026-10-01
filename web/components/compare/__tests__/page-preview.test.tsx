// @vitest-environment jsdom
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CompareDocument, Comparison } from "@/lib/api";
import { ApiError } from "@/lib/errors";

const api = vi.hoisted(() => ({ fetchPagePreview: vi.fn(), getDocumentPages: vi.fn() }));
vi.mock("@/lib/api", () => api);

import { DocumentCompare } from "../document-viewer";

const PDF = "application/pdf";
const DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

const doc = (id: string, media_type = PDF, page_count = 2): CompareDocument => ({
  id,
  filename: `${id}.pdf`,
  media_type,
  byte_size: 1000,
  received_at: "2026-09-01T00:00:00Z",
  page_count,
  status: "profiled",
  is_current: false,
  text_source: "text_layer",
  language_code: "en",
  error_code: null,
});

function comparison(over: { existing?: Partial<Comparison["existing"]>; incoming?: Partial<Comparison["incoming"]> } = {}): Comparison {
  return {
    review_id: "r1",
    status: "pending",
    decided_at: null,
    available: true,
    reason: null,
    warnings: [],
    candidates: [],
    candidate: { id: "c1", name: "Barak Buta", merged_into_id: null },
    existing: { state: "ok", document: doc("d-old"), ...over.existing },
    incoming: { state: "ok", document: doc("d-new"), ...over.incoming },
    identical_bytes: false,
    fields: [],
    dates: null,
    text_diff: { available: true, note: "", incoming_only: [], existing_only: [], incoming_only_count: 0, existing_only_count: 0, truncated: false },
  } as unknown as Comparison;
}

const image = (pages = 2, highlights = 3) => ({ blob: new Blob(["png"]), pages, highlights });
let urls = 0;

beforeEach(() => {
  api.fetchPagePreview.mockReset();
  api.getDocumentPages.mockReset();
  urls = 0;
  URL.createObjectURL = vi.fn(() => `blob:page-${++urls}`);
  URL.revokeObjectURL = vi.fn();
});
afterEach(cleanup);

const panel = (name: string) => within(screen.getByRole("region", { name }));

describe("page view", () => {
  it("draws nothing until it is opened, then shows the real page with its marks", async () => {
    api.fetchPagePreview.mockResolvedValue(image());
    const user = userEvent.setup();
    render(<DocumentCompare comparison={comparison()} focus={null} />);
    expect(api.fetchPagePreview).not.toHaveBeenCalled();
    expect(panel("New CV text").getByText(/recorded in the audit trail/)).toBeTruthy();
    await user.click(panel("New CV text").getByRole("button", { name: "Open page view" }));
    const picture = await screen.findByAltText("New CV, page 1 of 2");
    expect(picture.getAttribute("src")).toBe("blob:page-1");
    expect(api.fetchPagePreview).toHaveBeenCalledTimes(1);
    const path = api.fetchPagePreview.mock.calls[0][0] as string;
    expect(path).toContain("/reviews/r1/documents/d-new/pages/1/preview");
    expect(path).toContain("candidate_id=c1");
    expect(panel("New CV text").getByText("Page 1 of 2")).toBeTruthy();
    expect(panel("New CV text").getByText("3 marks on this page.")).toBeTruthy();
    expect(panel("New CV text").getByText(/Some lines may not be located/)).toBeTruthy();
  });

  it("moves between pages and frees the previous image", async () => {
    api.fetchPagePreview.mockResolvedValue(image());
    const user = userEvent.setup();
    render(<DocumentCompare comparison={comparison()} focus={null} />);
    await user.click(panel("Previous CV text").getByRole("button", { name: "Open page view" }));
    await screen.findByAltText("Previous CV, page 1 of 2");
    await user.click(panel("Previous CV text").getByRole("button", { name: "Previous CV: next page" }));
    await screen.findByAltText("Previous CV, page 2 of 2");
    expect((api.fetchPagePreview.mock.calls[1][0] as string)).toContain("/documents/d-old/pages/2/preview");
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:page-1");
    expect((panel("Previous CV text").getByRole("button", { name: "Previous CV: next page" }) as HTMLButtonElement).disabled).toBe(true);
    expect((panel("Previous CV text").getByRole("button", { name: "Previous CV: previous page" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("frees the last image when the comparison closes", async () => {
    api.fetchPagePreview.mockResolvedValue(image());
    const user = userEvent.setup();
    const { unmount } = render(<DocumentCompare comparison={comparison()} focus={null} />);
    await user.click(panel("New CV text").getByRole("button", { name: "Open page view" }));
    await screen.findByAltText("New CV, page 1 of 2");
    unmount();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:page-1");
  });

  it("opens the cited page and outlines the selected evidence when an evidence link is used", async () => {
    api.fetchPagePreview.mockResolvedValue(image());
    render(<DocumentCompare comparison={comparison()} focus={{ side: "incoming", page: 2, quote: "Google, Senior Engineer" }} />);
    await screen.findByAltText("New CV, page 2 of 2");
    const query = new URL("http://x" + (api.fetchPagePreview.mock.calls[0][0] as string)).searchParams;
    expect(query.get("focus")).toBe("Google, Senior Engineer");
    expect(api.fetchPagePreview.mock.calls[0][0]).toContain("/pages/2/preview");
    expect(api.getDocumentPages).not.toHaveBeenCalled();
  });

  it("shows the Text view without touching the page route", async () => {
    api.getDocumentPages.mockResolvedValue({ id: "d-new", page_count: 1, pages: [{ number: 1, text: "Barak Buta" }] });
    const user = userEvent.setup();
    render(<DocumentCompare comparison={comparison()} focus={null} />);
    await user.click(within(screen.getByRole("group", { name: "New CV view" })).getByRole("button", { name: "Text" }));
    await user.click(panel("New CV text").getByRole("button", { name: "Open CV text" }));
    await screen.findByLabelText("New CV, page 1");
    expect(api.fetchPagePreview).not.toHaveBeenCalled();
  });

  it("says a page could not be drawn, keeps the text available, and retries", async () => {
    api.fetchPagePreview.mockRejectedValueOnce(new ApiError(422, "preview_failed")).mockResolvedValueOnce(image());
    const user = userEvent.setup();
    render(<DocumentCompare comparison={comparison()} focus={null} />);
    await user.click(panel("New CV text").getByRole("button", { name: "Open page view" }));
    await screen.findByText("This page could not be drawn.");
    expect(screen.getByText("The text view still shows this CV.")).toBeTruthy();
    await user.click(panel("New CV text").getByRole("button", { name: "Try again" }));
    await screen.findByAltText("New CV, page 1 of 2");
    expect(api.fetchPagePreview).toHaveBeenCalledTimes(2);
  });

  it("is honest about a PDF with no text layer: it still draws, and marks nothing", async () => {
    api.fetchPagePreview.mockResolvedValue(image(1, 0));
    const user = userEvent.setup();
    render(<DocumentCompare comparison={comparison({ incoming: { state: "needs_ocr", document: doc("d-new", PDF, 1) } })} focus={null} />);
    expect(panel("New CV text").getByText(/no readable text layer/)).toBeTruthy();
    await user.click(panel("New CV text").getByRole("button", { name: "Open page view" }));
    await screen.findByAltText("New CV, page 1 of 1");
    expect(panel("New CV text").getByText("Nothing is marked on this page.")).toBeTruthy();
  });
});

describe("a Word document", () => {
  it("says there is no visual preview, makes no request, and keeps the text comparison", async () => {
    render(<DocumentCompare comparison={comparison({ incoming: { state: "ok", document: doc("d-new", DOCX) } })} focus={null} />);
    expect(panel("New CV text").getByText("Visual preview unavailable for Word document. Text comparison is available below.")).toBeTruthy();
    expect(panel("New CV text").queryByRole("button", { name: "Open page view" })).toBeNull();
    expect(panel("New CV text").getByRole("button", { name: "Open CV text" })).toBeTruthy();
    expect(api.fetchPagePreview).not.toHaveBeenCalled();
    // The PDF on the other side is unaffected.
    expect(panel("Previous CV text").getByRole("button", { name: "Open page view" })).toBeTruthy();
  });

  it("does not request a preview even if an evidence link points at it", async () => {
    api.getDocumentPages.mockResolvedValue({ id: "d-new", page_count: 1, pages: [{ number: 1, text: "Google, Senior Engineer" }] });
    render(<DocumentCompare comparison={comparison({ incoming: { state: "ok", document: doc("d-new", DOCX, 1) } })} focus={{ side: "incoming", page: 1, quote: "Google, Senior Engineer" }} />);
    await waitFor(() => expect(api.getDocumentPages).toHaveBeenCalledWith("d-new"));
    expect(api.fetchPagePreview).not.toHaveBeenCalled();
  });
});
