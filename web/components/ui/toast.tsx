"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

type Tone = "ok" | "bad";
type Ctx = { notify: (message: string, tone?: Tone) => void };

const ToastContext = createContext<Ctx>({ notify: () => {} });

export function useToast() {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<{ message: string; tone: Tone; id: number } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const notify = useCallback((message: string, tone: Tone = "ok") => {
    if (timer.current) clearTimeout(timer.current);
    setToast({ message, tone, id: Date.now() });
    timer.current = setTimeout(() => setToast(null), 6000);
  }, []);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  return (
    <ToastContext.Provider value={{ notify }}>
      {children}
      <div role="status" aria-live="polite" className="pointer-events-none fixed inset-x-3 bottom-20 z-50 flex justify-center md:bottom-6">
        {toast ? (
          <p
            key={toast.id}
            className={`pointer-events-auto max-w-md rounded border px-4 py-2.5 text-[13px] font-semibold shadow-lg ${
              toast.tone === "ok" ? "border-ok-ink bg-ok-ink text-white" : "border-bad-ink bg-bad-ink text-white"
            }`}
          >
            {toast.message}
          </p>
        ) : null}
      </div>
    </ToastContext.Provider>
  );
}
