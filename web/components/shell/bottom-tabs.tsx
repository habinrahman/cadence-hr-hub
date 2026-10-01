"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { MOBILE_TABS } from "./nav";

/** Phone navigation for the four daily destinations. Everything else is in the drawer. */
export function BottomTabs() {
  const path = usePathname();
  return (
    <nav
      aria-label="Primary (mobile)"
      className="fixed inset-x-0 bottom-0 z-30 border-t border-nav-line bg-nav pb-[env(safe-area-inset-bottom)] md:hidden"
    >
      <ul className="flex">
        {MOBILE_TABS.map((item) => {
          const active = item.match(path);
          return (
            <li key={item.href} className="flex-1">
              <Link
                href={item.href}
                prefetch={false}
                aria-current={active ? "page" : undefined}
                className={`flex min-h-14 items-center justify-center border-t-2 text-[12px] no-underline ${
                  active ? "border-[#8fb3ff] font-semibold text-white" : "border-transparent text-nav-ink"
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
