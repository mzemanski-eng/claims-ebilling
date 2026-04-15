"use client";

import type { InvoiceDetail, LineItemSupplierView } from "@/lib/types";

interface SupplierTimelineProps {
  invoice: InvoiceDetail;
  lines: LineItemSupplierView[];
}

function fmt(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function fmtMoney(val: string | null | undefined): string {
  if (!val) return "";
  const n = parseFloat(val);
  if (isNaN(n)) return "";
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

type StepVariant = "complete" | "active" | "warning" | "pending";

interface TimelineStep {
  id: string;
  label: string;
  subLabel?: string;
  timestamp?: string | null;
  variant: StepVariant;
}

function buildSteps(
  invoice: InvoiceDetail,
  lines: LineItemSupplierView[],
): TimelineStep[] {
  const allExceptions = lines.flatMap((li) => li.exceptions);
  const hasExceptions = allExceptions.length > 0;
  const hasResponse = allExceptions.some((e) => !!e.supplier_response);
  const resolvedExceptions = allExceptions.filter(
    (e) => e.status === "RESOLVED" || e.status === "WAIVED",
  );
  const hasResolution = resolvedExceptions.length > 0;
  const isApproved =
    invoice.status === "APPROVED" || invoice.status === "EXPORTED";
  const isExported = invoice.status === "EXPORTED";
  const isProcessed = !!invoice.processed_at;
  const isProcessing =
    invoice.status === "SUBMITTED" || invoice.status === "PROCESSING";

  const steps: TimelineStep[] = [];

  // ── Step 1: Submitted ────────────────────────────────────────────────────
  steps.push({
    id: "submitted",
    label: "Invoice Submitted",
    subLabel: invoice.invoice_number,
    timestamp: invoice.submitted_at,
    variant: "complete",
  });

  // ── Step 2: AI Processing ────────────────────────────────────────────────
  const lineCount = lines.length;
  const processedSubLabel = isProcessed
    ? lineCount > 0
      ? `${lineCount} line${lineCount !== 1 ? "s" : ""} reviewed`
      : "Processing complete"
    : isProcessing
      ? "Reviewing lines against contract…"
      : "Processing complete";

  steps.push({
    id: "processing",
    label: "AI Processing",
    subLabel: processedSubLabel,
    timestamp: invoice.processed_at,
    variant: isProcessed ? "complete" : isProcessing ? "active" : "complete",
  });

  // ── Step 3: Issues Detected (conditional) ───────────────────────────────
  if (hasExceptions) {
    const exceptedLines = new Set(
      allExceptions.map((e) => {
        // Find the line that owns this exception
        const ownerLine = lines.find((li) =>
          li.exceptions.some((le) => le.exception_id === e.exception_id),
        );
        return ownerLine?.id;
      }),
    ).size;

    // Earliest created_at across all exceptions
    const earliest = allExceptions
      .map((e) => e.created_at)
      .filter(Boolean)
      .sort()[0];

    const isReviewRequired = invoice.status === "REVIEW_REQUIRED";
    const resolvedCount = resolvedExceptions.length;

    steps.push({
      id: "issues",
      label: "Issues Detected",
      subLabel:
        resolvedCount > 0
          ? `${resolvedCount} of ${allExceptions.length} resolved`
          : `${allExceptions.length} issue${allExceptions.length !== 1 ? "s" : ""} flagged${exceptedLines > 0 ? ` across ${exceptedLines} line${exceptedLines !== 1 ? "s" : ""}` : ""}`,
      timestamp: earliest,
      variant: isReviewRequired ? "warning" : resolvedCount === allExceptions.length ? "complete" : "active",
    });
  }

  // ── Step 4: Your Response (conditional) ─────────────────────────────────
  if (hasResponse) {
    const responseCount = allExceptions.filter((e) => !!e.supplier_response).length;
    steps.push({
      id: "response",
      label: "Your Response",
      subLabel: `${responseCount} response${responseCount !== 1 ? "s" : ""} submitted`,
      timestamp: null, // response timestamp not stored on model
      variant: "complete",
    });
  }

  // ── Step 5: Carrier Decision (conditional) ───────────────────────────────
  if (hasResolution) {
    const latestResolved = resolvedExceptions
      .map((e) => e.resolved_at)
      .filter((d): d is string => !!d)
      .sort()
      .at(-1);

    steps.push({
      id: "decision",
      label: "Carrier Decision",
      subLabel: `${resolvedExceptions.length} of ${allExceptions.length} issue${allExceptions.length !== 1 ? "s" : ""} resolved`,
      timestamp: latestResolved,
      variant: resolvedExceptions.length === allExceptions.length ? "complete" : "active",
    });
  }

  // ── Step 6: Approved (conditional) ──────────────────────────────────────
  if (isApproved) {
    const payable = invoice.validation_summary?.total_payable;
    steps.push({
      id: "approved",
      label: "Approved for Payment",
      subLabel: payable ? `${fmtMoney(payable)} approved` : "Payment authorized",
      timestamp: null, // no explicit approved_at column; would need audit event
      variant: "complete",
    });
  }

  // ── Step 7: Payment Issued (conditional) ────────────────────────────────
  if (isExported) {
    steps.push({
      id: "exported",
      label: "Payment Issued",
      subLabel: "Exported to accounts payable",
      timestamp: invoice.updated_at ?? null,
      variant: "complete",
    });
  }

  // ── Trailing pending steps for incomplete invoices ───────────────────────
  if (!isApproved && !isExported && !isProcessing) {
    if (!hasExceptions) {
      // Clean invoice still awaiting carrier approval
      steps.push({
        id: "approved",
        label: "Approved for Payment",
        subLabel: "Awaiting carrier approval",
        timestamp: null,
        variant: "pending",
      });
    }
    steps.push({
      id: "exported",
      label: "Payment Issued",
      subLabel: "Pending",
      timestamp: null,
      variant: "pending",
    });
  }

  return steps;
}

const VARIANT_STYLES: Record<
  StepVariant,
  { circle: string; label: string; line: string }
> = {
  complete: {
    circle: "bg-green-500 text-white border-green-500",
    label: "text-gray-900",
    line: "bg-green-300",
  },
  active: {
    circle: "bg-blue-600 text-white border-blue-600 ring-2 ring-blue-200 ring-offset-1",
    label: "text-blue-900 font-semibold",
    line: "bg-gray-200",
  },
  warning: {
    circle: "bg-orange-500 text-white border-orange-500 ring-2 ring-orange-200 ring-offset-1",
    label: "text-orange-900 font-semibold",
    line: "bg-gray-200",
  },
  pending: {
    circle: "bg-white text-gray-300 border-gray-200",
    label: "text-gray-400",
    line: "bg-gray-200",
  },
};

function CircleIcon({ variant }: { variant: StepVariant }) {
  if (variant === "complete") {
    return (
      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
      </svg>
    );
  }
  if (variant === "warning") {
    return <span className="text-xs font-bold leading-none">!</span>;
  }
  if (variant === "active") {
    return (
      <span className="h-2 w-2 rounded-full bg-white block" />
    );
  }
  return null;
}

export function SupplierTimeline({ invoice, lines }: SupplierTimelineProps) {
  const steps = buildSteps(invoice, lines);

  return (
    <div className="rounded-xl border border-gray-200 bg-white px-5 py-4">
      <h2 className="mb-4 text-xs font-semibold uppercase tracking-wide text-gray-500">
        Invoice Progress
      </h2>
      <div className="relative">
        {steps.map((step, i) => {
          const isLast = i === steps.length - 1;
          const styles = VARIANT_STYLES[step.variant];
          return (
            <div key={step.id} className="flex gap-4">
              {/* Circle + connector line */}
              <div className="flex flex-col items-center">
                <div
                  className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 ${styles.circle}`}
                >
                  <CircleIcon variant={step.variant} />
                </div>
                {!isLast && (
                  <div className={`mt-1 w-0.5 flex-1 min-h-[24px] ${styles.line}`} />
                )}
              </div>

              {/* Step content */}
              <div className={`pb-5 ${isLast ? "" : ""}`}>
                <div className="flex items-baseline gap-3">
                  <span className={`text-sm ${styles.label}`}>{step.label}</span>
                  {step.timestamp && (
                    <span className="text-xs text-gray-400">{fmt(step.timestamp)}</span>
                  )}
                </div>
                {step.subLabel && (
                  <p className="mt-0.5 text-xs text-gray-500">{step.subLabel}</p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
