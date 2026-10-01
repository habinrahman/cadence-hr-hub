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
    expect(describeSignal(signal({ code: "email", state: "matched" }))).toEqual({ text: "Same email address — strong identity evidence", kind: "match" });
    expect(describeSignal(signal({ code: "phone", state: "unmatched" }))).toEqual({
      text: "Different phone number — evidence against the same person",
      kind: "mismatch",
    });
  });
  it("treats unknown as unknown, not as a mismatch", () => {
    const result = describeSignal(signal({ code: "phone", state: "unknown", value: null }));
    expect(result.kind).toBe("unknown");
    expect(result.text).toMatch(/not available/i);
  });
  it("words missing sections as not compared, never as a difference", () => {
    for (const code of ["employment", "education", "skills", "semantic", "cv_dates", "explicit_version"]) {
      const result = describeSignal(signal({ code, state: "unknown", value: null }));
      expect(result.kind).toBe("unknown");
      expect(result.text).toMatch(/not (compared|available)/i);
    }
  });
  it("treats dates as update evidence, not as evidence against the same person", () => {
    expect(describeSignal(signal({ code: "cv_dates", state: "unmatched" })).kind).toBe("info");
    expect(describeSignal(signal({ code: "explicit_version", state: "unmatched" })).kind).toBe("info");
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
    expect(describeSignal(matched).text).toBe("Same phone number — strong identity evidence");
    expect(describeSignal(matched, { sharedPhone: true }).text).toBe("Same phone number — strong identity evidence");
    const doubtful = describeSignal(matched, { sharedPhone: false });
    expect(doubtful.kind).toBe("unknown");
    expect(doubtful.text).toMatch(/date-like digits/i);
    expect(doubtful.text).not.toMatch(/^Same phone/);
  });
  it("only second-guesses the phone signal, never the email signal", () => {
    expect(describeSignal(signal({ code: "email", state: "matched" }), { sharedPhone: false }).text).toBe("Same email address — strong identity evidence");
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
    expect(ITEM_STATUS.only_existing.label).toBe("Not found in new CV");
    expect(ITEM_STATUS.unknown.label).toBe("Not compared");
  });
});

describe("decisionCopy", () => {
  it("uses the three action names and says what each one really does", () => {
    expect(decisionCopy("accept_update").label).toBe("Merge & Update Profile");
    expect(decisionCopy("accept_update").body).toMatch(/becomes their current CV/i);
    expect(decisionCopy("accept_update").body).toMatch(/stays in the candidate's history/i);
    expect(decisionCopy("record_duplicate").label).toBe("Delete Duplicate");
    expect(decisionCopy("create_separate_candidate").label).toBe("Create New Candidate");
    expect(decisionCopy("create_separate_candidate").body).toMatch(/new candidate profile/i);
  });
  it("Delete Duplicate is the danger action and says only the duplicate is archived", () => {
    const copy = decisionCopy("record_duplicate");
    expect(copy.tone).toBe("danger");
    expect(copy.body).toMatch(/only this duplicate/i);
    expect(copy.body).toMatch(/archived/i);
    expect(copy.body).toMatch(/current CV are not changed/i);
  });
  it("an Excel row has no CV to delete, so it never says Delete Duplicate", () => {
    const copy = decisionCopy("record_duplicate", false);
    expect(copy.label).toBe("Record as duplicate");
    expect(copy.body.toLowerCase()).not.toMatch(/delete|archiv/);
  });
  it("only Delete Duplicate mentions deleting", () => {
    for (const action of ["accept_update", "create_separate_candidate"]) {
      expect(decisionCopy(action).body.toLowerCase()).not.toMatch(/delete/);
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
    expect(result.headline).toBe("Possible relationship — review required");
  });
  it("says possible different person when the same person is unlikely", () => {
    const result = recommendation({ ...base, likely_relationship: "different_candidate", recommended_action: null, confidence: 25 });
    expect(result.headline).toBe("Possible different person");
  });

  it("calls a shared phone with a different email conflicting evidence, not a different person", () => {
    const evidence = [
      { code: "email", weight: 0.5, state: "unmatched", value: 0 },
      { code: "phone", weight: 0.8, state: "matched", value: 1 },
    ];
    const result = recommendation({ ...base, likely_relationship: "updated_cv", recommended_action: null, confidence: 46, evidence });
    expect(result.headline).toBe("Conflicting contact details — your decision");
    expect(result.basis).toMatch(/same phone number, but a different email address/);
    expect(result.action).toBeNull();
    expect(result.action).toBeNull();
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
