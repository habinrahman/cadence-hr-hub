import { describe, it, expect } from "vitest";
import { displayContacts, isDateShaped, realPhones } from "@/lib/contacts";

describe("realPhones", () => {
  it("recognises date-shaped digit runs", () => {
    expect(isDateShaped("2011-03-21")).toBe(true);
    expect(isDateShaped(" 2023/1/5 ")).toBe(true);
    expect(isDateShaped("+14155557984")).toBe(false);
    expect(isDateShaped("+971 50 234 1188")).toBe(false);
    // The same date once the pipeline has normalised it to digits only.
    expect(isDateShaped("20110321")).toBe(true);
    expect(isDateShaped("20111321")).toBe(false);
    expect(isDateShaped("14155557984")).toBe(false);
  });
  it("never lists a date as a phone number, and leaves emails alone", () => {
    const contacts = [
      { kind: "phone", value: "+14155557984" },
      { kind: "phone", value: "2011-03-21" },
      { kind: "email", value: "a@example.com" },
    ];
    expect(realPhones(contacts)).toEqual(["+14155557984"]);
  });
  it("filters a contact list for display without touching emails", () => {
    const list = [
      { kind: "email", value: "20110321" },
      { kind: "phone", value: "20110321" },
      { kind: "phone", value: "14155557984" },
    ];
    expect(displayContacts(list).map((c) => `${c.kind}:${c.value}`)).toEqual(["email:20110321", "phone:14155557984"]);
  });
});
