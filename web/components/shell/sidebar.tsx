"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef } from "react";
import { useDeskCounts } from "@/lib/use-desk-counts";
import { Icon } from "@/components/ui/icons";
import { InstallLink } from "./install-banner";
import { NAV_GROUPS } from "./nav";

function Brand() {
  return (
    <Link href="/" prefetch={false} className="flex items-center gap-3 px-1 text-white no-underline">
      <span aria-hidden="true" className="inline-flex h-8 w-8 items-center justify-center border border-nav-ink/70 font-semibold">
        C
      </span>
      <span className="leading-tight">
        <span className="block text-[17px] font-semibold tracking-[0.06em]">CADENCE</span>
        <span className="block font-mono text-[11px] text-nav-mut">HR intelligence hub</span>
      </span>
    </Link>
  );
}

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const path = usePathname();
  const search = useSearchParams();
  const counts = useDeskCounts();
  return (
    <nav aria-label="Primary" className="flex-1 overflow-y-auto">
      {NAV_GROUPS.map((group) => (
        <div key={group.label} className="mt-7 first:mt-0">
          <p className="px-3 pb-2 font-mono text-[11px] uppercase tracking-[0.16em] text-nav-mut">{group.label}</p>
          <ul className="space-y-0.5">
            {group.items.map((item) => {
              const active = item.match(path);
              const badge = item.badge && counts ? (item.badge === "decisions" ? counts.decisions : counts.reports) : 0;
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    prefetch={false}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    className={`flex min-h-11 items-center gap-3 rounded-[2px] px-3 text-[14px] no-underline lg:min-h-10 ${
                      active ? "bg-nav-active text-white" : "text-nav-ink hover:bg-nav-2 hover:text-white"
                    }`}
                  >
                    <Icon name={item.icon} size={18} className={active ? "text-white" : "text-nav-mut"} />
                    <span className="flex-1">{item.label}</span>
                    {badge > 0 ? (
                      <span className="font-mono text-[12px] text-nav-ink">
                        <span className="sr-only">, </span>
                        {badge}
                        <span className="sr-only"> waiting</span>
                      </span>
                    ) : null}
                  </Link>
                  {active && item.children ? (
                    <ul className="mb-1 ml-9 space-y-0.5">
                      {item.children.map((child) => {
                        const current = child.match(path, search);
                        return (
                          <li key={child.href}>
                            <Link
                              href={child.href}
                              prefetch={false}
                              onClick={onNavigate}
                              aria-current={current ? "page" : undefined}
                              className={`flex min-h-9 items-center rounded-[2px] px-3 text-[13px] no-underline ${
                                current ? "text-white" : "text-nav-ink hover:text-white"
                              }`}
                            >
                              {child.label}
                            </Link>
                          </li>
                        );
                      })}
                    </ul>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function Footer() {
  return (
    <div className="mt-6 border-t border-nav-line pt-4 text-[12px] text-nav-mut">
      <p className="px-3">Cadence HR desk</p>
      <p className="px-3 font-mono text-[11px]">Internal workspace</p>
      <div className="px-3 [&_button]:min-h-9 [&_button]:text-nav-ink">
        <InstallLink />
      </div>
    </div>
  );
}

/** Desktop sidebar. Hidden below 1024 px, where the drawer takes over. */
export function Sidebar() {
  return (
    <aside className="sticky top-0 hidden h-dvh w-[248px] shrink-0 flex-col bg-nav px-4 py-6 lg:flex">
      <Brand />
      <div className="mt-8 flex min-h-0 flex-1 flex-col">
        <Suspense fallback={null}>
          <NavList />
        </Suspense>
        <Footer />
      </div>
    </aside>
  );
}

/** The same navigation in a drawer for tablets and phones. */
export function NavDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const path = usePathname();
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  useEffect(() => {
    onClose();
    // Close whenever the route changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);
  return (
    <dialog
      ref={ref}
      className="drawer-left"
      aria-label="Navigation"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === ref.current) onClose();
      }}
    >
      <div className="flex h-full flex-col px-4 py-5">
        <div className="flex items-center justify-between">
          <Brand />
          <button
            type="button"
            onClick={onClose}
            aria-label="Close navigation"
            className="inline-flex h-11 w-11 items-center justify-center rounded-[2px] text-nav-ink hover:bg-nav-2"
          >
            <Icon name="close" />
          </button>
        </div>
        <div className="mt-7 flex min-h-0 flex-1 flex-col">
          <Suspense fallback={null}>
            <NavList onNavigate={onClose} />
          </Suspense>
          <Footer />
        </div>
      </div>
    </dialog>
  );
}
