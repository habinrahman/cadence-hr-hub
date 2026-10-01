// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/ui/toast";
import { ApiError } from "@/lib/errors";

const api = vi.hoisted(() => ({
  submitSourcedCandidate: vi.fn(),
  getSourcedCandidate: vi.fn(),
  getReview: vi.fn(),
  decideReview: vi.fn(),
}));
vi.mock("@/lib/api", () => api);
vi.mock("next/link", () => ({ default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a> }));

import { SourceDesk } from "../form";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const lead = (overrides = {}) => ({
  id: "s1",
  display_name: "Lena Lead",
  email: null,
  phone: null,
  source_type: "linkedin",
  source_reference: "linkedin.com/in/lena",
  notes: null,
  document_id: null,
  document_status: null,
  identity_outcome: null,
  candidate_id: "c-new",
  review_id: null,
  events: [],
  ...overrides,
});

function fill() {
  render(
    <ToastProvider>
      <SourceDesk />
    </ToastProvider>,
  );
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Lena Lead" } });
  fireEvent.change(screen.getByLabelText("Source reference"), { target: { value: "linkedin.com/in/lena" } });
}

describe("sourcing a candidate with no CV", () => {
  it("saves a lead without a CV", async () => {
    api.submitSourcedCandidate.mockResolvedValue(lead());
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Add sourced candidate" }));
    await screen.findByText(/Candidate added without a CV/);
    const sent = api.submitSourcedCandidate.mock.calls[0][0] as FormData;
    expect(sent.get("file")).toBeNull();
  });

  it("asks the recruiter when the person may already exist, and saves only their choice", async () => {
    api.submitSourcedCandidate
      .mockRejectedValueOnce(
        new ApiError(409, "possible_existing", {
          code: "possible_existing",
          matches: [{ candidate_id: "c-old", display_name: "Lena Lead", reasons: ["same_email", "same_name"] }],
        }),
      )
      .mockResolvedValueOnce(lead({ candidate_id: "c-old" }));
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Add sourced candidate" }));
    await screen.findByText("This person may already be on file");
    expect(screen.getByText("Same email")).toBeTruthy();
    expect(document.body.textContent).toMatch(/Nothing has been saved yet/);
    fireEvent.click(screen.getByRole("button", { name: "Same person — add source to this profile" }));
    await waitFor(() => expect(api.submitSourcedCandidate).toHaveBeenCalledTimes(2));
    const second = api.submitSourcedCandidate.mock.calls[1][0] as FormData;
    expect(second.get("attach_to")).toBe("c-old");
    await screen.findByText(/Source added to the existing profile/);
  });
});
