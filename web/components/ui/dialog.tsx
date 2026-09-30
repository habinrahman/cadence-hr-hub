"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { Button } from "./button";

function useModal(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    const handle = (event: Event) => {
      event.preventDefault();
      onClose();
    };
    dialog.addEventListener("cancel", handle);
    return () => dialog.removeEventListener("cancel", handle);
  }, [onClose]);
  return ref;
}

export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  tone = "primary",
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  body: ReactNode;
  confirmLabel: string;
  tone?: "primary" | "danger";
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useModal(open, onCancel);
  const titleId = useId();
  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClick={(event) => {
        if (event.target === ref.current) onCancel();
      }}
    >
      <div className="p-5">
        <h2 id={titleId} className="text-base font-bold">
          {title}
        </h2>
        <div className="mt-2 text-[14px] text-ink">{body}</div>
        <div className="mt-5 flex flex-wrap justify-end gap-2">
          <Button onClick={onCancel} autoFocus={tone === "danger"}>
            Cancel
          </Button>
          <Button variant={tone === "danger" ? "danger" : "primary"} busy={busy} onClick={onConfirm} autoFocus={tone !== "danger"}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </dialog>
  );
}

export function SlideOver({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useModal(open, onClose);
  const titleId = useId();
  return (
    <dialog
      ref={ref}
      className="slide-over"
      aria-labelledby={titleId}
      onClick={(event) => {
        if (event.target === ref.current) onClose();
      }}
    >
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-between gap-3 border-b border-rule px-4 py-3">
          <h2 id={titleId} className="min-w-0 break-words text-base font-bold">
            {title}
          </h2>
          <Button onClick={onClose} aria-label="Close panel">
            Close
          </Button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">{open ? children : null}</div>
      </div>
    </dialog>
  );
}
