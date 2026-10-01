// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ getAudit: vi.fn() }));
vi.mock("@/lib/api", () => api);
vi.mock("next/link", () => ({ default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a> }));

import { AuditTrail } from "../audit-trail";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const shared = {
  id: "e1",
  created_at: "2026-10-01T07:03:00+00:00",
  action: "candidate_shared",
  actor: { kind: "user", name: "Rana Recruiter" },
  request: { id: "r1", label: "Northwind Analytics · Data Analyst" },
  candidate: { id: "c1", label: "Daivik Vennela" },
  document: null,
  detail: {},
};

describe("audit trail", () => {
  it("says who did what to which candidate and request", async () => {
    api.getAudit.mockResolvedValue({ events: [shared], next_before: null });
    render(<AuditTrail />);
    await screen.findByText("Candidate shared");
    expect(screen.getByText("Rana Recruiter")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Daivik Vennela" }).getAttribute("href")).toBe("/candidates/c1");
    expect(screen.getByRole("link", { name: "Northwind Analytics · Data Analyst" }).getAttribute("href")).toBe("/hiring?request=r1");
  });

  it("filters to decisions by people and loads older events on request", async () => {
    api.getAudit.mockResolvedValue({ events: [shared], next_before: "2026-10-01T07:03:00+00:00" });
    render(<AuditTrail />);
    await screen.findByText("Candidate shared");
    fireEvent.click(screen.getByRole("button", { name: "Decisions by people" }));
    await waitFor(() => expect(api.getAudit).toHaveBeenLastCalledWith({ category: "decisions", before: null }));
    fireEvent.click(await screen.findByRole("button", { name: "Show older events" }));
    await waitFor(() =>
      expect(api.getAudit).toHaveBeenLastCalledWith({ category: "decisions", before: "2026-10-01T07:03:00+00:00" }),
    );
  });
});
