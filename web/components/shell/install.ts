"use client";

import { useSyncExternalStore } from "react";

type InstallEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: "accepted" | "dismissed" }> };

const DISMISS_KEY = "cadence.pwa.dismissed.v1";
export const DISMISS_TTL_MS = 30 * 24 * 60 * 60 * 1000;

let deferred: InstallEvent | null = null;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export function readDismissedAt(): number {
  try {
    const n = Number(window.localStorage.getItem(DISMISS_KEY));
    return Number.isFinite(n) ? n : 0;
  } catch {
    return 0;
  }
}

export function markDismissed() {
  try {
    window.localStorage.setItem(DISMISS_KEY, String(Date.now()));
  } catch {
    // Private mode or blocked storage: the banner simply will not remember.
  }
}

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferred = event as InstallEvent;
    emit();
  });
  window.addEventListener("appinstalled", () => {
    deferred = null;
    markDismissed();
    emit();
  });
}

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

export function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia?.("(display-mode: standalone)").matches || (window.navigator as { standalone?: boolean }).standalone === true;
}

/** Real Safari on iOS only: other iOS browsers use CriOS, FxiOS or EdgiOS and cannot install. */
export function isIosSafari(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent;
  return /iPad|iPhone|iPod/.test(ua) && /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS/.test(ua);
}

let helpOpen = false;
export const setInstallHelp = (open: boolean) => {
  helpOpen = open;
  emit();
};
export function useInstallHelp() {
  return useSyncExternalStore(
    subscribe,
    () => helpOpen,
    () => false,
  );
}

export function useInstallPrompt() {
  const canInstall = useSyncExternalStore(
    subscribe,
    () => deferred !== null,
    () => false,
  );
  return {
    canInstall,
    isIos: useSyncExternalStore(subscribe, isIosSafari, () => false),
    async install() {
      if (!deferred) return;
      const event = deferred;
      deferred = null;
      emit();
      try {
        await event.prompt();
        const choice = await event.userChoice;
        if (choice.outcome !== "accepted") markDismissed();
      } catch {
        // The browser refused to show the prompt. Nothing to recover.
      }
    },
  };
}
