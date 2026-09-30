"use client";

import { useEffect } from "react";
import "./install";

/** Registers the service worker in production builds only, so development is never fighting a cached worker. */
export function SwRegister() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production" || !("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // Installability is a convenience. The app works without the worker.
    });
  }, []);
  return null;
}
