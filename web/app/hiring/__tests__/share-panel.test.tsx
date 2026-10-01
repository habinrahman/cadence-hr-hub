// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/ui/toast";

const api = vi.hoisted(() => ({ getSharePreview: vi.fn(), approveShare: vi.fn(), sendShare: vi.fn(), setRequestContact: vi.fn() }));
vi.mock("@/lib/api", () => api);

import { SharePanel } from "../share-panel";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const preview = (approved: boolean) => ({
  company: "ABC Technologies",
  recipient: "company@localhost",
  candidate: "Ada Example",
  candidate_id: "c1",
  role: "Python Backend Engineer",
  selected: { years_of_experience: 4, requirements_met: ["Python"] },
  approved,
  sharing: null,
});

function open(approved: boolean) {
  api.getSharePreview.mockResolvedValue(preview(approved));
  const onChanged = vi.fn();
  render(
    <ToastProvider>
      <SharePanel requestId="r1" candidateId="c1" candidateName="Ada Example" onClose={vi.fn()} onChanged={onChanged} />
    </ToastProvider>,
  );
  return onChanged;
}

describe("share panel: one decision, still two server records", () => {
  it("approves and sends from one confirmation, in that order", async () => {
    const onChanged = open(false);
    api.approveShare.mockResolvedValue({ id: "a", decision: "approved" });
    api.sendShare.mockResolvedValue({ id: "s", status: "sent", destination: "smtp", recipient: "company@localhost", sent_at: null, sender: null, audit: null });
    await screen.findByRole("button", { name: "Approve & send" });
    expect(document.body.textContent).toMatch(/An email about Ada Example goes to company@localhost now\. This cannot be undone/);
    expect(api.approveShare).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByRole("button", { name: "Approve & send" }));
    expect(screen.queryByRole("dialog", { name: /Approve and send/ })).toBeNull();
    await waitFor(() => expect(api.sendShare).toHaveBeenCalled());
    expect(api.approveShare.mock.invocationCallOrder[0]).toBeLessThan(api.sendShare.mock.invocationCallOrder[0]);
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("does not send, and does not claim an approval, when the approval is refused", async () => {
    const onChanged = open(false);
    api.approveShare.mockRejectedValue(new Error("pool_provisional"));
    fireEvent.click(await screen.findByRole("button", { name: "Approve & send" }));
    await waitFor(() => expect(api.approveShare).toHaveBeenCalled());
    expect(api.sendShare).not.toHaveBeenCalled();
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("offers only the send when the approval is already recorded", async () => {
    open(true);
    api.sendShare.mockResolvedValue({ id: "s", status: "sent", destination: "smtp", recipient: "x", sent_at: null, sender: null, audit: null });
    fireEvent.click(await screen.findByRole("button", { name: "Send email" }));
    await waitFor(() => expect(api.sendShare).toHaveBeenCalled());
    expect(api.approveShare).not.toHaveBeenCalled();
  });

  it("asks for the company contact before anything can be sent", async () => {
    api.getSharePreview.mockResolvedValue({ ...preview(false), recipient: null });
    api.setRequestContact.mockResolvedValue({ id: "r1", contact_email: "hiring@abc.example" });
    render(
      <ToastProvider>
        <SharePanel requestId="r1" candidateId="c1" candidateName="Ada Example" onClose={vi.fn()} onChanged={vi.fn()} />
      </ToastProvider>,
    );
    await screen.findByText("Not set yet");
    expect(screen.queryByRole("button", { name: "Approve & send" })).toBeNull();
    fireEvent.change(screen.getByLabelText(/receives this shortlist/), { target: { value: "hiring@abc.example" } });
    fireEvent.click(screen.getByRole("button", { name: "Save company contact" }));
    await screen.findByRole("button", { name: "Approve & send" });
    expect(api.setRequestContact).toHaveBeenCalledWith("r1", "hiring@abc.example");
    expect(api.approveShare).not.toHaveBeenCalled();
  });
});
