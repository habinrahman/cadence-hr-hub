"use client";

import { useId, type ReactNode } from "react";

export const inputClass =
  "block w-full min-h-11 rounded border border-rule-strong bg-panel px-2.5 py-1.5 text-[14px] text-ink placeholder:text-mut sm:min-h-9 disabled:bg-inset";

export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string | null;
  children: (ids: { id: string; describedBy?: string; invalid: boolean }) => ReactNode;
}) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className="text-[13px]">
      <label htmlFor={id} className="mb-1 block font-semibold">
        {label}
      </label>
      {children({ id, describedBy, invalid: Boolean(error) })}
      {hint ? (
        <p id={hintId} className="mt-1 text-xs text-mut">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} role="alert" className="mt-1 text-xs font-semibold text-bad-ink">
          {error}
        </p>
      ) : null}
    </div>
  );
}
