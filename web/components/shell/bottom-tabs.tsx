"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { InstallLink } from "./install-banner";
import { PRIMARY_NAV, DESK_ITEMS } from "./nav";

/** Phone navigation. The Desk items (rare) live in a short row above the tabs' safe area on the Inbox only. */
export function BottomTabs() {
  const path = usePathname();
  return (
    <nav
      aria-label="Primary (mobile)"
      className="fixed inset-x-0 bottom-0 z-30 border-t border-rule-strong bg-panel pb-[env(safe-area-inset-bottom)] md:hidden"
    >
      <ul className="flex">
        {PRIMARY_NAV.map((item) => {
          const active = item.match(path);
          return (
            <li key={item.href} className="flex-1">
              <Link
                href={item.href}
                prefetch={false}
                aria-current={active ? "page" : undefined}
                className={`flex min-h-14 flex-col items-center justify-center gap-0.5 border-t-2 text-[12px] no-underline ${
                  active ? "border-human font-bold text-human-ink" : "border-transparent text-mut"
                }`}
              >
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

export function MobileDeskLinks() {
  return (
    <nav aria-label="Desk" className="mt-8 flex flex-wrap gap-x-4 gap-y-1 border-t border-rule pt-4 text-[13px] sm:hidden">
      {DESK_ITEMS.map((item) => (
        <Link key={item.href} href={item.href} prefetch={false} className="inline-flex min-h-11 items-center">
          {item.label}
        </Link>
      ))}
      <InstallLink />
    </nav>
  );
}
