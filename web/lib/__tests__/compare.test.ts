import { describe, it, expect } from "vitest";
import {
  ITEM_STATUS,
  decisionCopy,
  describeSignal,
  documentStateMessage,
  isDecided,
  normalizeLine,
  recommendation,
  summarize,
} from "@/lib/compare";
import type { Comparison, CompareField, EvidenceItem } from "@/lib/api";

const signal = (over: Partial<EvidenceItem>): EvidenceItem => ({ code: "email", weight: 0.5, state: "matched", value: 1, ...over });

const field = (over: Partial<CompareField>): CompareField => ({
  key: "skills",
  label: "Skills",
  comparable: true,
  existing_state: "extracted",
  incoming_state: "extracted",
  note: null,
  items: [],
  ...over,
});

const comparison = (fields: CompareField[], over: Partial<Comparison> = {}): Comparison => ({
  review_id: "r1",
  status: "pending",
  decided_at: null,
  available: true,
  reason: null,
  warnings: [],
  candidates: [],
  candidate: null,
  existing: null,
  incoming: null,
  identical_bytes: false,
  fields,
  dates: null,
  text_diff: null,
  ...over,
});

describe("describeSignal", () => {
  it("says what matched in plain words", () => {
    expect(describeSignal(signal({ code: "email", state: "matched" }))).toEqual({ text: "Same email address", kind: "match" });
    expect(describeSignal(signal({ code: "phone", state: "unmatched" })).text).toBe("Different phone number");
  });
  it("treats unknown as unknown, not as a mismatch", () => {
    const result = describeSignal(signal({ code: "phone", state: "unknown", value: null }));
    expect(result.kind).toBe("unknown");
    expect(result.text).toMatch(/not available/i);
  });
  it("reports similarity as a percentage of overlap", () => {
    expect(describeSignal(signal({ code: "name", state: "recorded", value: 0.67 })).text).toBe("Name similarity 67%");
    expect(describeSignal(signal({ code: "skills", state: "recorded", value: 0.5 })).text).toBe("Skills overlap 50%");
  });
  it("words the date signals as later or not later, never as newer filenames", () => {
    expect(describeSignal(signal({ code: "cv_dates", state: "matched" })).text).toMatch(/later dates/i);
    expect(describeSignal(signal({ code: "explicit_version", state: "unmatched" })).text).toMatch(/not later/i);
  });
  it("does not repeat a phone match when the two CVs share no phone number", () => {
    const matched = signal({ code: "phone", state: "matched" });
    expect(describeSignal(matched).text).toBe("Same phone number");
    expect(describeSignal(matched, { sharedPhone: true }).text).toBe("Same phone number");
    const doubtful = describeSignal(matched, { sharedPhone: false });
    expect(doubtful.kind).toBe("unknown");
    expect(doubtful.text).toMatch(/date-like digits/i);
    expect(doubtful.text).not.toMatch(/^Same phone/);
  });
  it("only second-guesses the phone signal, never the email signal", () => {
    expect(describeSignal(signal({ code: "email", state: "matched" }), { sharedPhone: false }).text).toBe("Same email address");
  });
  it("does not call the wording similarity a meaning model", () => {
    expect(describeSignal(signal({ code: "semantic", state: "recorded", value: 0.4 })).text).toMatch(/word overlap/i);
  });
});

describe("summarize", () => {
  it("counts only what was compared and lists what could not be", () => {
    const result = summarize(
      comparison([
        field({
          key: "experience",
          label: "Experience",
          items: [
            { status: "same", label: "Acme", existing: null, incoming: null },
            { status: "added", label: "Google", existing: null, incoming: null },
            { status: "changed", label: "Initech", existing: null, incoming: null },
            { status: "only_existing", label: "Old Co", existing: null, incoming: null },
          ],
        }),
        field({
          key: "skills",
          label: "Skills",
          comparable: false,
          incoming_state: "not_extracted",
          items: [{ status: "unknown", label: "Python", existing: null, incoming: null }],
        }),
      ]),
    );
    expect(result).toEqual({ same: 1, added: 1, changed: 1, notFound: 1, notCompared: ["Skills"], differences: 3 });
  });
  it("never counts unknown items as differences", () => {
    const result = summarize(
      comparison([field({ comparable: false, existing_state: "not_extracted", items: [{ status: "unknown", label: "Python", existing: null, incoming: null }] })]),
    );
    expect(result.differences).toBe(0);
    expect(result.notFound).toBe(0);
  });
});

describe("item status labels", () => {
  it("never uses the word removed", () => {
    for (const meta of Object.values(ITEM_STATUS)) expect(meta.label.toLowerCase()).not.toContain("removed");
    expect(ITEM_STATUS.only_existing.label).toBe("Not found in incoming CV");
    expect(ITEM_STATUS.unknown.label).toBe("Not compared");
  });
});

describe("decisionCopy", () => {
  it("describes what each backend action really does", () => {
    expect(decisionCopy("accept_update").body).toMatch(/current CV/i);
    expect(decisionCopy("accept_update").body).toMatch(/stays in the candidate's history/i);
    expect(decisionCopy("record_duplicate").body).toMatch(/not become the current/i);
    expect(decisionCopy("create_separate_candidate").body).toMatch(/new candidate/i);
  });
  it("never promises to delete anything", () => {
    for (const action of ["accept_update", "record_duplicate", "create_separate_candidate"]) {
      expect(decisionCopy(action).body.toLowerCase()).not.toMatch(/delete|remove|merge/);
    }
  });
});

describe("recommendation", () => {
  const base = { likely_relationship: "updated_cv", recommended_action: "accept_update", confidence: 96, ambiguous: false };
  it("separates the system's suggestion from any decision", () => {
    const result = recommendation(base);
    expect(result.headline).toBe("Likely an updated CV");
    expect(result.action).toBe("accept_update");
    expect(result.basis).toMatch(/above the high-confidence setting/i);
  });
  it("proposes nothing when the backend proposes nothing", () => {
    const result = recommendation({ ...base, recommended_action: null, confidence: 60 });
    expect(result.action).toBeNull();
    expect(result.basis).toMatch(/below the high-confidence setting/i);
  });
  it("says so when more than one existing profile looks related", () => {
    expect(recommendation({ ...base, recommended_action: null, ambiguous: true }).headline).toMatch(/more than one/i);
  });
});

describe("helpers", () => {
  it("knows when a review is decided", () => {
    expect(isDecided("pending")).toBe(false);
    expect(isDecided("accepted_update")).toBe(true);
    expect(isDecided("recorded_duplicate")).toBe(true);
    expect(isDecided("created_separate")).toBe(true);
  });
  it("explains documents that cannot be read", () => {
    expect(documentStateMessage("needs_ocr", "incoming")).toMatch(/scan/i);
    expect(documentStateMessage("no_text", "existing")).toMatch(/no readable text/i);
    expect(documentStateMessage("ok", "existing")).toBeNull();
  });
  it("normalises lines the same way for matching", () => {
    expect(normalizeLine("  Google,   Senior Engineer ")).toBe("google, senior engineer");
  });
});
