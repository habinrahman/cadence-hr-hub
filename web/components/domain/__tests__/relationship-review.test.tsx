// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, it, expect, vi } from "vitest";
import type { Review } from "@/lib/api";
import { RelationshipReview } from "../relationship-review";

const review = (over: Partial<Review> = {}): Review => ({
  id: "rv1",
  document_id: "doc1",
  status: "pending",
  confidence: 97,
  likely_relationship: "duplicate",
  recommended_action: "record_duplicate",
  offered_actions: ["accept_update", "record_duplicate", "create_separate_candidate"],
  candidate_id: "c1",
  candidate_ids: ["c1"],
  candidates: [{ id: "c1", display_name: "Ada Lovelace" }],
  ambiguous: false,
  evidence: [],
  ...over,
});

afterEach(cleanup);

describe("RelationshipReview", () => {
  it("offers the three explicit actions and recommends Delete Duplicate for a duplicate", () => {
    render(<RelationshipReview review={review()} busy={false} onDecide={vi.fn()} />);
    for (const name of ["Merge & Update Profile", "Delete Duplicate", "Create New Candidate"]) {
      expect(screen.getByRole("button", { name })).toBeTruthy();
    }
    expect(screen.getByText(/Duplicate: Delete Duplicate/)).toBeTruthy();
  });

  it("changes nothing on the first click: it asks first, and Cancel decides nothing", async () => {
    const user = userEvent.setup();
    const onDecide = vi.fn();
    render(<RelationshipReview review={review()} busy={false} onDecide={onDecide} />);
    await user.click(screen.getByRole("button", { name: "Delete Duplicate" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/Only this duplicate upload is deleted/)).toBeTruthy();
    expect(onDecide).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: /cancel/i }));
    expect(onDecide).not.toHaveBeenCalled();
  });

  it("decides only the confirmed action", async () => {
    const user = userEvent.setup();
    const onDecide = vi.fn();
    render(<RelationshipReview review={review()} busy={false} onDecide={onDecide} />);
    await user.click(screen.getByRole("button", { name: "Delete Duplicate" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Yes, delete duplicate" }));
    expect(onDecide).toHaveBeenCalledTimes(1);
    expect(onDecide).toHaveBeenCalledWith("record_duplicate");
  });

  it("an Excel row never offers Delete Duplicate", () => {
    render(<RelationshipReview review={review({ document_id: null, source: "excel" })} busy={false} onDecide={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Delete Duplicate" })).toBeNull();
    expect(screen.getByRole("button", { name: "Record as duplicate" })).toBeTruthy();
  });

  it("an ambiguous review proposes nothing and still waits for a person", () => {
    const onDecide = vi.fn();
    render(
      <RelationshipReview
        review={review({ ambiguous: true, recommended_action: null, likely_relationship: null, candidates: [{ id: "c1", display_name: "A" }, { id: "c2", display_name: "B" }] })}
        busy={false}
        onDecide={onDecide}
        targetId="c1"
        onTarget={vi.fn()}
      />,
    );
    expect(screen.getByText(/not confident enough to propose an action/)).toBeTruthy();
    expect(onDecide).not.toHaveBeenCalled();
  });
});
