"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import {
  DISMISS_TTL_MS,
  isStandalone,
  markDismissed,
  readDismissedAt,
  setInstallHelp,
  useInstallHelp,
  useInstallPrompt,
} from "./install";

const SHOW_DELAY_MS = 15_000;

export function InstallBanner() {
  const { canInstall, isIos, install } = useInstallPrompt();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (isStandalone()) return;
    if (!window.matchMedia("(max-width: 1024px)").matches) return;
    const dismissedAt = readDismissedAt();
    if (dismissedAt && Date.now() - dismissedAt < DISMISS_TTL_MS) return;
    if (!canInstall && !isIos) return;
    const timer = setTimeout(() => setVisible(true), SHOW_DELAY_MS);
    return () => clearTimeout(timer);
  }, [canInstall, isIos]);

  const dismiss = useCallback(() => {
    setVisible(false);
    markDismissed();
  }, []);

  if (!visible || (!canInstall && !isIos)) return null;
  return (
    <section
      aria-label="Install Cadence"
      className="fixed inset-x-3 bottom-[4.75rem] z-40 rounded border border-rule-strong bg-panel p-3 shadow-lg md:bottom-4 md:left-auto md:right-4 md:max-w-sm"
    >
      <p className="font-bold">Install Cadence</p>
      {canInstall ? (
        <p className="text-mut">Open the desk from your home screen, in its own window.</p>
      ) : (
        <p className="text-mut">
          Tap the Share button, then <strong className="text-ink">Add to Home Screen</strong>.
        </p>
      )}
      <div className="mt-2 flex flex-wrap gap-2">
        {canInstall ? (
          <Button
            variant="primary"
            onClick={async () => {
              setVisible(false);
              await install();
            }}
          >
            Install
          </Button>
        ) : null}
        <Button variant="quiet" onClick={dismiss}>
          Not now
        </Button>
      </div>
    </section>
  );
}

/** The iOS steps live here, outside any menu, so closing a menu cannot dismiss them. */
export function InstallHelp() {
  const open = useInstallHelp();
  return (
    <ConfirmDialog
      open={open}
      title="Install on this device"
      body={
        <p>
          In Safari, tap the <strong>Share</strong> button, then choose <strong>Add to Home Screen</strong>.
        </p>
      }
      confirmLabel="Got it"
      onConfirm={() => setInstallHelp(false)}
      onCancel={() => setInstallHelp(false)}
    />
  );
}

function useInstallAction() {
  const { canInstall, isIos, install } = useInstallPrompt();
  const available = !isStandalone() && (canInstall || isIos);
  return { available, run: () => (canInstall ? void install() : setInstallHelp(true)) };
}

export function InstallLink() {
  const { available, run } = useInstallAction();
  if (!available) return null;
  return (
    <button type="button" onClick={run} className="inline-flex min-h-11 items-center text-[13px] font-semibold text-human-ink underline">
      Install app
    </button>
  );
}
