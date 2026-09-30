import { describe, it, expect } from "vitest";
import { groupQueue, requestIdFromHref } from "@/lib/queue";

const item = (type: string, subject: string, href: string, created_at = "2026-09-30T10:00:00Z") =>
  ({ type, subject, status: "proposed", created_at, href });

describe("queue", () => {
  it("extracts request ids", () => {
    expect(requestIdFromHref("/hiring?request=abc&candidate=x")).toBe("abc");
    expect(requestIdFromHref("/?document=d1")).toBeNull();
  });
  it("groups requirement rows by request", () => {
    const g = groupQueue([
      item("requirement_approval", "Example Labs · Backend engineer", "/hiring?request=r1"),
      item("requirement_approval", "Example Labs · Backend engineer", "/hiring?request=r1", "2026-09-30T11:00:00Z"),
      item("requirement_approval", "Harbor · Accountant", "/hiring?request=r2"),
    ]);
    expect(g).toHaveLength(2);
    const r1 = g.find((x) => x.requestId === "r1")!;
    expect(r1.count).toBe(2);
    expect(r1.created_at).toBe("2026-09-30T11:00:00Z");
  });
  it("groups matches and lists candidate names", () => {
    const g = groupQueue([
      item("match_review", "Amira Khan · Example Labs · Backend engineer", "/hiring?request=r1"),
      item("match_review", "Jonas Weber · Example Labs · Backend engineer", "/hiring?request=r1"),
    ]);
    expect(g).toHaveLength(1);
    expect(g[0].names).toEqual(["Amira Khan", "Jonas Weber"]);
    expect(g[0].subject).toBe("Example Labs · Backend engineer");
  });
  it("keeps relationship and share rows separate", () => {
    const g = groupQueue([
      item("relationship_review", "Amira Khan", "/?document=d1"),
      item("relationship_review", "Amira Khan", "/?document=d2"),
      item("share_approval", "Jonas · Example Labs · Backend", "/hiring?request=r1&candidate=c1"),
      item("share_approval", "Lena · Example Labs · Backend", "/hiring?request=r1&candidate=c2"),
    ]);
    expect(g).toHaveLength(4);
  });
  it("orders newest first", () => {
    const g = groupQueue([
      item("relationship_review", "Old", "/?document=a", "2026-09-01T00:00:00Z"),
      item("relationship_review", "New", "/?document=b", "2026-09-29T00:00:00Z"),
    ]);
    expect(g[0].subject).toBe("New");
  });
});
