import { describe, it, expect } from "vitest";
import { shortDate, shortDateTime, relativeAge, plural } from "@/lib/format";

const now = new Date("2026-09-30T12:00:00Z");
describe("format", () => {
  it("formats dates", () => {
    expect(shortDate("2026-09-28T09:00:00Z")).toBe("28 Sep 2026");
    expect(shortDate(null)).toBe("—");
    expect(shortDate("")).toBe("—");
  });
  it("gives relative ages", () => {
    expect(relativeAge("2026-09-30T08:00:00Z", now)).toBe("today");
    expect(relativeAge("2026-09-28T12:00:00Z", now)).toBe("2 days ago");
    expect(relativeAge("2026-09-09T12:00:00Z", now)).toBe("3 weeks ago");
  });
  it("pluralises", () => {
    expect(plural(1, "item")).toBe("1 item");
    expect(plural(3, "item")).toBe("3 items");
    expect(plural(2, "match", "matches")).toBe("2 matches");
  });
  it("formats date and time in UTC", () => {
    expect(shortDateTime("2026-09-28T09:05:00Z")).toBe("28 Sep 2026, 09:05 UTC");
    expect(shortDateTime(undefined)).toBe("—");
  });
});
