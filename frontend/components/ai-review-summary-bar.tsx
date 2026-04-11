/**
 * AiReviewSummaryBar
 *
 * Shows the AI recommendation breakdown for an invoice in REVIEW_REQUIRED or
 * PENDING_CARRIER_REVIEW state. Displays a count breakdown by recommended action
 * (reduce/waive, deny, reclassify, needs review) and an "Accept AI Recommendations"
 * primary button that calls the bulk-resolve endpoint.
 *
 * Renders nothing when:
 * - Invoice is not in a reviewable status
 * - There are no open billing exceptions
 * - No exceptions have an AI recommendation (AI hasn't processed yet)
 */
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { acceptAiRecommendations } from "@/lib/api";
import type { LineItemCarrierView } from "@/lib/types";

interface AiReviewSummaryBarProps {
  invoiceId: string;
  invoiceStatus: string;
  lines: LineItemCarrierView[];
  /** Query keys to invalidate after bulk accept */
  invalidateKeys: string[][];
  /** If false, the Accept button is hidden (reviewer can see breakdown but not act) */
  canAct?: boolean;
}

const REVIEWABLE_STATUSES = new Set(["REVIEW_REQUIRED", "PENDING_CARRIER_REVIEW"]);

const REDUCE_ACTIONS = new Set(["WAIVED", "HELD_CONTRACT_RATE", "ACCEPTED_REDUCTION"]);
const DENY_ACTIONS = new Set(["DENIED"]);
const RECLASSIFY_ACTIONS = new Set(["RECLASSIFIED"]);

const CHIP_STYLES = {
  reduce: "border-amber-200 bg-amber-50 text-amber-800",
  deny: "border-red-200 bg-red-50 text-red-800",
  reclassify: "border-purple-200 bg-purple-50 text-purple-800",
  noRec: "border-gray-200 bg-gray-50 text-gray-500",
} as const;

export function AiReviewSummaryBar({
  invoiceId,
  invoiceStatus,
  lines,
  invalidateKeys,
  canAct = true,
}: AiReviewSummaryBarProps) {
  const queryClient = useQueryClient();

  // Collect all active billing exceptions across all lines
  const openBillingExcs = lines.flatMap((li) =>
    (li.exceptions ?? []).filter(
      (e) =>
        (e.status === "OPEN" ||
          e.status === "SUPPLIER_RESPONDED" ||
          e.status === "CARRIER_REVIEWING") &&
        e.required_action !== "REQUEST_RECLASSIFICATION",
    ),
  );

  // Only render for invoices that need human review
  if (!REVIEWABLE_STATUSES.has(invoiceStatus)) return null;
  if (openBillingExcs.length === 0) return null;

  // Bucket exceptions by AI recommendation
  const reduce = openBillingExcs.filter(
    (e) => e.ai_recommendation && REDUCE_ACTIONS.has(e.ai_recommendation),
  );
  const deny = openBillingExcs.filter(
    (e) => e.ai_recommendation && DENY_ACTIONS.has(e.ai_recommendation),
  );
  const reclassify = openBillingExcs.filter(
    (e) => e.ai_recommendation && RECLASSIFY_ACTIONS.has(e.ai_recommendation),
  );
  const noRec = openBillingExcs.filter((e) => !e.ai_recommendation);

  const readyCount = openBillingExcs.length - noRec.length;

  // Don't render if AI has no recommendations for any exception
  if (readyCount === 0) return null;

  const mutation = useMutation({
    mutationFn: () => acceptAiRecommendations(invoiceId),
    onSuccess: () => {
      invalidateKeys.forEach((key) =>
        queryClient.invalidateQueries({ queryKey: key }),
      );
    },
  });

  const chips: Array<{ count: number; label: string; style: string }> = [
    { count: reduce.length, label: "Reduce / Waive", style: CHIP_STYLES.reduce },
    { count: deny.length, label: "Deny", style: CHIP_STYLES.deny },
    { count: reclassify.length, label: "Reclassify", style: CHIP_STYLES.reclassify },
    { count: noRec.length, label: "Needs review", style: CHIP_STYLES.noRec },
  ].filter((c) => c.count > 0);

  return (
    <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 mb-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Left: summary */}
        <div className="flex flex-col gap-1.5">
          <p className="text-sm font-semibold text-blue-900">
            AI Review &mdash;{" "}
            {readyCount === openBillingExcs.length
              ? `AI has recommendations for all ${openBillingExcs.length} exception${openBillingExcs.length !== 1 ? "s" : ""}`
              : `${readyCount} of ${openBillingExcs.length} exceptions have AI recommendations`}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {chips.map(({ count, label, style }) => (
              <span
                key={label}
                className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap ${style}`}
              >
                {count} {label}
              </span>
            ))}
          </div>
        </div>

        {/* Right: action button (only for users with write access) */}
        {canAct ? (
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || mutation.isSuccess}
            className="shrink-0 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 active:bg-blue-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {mutation.isPending
              ? "Applying…"
              : mutation.isSuccess
                ? "Applied"
                : `Accept ${readyCount} AI Recommendation${readyCount !== 1 ? "s" : ""}`}
          </button>
        ) : (
          <span className="text-xs text-blue-500 italic shrink-0">
            Carrier Admin required to apply
          </span>
        )}
      </div>

      {/* Feedback messages */}
      {mutation.isSuccess && (
        <p className="mt-2 text-xs text-blue-700">{mutation.data?.message}</p>
      )}
      {mutation.isError && (
        <p className="mt-2 text-xs text-red-600">
          Failed to apply recommendations. Please try again.
        </p>
      )}
    </div>
  );
}
