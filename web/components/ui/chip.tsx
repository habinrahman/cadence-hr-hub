import type { ReactNode } from "react";

export function Chip({
  children,
  onRemove,
  removeLabel = "Remove",
  className = "",
}: {
  children: ReactNode;
  onRemove?: () => void;
  removeLabel?: string;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-[3px] border border-rule-strong bg-panel px-2 py-px text-xs ${className}`}
    >
      {children}
      {onRemove ? (
        <button
          type="button"
          aria-label={removeLabel}
          onClick={onRemove}
          className="-mr-1 ml-0.5 inline-flex h-5 w-5 items-center justify-center rounded text-mut hover:bg-inset hover:text-ink"
        >
          <span aria-hidden="true">×</span>
        </button>
      ) : null}
    </span>
  );
}
