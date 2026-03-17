"use client";

/**
 * Lightweight toast notification system — no external dependencies.
 *
 * Usage:
 *   1. Wrap your layout with <ToastProvider>
 *   2. Call useToast() anywhere inside to get { toast }
 *   3. toast.success("Invoice approved") / toast.error("…") / toast.info("…")
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";

// ── Types ─────────────────────────────────────────────────────────────────────

type ToastVariant = "success" | "error" | "warning" | "info";

interface ToastItem {
  id: string;
  variant: ToastVariant;
  title: string;
  description?: string;
  /** ms before auto-dismiss (default 4000) */
  duration?: number;
  exiting?: boolean;
}

interface ToastApi {
  success: (title: string, description?: string) => void;
  error:   (title: string, description?: string) => void;
  warning: (title: string, description?: string) => void;
  info:    (title: string, description?: string) => void;
}

// ── Context ───────────────────────────────────────────────────────────────────

const ToastContext = createContext<ToastApi | null>(null);

// ── Styles per variant ────────────────────────────────────────────────────────

const VARIANT_CLASSES: Record<ToastVariant, { bar: string; icon: string; text: string }> = {
  success: {
    bar:  "bg-green-500",
    icon: "✓",
    text: "text-green-700",
  },
  error: {
    bar:  "bg-red-500",
    icon: "✕",
    text: "text-red-700",
  },
  warning: {
    bar:  "bg-amber-500",
    icon: "⚠",
    text: "text-amber-700",
  },
  info: {
    bar:  "bg-blue-500",
    icon: "ℹ",
    text: "text-blue-700",
  },
};

// ── Individual toast component ────────────────────────────────────────────────

function Toast({
  item,
  onDismiss,
}: {
  item: ToastItem;
  onDismiss: (id: string) => void;
}) {
  const vc = VARIANT_CLASSES[item.variant];

  return (
    <div
      className={`relative flex w-80 overflow-hidden rounded-xl border bg-white shadow-lg transition-all duration-300 ${
        item.exiting ? "translate-x-full opacity-0" : "translate-x-0 opacity-100"
      }`}
    >
      {/* Left accent bar */}
      <div className={`w-1 shrink-0 ${vc.bar}`} />

      {/* Content */}
      <div className="flex flex-1 items-start gap-3 px-4 py-3">
        <span className={`mt-0.5 text-sm font-bold ${vc.text}`}>{vc.icon}</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-gray-900 leading-snug">
            {item.title}
          </p>
          {item.description && (
            <p className="mt-0.5 text-xs text-gray-500 leading-snug">
              {item.description}
            </p>
          )}
        </div>
        <button
          onClick={() => onDismiss(item.id)}
          className="mt-0.5 shrink-0 text-gray-300 hover:text-gray-500 transition-colors text-xs"
          aria-label="Dismiss"
        >
          ✕
        </button>
      </div>
    </div>
  );
}

// ── Provider ──────────────────────────────────────────────────────────────────

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const timers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: string) => {
    // Start exit animation
    setToasts((prev) =>
      prev.map((t) => (t.id === id ? { ...t, exiting: true } : t)),
    );
    // Remove after animation completes
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 300);
  }, []);

  const add = useCallback(
    (variant: ToastVariant, title: string, description?: string, duration = 4000) => {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      setToasts((prev) => [{ id, variant, title, description, duration }, ...prev]);

      const timer = setTimeout(() => dismiss(id), duration);
      timers.current.set(id, timer);
    },
    [dismiss],
  );

  // Clean up timers on unmount
  useEffect(() => {
    const t = timers.current;
    return () => t.forEach((timer) => clearTimeout(timer));
  }, []);

  const api: ToastApi = {
    success: (title, description) => add("success", title, description),
    error:   (title, description) => add("error",   title, description),
    warning: (title, description) => add("warning", title, description),
    info:    (title, description) => add("info",    title, description),
  };

  return (
    <ToastContext.Provider value={api}>
      {children}
      {/* Toast stack — bottom-right, stacks upward */}
      <div
        className="fixed bottom-6 right-6 z-50 flex flex-col-reverse gap-2 pointer-events-none"
        aria-live="polite"
        aria-label="Notifications"
      >
        {toasts.map((item) => (
          <div key={item.id} className="pointer-events-auto">
            <Toast item={item} onDismiss={dismiss} />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return ctx;
}
