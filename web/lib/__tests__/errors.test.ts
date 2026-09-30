import { describe, it, expect } from "vitest";
import { ApiError, describeError } from "@/lib/errors";

describe("describeError", () => {
  it("explains 401", () => {
    const e = describeError(new ApiError(401, "unauthorized"));
    expect(e.kind).toBe("auth");
    expect(e.title).toMatch(/not accepted/i);
  });
  it("explains 403 by role", () => {
    const e = describeError(new ApiError(403, "recruiter_required"));
    expect(e.kind).toBe("forbidden");
    expect(e.body).toMatch(/role/i);
  });
  it("maps known conflict codes to plain words", () => {
    expect(describeError(new ApiError(409, "requirements_not_approved")).body).toMatch(/approve/i);
    expect(describeError(new ApiError(409, "not_shortlisted")).body).toMatch(/shortlist/i);
    expect(describeError(new ApiError(409, "request_not_open")).kind).toBe("conflict");
  });
  it("handles unknown 5xx and network failure", () => {
    expect(describeError(new ApiError(500, "boom")).kind).toBe("server");
    expect(describeError(new TypeError("Failed to fetch")).kind).toBe("network");
  });
  it("never returns raw JSON", () => {
    expect(describeError(new ApiError(422, "[object Object]")).body).not.toMatch(/object Object/);
  });
});
