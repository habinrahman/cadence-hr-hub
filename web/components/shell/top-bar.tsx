"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { getDashboard } from "@/lib/api";
import { Menu, MenuItem } from "@/components/ui/menu";
import { InstallMenuItem } from "./install-banner";
import { ADD_ITEMS, DESK_ITEMS, PRIMARY_NAV } from "./nav";

/** Decisions waiting for a person. A failed call shows no badge rather than a wrong one. */
export function useInboxCount(): number | null {
  const [count, setCount] = useState<number | null>(null);
  const path = usePathname();
  useEffect(() => {
    let cancelled = false;
    getDashboard()
      .then((d) => {
        if (cancelled) return;
        const c = d.counts;
        setCount(
          c.relationship_reviews + c.requirements_awaiting_approval + c.matches_awaiting_review + c.shares_awaiting_approval,
        );
      })
      .catch(() => {
        if (!cancelled) setCount(null);
      });
    return () => {
      cancelled = true;
    };
  }, [path]);
  return count;
}

export function TopBar() {
  const path = usePathname();
  const count = useInboxCount();
  const find = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const el = document.activeElement as HTMLElement | null;
      const typing = el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);
      if (event.key === "/" && !typing && !event.metaKey && !event.ctrlKey) {
        event.preventDefault();
        find.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <header className="bg-nav text-white">
      <div className="mx-auto flex h-12 max-w-[1200px] items-center gap-3 px-4 sm:px-6 lg:gap-5">
        <Link href="/" prefetch={false} className="flex items-center gap-2 font-bold text-white no-underline">
          <span
            aria-hidden="true"
            className="inline-block h-3 w-3 rounded-[3px] bg-gradient-to-br from-t-rel to-t-match"
          />
          Cadence <span className="font-medium text-nav-ink">HR</span>
        </Link>

        <nav aria-label="Primary" className="hidden h-full items-stretch gap-4 md:flex">
          {PRIMARY_NAV.map((item) => {
            const active = item.match(path);
            return (
              <Link
                key={item.href}
                href={item.href}
                prefetch={false}
                aria-current={active ? "page" : undefined}
                className={`flex items-center border-b-2 px-0.5 text-[14px] no-underline ${
                  active ? "border-[#8fb8ff] font-semibold text-white" : "border-transparent text-nav-ink hover:text-white"
                }`}
              >
                {item.label}
                {item.href === "/" && count !== null && count > 0 ? (
                  <span className="ml-1.5 rounded-full bg-[#ffb454] px-1.5 text-[11px] font-bold text-[#2b1700]">
                    <span className="sr-only">{count} waiting: </span>
                    {count}
                  </span>
                ) : null}
              </Link>
            );
          })}
        </nav>

        <div className="flex-1" />

        <form action="/candidates" method="get" role="search" className="hidden lg:block">
          <label htmlFor="global-find" className="sr-only">
            Find a candidate
          </label>
          <input
            ref={find}
            id="global-find"
            name="q"
            type="search"
            placeholder="Find a candidate…  /"
            className="h-8 w-56 rounded border border-white/25 bg-white/10 px-2.5 text-[13px] text-white placeholder:text-nav-ink"
          />
        </form>

        <Menu label="+ Add" tone="dark" primary align="right">
          {ADD_ITEMS.map((item) => (
            <MenuItem key={item.href} href={item.href}>
              {item.label}
            </MenuItem>
          ))}
        </Menu>
        <div className="hidden sm:block">
          <Menu label="Desk" tone="dark" align="right">
            {DESK_ITEMS.map((item) => (
              <MenuItem key={item.href} href={item.href}>
                {item.label}
              </MenuItem>
            ))}
            <InstallMenuItem />
          </Menu>
        </div>
      </div>
    </header>
  );
}
