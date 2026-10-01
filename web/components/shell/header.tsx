"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useDeskCounts } from "@/lib/use-desk-counts";
import { Icon } from "@/components/ui/icons";
import { pageLabel } from "./nav";
import { GlobalSearch } from "./global-search";
import { NavDrawer } from "./sidebar";

export function Header() {
  const path = usePathname();
  const counts = useDeskCounts();
  const [drawer, setDrawer] = useState(false);
  const [mobileFind, setMobileFind] = useState(false);
  const find = useRef<HTMLInputElement>(null);
  const waiting = counts?.decisions ?? 0;

  // "/" jumps to the global search unless the user is typing somewhere.
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
    <header className="sticky top-0 z-30 border-b border-rule bg-panel">
      <div className="flex h-[60px] items-center gap-3 px-4 sm:px-8 lg:h-[70px] lg:px-11">
        <button
          type="button"
          className="-ml-2 inline-flex h-11 w-11 items-center justify-center rounded-[2px] text-ink hover:bg-inset lg:hidden"
          aria-label="Open navigation"
          aria-expanded={drawer}
          onClick={() => setDrawer(true)}
        >
          <Icon name="menu" />
        </button>

        <nav aria-label="Breadcrumb" className="min-w-0 flex-1 text-[14px]">
          <ol className="flex items-center gap-2 truncate">
            <li className="hidden text-mut sm:block">Workspace</li>
            <li aria-hidden="true" className="hidden text-mut sm:block">
              /
            </li>
            <li aria-current="page" className="truncate font-semibold text-ink">
              {pageLabel(path)}
            </li>
          </ol>
        </nav>

        <div className="hidden w-64 md:block">
          <GlobalSearch inputRef={find} />
        </div>

        <Link
          href="/queue"
          prefetch={false}
          aria-label={waiting > 0 ? `Review queue, ${waiting} decisions waiting` : "Review queue"}
          className="relative inline-flex h-11 w-11 items-center justify-center rounded-[2px] text-ink no-underline hover:bg-inset"
        >
          <Icon name="bell" size={19} />
          {waiting > 0 ? <span aria-hidden="true" className="absolute right-2.5 top-2.5 h-2 w-2 rounded-full bg-bad" /> : null}
        </Link>
        <button
          type="button"
          aria-label="Search candidates, roles, requests"
          aria-expanded={mobileFind}
          onClick={() => setMobileFind((v) => !v)}
          className="inline-flex h-11 w-11 items-center justify-center rounded-[2px] text-ink hover:bg-inset md:hidden"
        >
          <Icon name={mobileFind ? "close" : "search"} size={19} />
        </button>
      </div>
      {mobileFind ? (
        <div className="border-t border-rule px-4 py-3 md:hidden">
          <GlobalSearch autoFocus onDone={() => setMobileFind(false)} />
        </div>
      ) : null}
      <NavDrawer open={drawer} onClose={() => setDrawer(false)} />
    </header>
  );
}
