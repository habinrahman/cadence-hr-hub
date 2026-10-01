import { describe, expect, it } from "vitest";
import { FOCUS_LIMIT, clampPage, previewKind, previewPath, unavailableNotice } from "@/lib/page-preview";

describe("previewKind", () => {
  it("draws PDFs only", () => {
    expect(previewKind("application/pdf")).toBe("pdf");
    expect(previewKind("application/vnd.openxmlformats-officedocument.wordprocessingml.document")).toBe("word");
    expect(previewKind("application/msword")).toBe("word");
    expect(previewKind("image/png")).toBe("other");
    expect(previewKind(null)).toBe("other");
    expect(previewKind(undefined)).toBe("other");
  });
  it("says plainly that a Word document has no visual preview", () => {
    expect(unavailableNotice("word")).toBe("Visual preview unavailable for Word document. Text comparison is available below.");
    expect(unavailableNotice("other")).toBe("Visual preview unavailable for this file type. Text comparison is available below.");
  });
});

describe("previewPath", () => {
  const base = { reviewId: "r1", documentId: "d1", page: 2 };
  it("names the review, the document and the page", () => {
    expect(previewPath(base)).toBe("/reviews/r1/documents/d1/pages/2/preview?width=900");
  });
  it("carries the chosen candidate and an encoded evidence quote", () => {
    const path = previewPath({ ...base, candidateId: "c9", focus: "Google, Senior Engineer & Lead" });
    const query = new URL("http://x" + path).searchParams;
    expect(query.get("candidate_id")).toBe("c9");
    expect(query.get("focus")).toBe("Google, Senior Engineer & Lead");
    expect(path).not.toContain("& Lead");
  });
  it("collapses whitespace and never sends more than the server accepts", () => {
    const long = "word ".repeat(200);
    const focus = new URL("http://x" + previewPath({ ...base, focus: long })).searchParams.get("focus") ?? "";
    expect(focus.length).toBeLessThanOrEqual(FOCUS_LIMIT);
    expect(previewPath({ ...base, focus: "  \n " })).not.toContain("focus=");
  });
});

describe("clampPage", () => {
  it("keeps the page inside the document", () => {
    expect(clampPage(0, 3)).toBe(1);
    expect(clampPage(9, 3)).toBe(3);
    expect(clampPage(2, 3)).toBe(2);
    expect(clampPage(2, 0)).toBe(1);
    expect(clampPage(Number.NaN, 4)).toBe(1);
  });
});
