"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";

/** Disclosure menu. Arrow keys move focus, Escape closes and returns focus to the trigger. */
export function Menu({
  label,
  children,
  align = "left",
  tone = "light",
  primary = false,
}: {
  label: string;
  children: ReactNode;
  align?: "left" | "right";
  tone?: "dark" | "light";
  primary?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const listId = useId();

  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (wrap.current && !wrap.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  useEffect(() => {
    if (open) wrap.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
  }, [open]);

  function onKeyDown(event: React.KeyboardEvent) {
    const items = Array.from(wrap.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);
    const index = items.indexOf(document.activeElement as HTMLElement);
    if (event.key === "Escape") {
      setOpen(false);
      trigger.current?.focus();
    } else if (event.key === "ArrowDown" && items.length) {
      event.preventDefault();
      items[(index + 1) % items.length].focus();
    } else if (event.key === "ArrowUp" && items.length) {
      event.preventDefault();
      items[(index - 1 + items.length) % items.length].focus();
    }
  }

  const style = primary
    ? tone === "dark"
      ? "bg-[#8fb8ff] text-[#06213b] hover:bg-white"
      : "bg-human text-white hover:bg-human-ink"
    : tone === "dark"
      ? "border border-white/30 text-white hover:bg-white/10"
      : "border border-rule-strong bg-panel text-ink hover:bg-inset";

  return (
    <div ref={wrap} className="relative" onKeyDown={onKeyDown}>
      <button
        ref={trigger}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        onClick={() => setOpen((v) => !v)}
        className={`inline-flex min-h-11 items-center gap-1.5 rounded px-3 text-[13px] font-semibold sm:min-h-8 ${style}`}
      >
        {label}
        <span aria-hidden="true" className="text-[10px]">
          ▾
        </span>
      </button>
      {open ? (
        <div
          id={listId}
          role="menu"
          aria-label={label}
          onClick={() => setOpen(false)}
          className={`absolute z-40 mt-1 min-w-56 rounded border border-rule-strong bg-panel py-1 text-ink shadow-lg ${
            align === "right" ? "right-0" : "left-0"
          }`}
        >
          {children}
        </div>
      ) : null}
    </div>
  );
}

const ITEM = "block w-full px-3.5 py-2.5 text-left text-[13px] text-ink no-underline hover:bg-human-bg sm:py-2";

export function MenuItem({ href, onSelect, children }: { href?: string; onSelect?: () => void; children: ReactNode }) {
  if (href) {
    return (
      <Link role="menuitem" href={href} prefetch={false} className={ITEM}>
        {children}
      </Link>
    );
  }
  return (
    <button type="button" role="menuitem" onClick={onSelect} className={ITEM}>
      {children}
    </button>
  );
}
