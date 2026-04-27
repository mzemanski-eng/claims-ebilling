"use client";

import { useState, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  approveCarrierInvoice,
  downloadBlob,
  exportCarrierInvoice,
  getCarrierInvoice,
  getCarrierInvoiceLines,
  requestInvoiceChanges,
} from "@/lib/api";
import { isCarrierAdmin } from "@/lib/auth";
import type { LineItemCarrierView } from "@/lib/types";
import { StatusBadge } from "@/components/status-badge";
import { ValidationSummaryCard } from "@/components/validation-summary-card";
import { CarrierExceptionPanel } from "@/components/exception-panel";
import { AiAssessmentBadge } from "@/components/ai-assessment-badge";
import { AiReviewSummaryBar } from "@/components/ai-review-summary-bar";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/** Compact age label for an ISO timestamp — "today", "3d ago", "2w ago". */
function formatAge(iso: string | null): string | null {
  if (!iso) return null;
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "1d ago";
  if (days < 14) return `${days}d ago`;
  return `${Math.floor(days / 7)}w ago`;
}

/** Normalise raw_unit to a short readable label (hr, ea, day, …). */
function normaliseUnit(unit: string | null): string {
  if (!unit) return "";
  const u = unit.trim().toLowerCase();
  if (/^hours?$/.test(u) || u === "hr" || u === "hrs") return "hr";
  if (u === "days" || u === "day") return "day";
  if (u === "ea" || u === "each") return "ea";
  if (u === "flat" || u === "flat fee") return "flat";
  return u;
}

/** Display quantity + unit together: "8 hr", "1 ea", "2.5 day" */
function formatQty(quantity: string, unit: string | null): string {
  const q = parseFloat(quantity);
  const qStr = Number.isInteger(q) ? String(q) : q.toFixed(2);
  const u = normaliseUnit(unit);
  return u ? `${qStr} ${u}` : qStr;
}

/** Billing breakdown panel shown in the expanded row. */
function BillingBreakdown({ line }: { line: LineItemCarrierView }) {
  const qty = parseFloat(line.raw_quantity);
  const billed = parseFloat(line.raw_amount);
  const expected = line.expected_amount ? parseFloat(line.expected_amount) : null;
  const contractedRate = line.mapped_rate ? parseFloat(line.mapped_rate) : null;
  const unit = normaliseUnit(line.raw_unit);

  // Per-unit rate the supplier charged
  const billedRate = qty > 0 && qty !== 1 ? billed / qty : null;

  const delta = expected !== null ? billed - expected : null;
  const hasVariance = delta !== null && Math.abs(delta) > 0.005;

  return (
    <div className="rounded-lg border border-gray-200 bg-white px-4 py-3">
      <p className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-gray-400">
        Billing Breakdown
      </p>
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1 text-sm">
        {/* Quantity */}
        <span className="text-gray-700">
          <span className="font-medium text-gray-900">{formatQty(line.raw_quantity, line.raw_unit)}</span>
          <span className="ml-1 text-xs text-gray-400">billed</span>
        </span>

        {/* Rates — only when qty > 1 (time / unit billing) */}
        {billedRate !== null && (
          <span className="text-gray-700">
            <span className="font-medium text-gray-900">${billedRate.toFixed(2)}</span>
            <span className="ml-0.5 text-xs text-gray-400">/{unit || "unit"} billed</span>
          </span>
        )}
        {contractedRate !== null && (
          <span className="text-gray-700">
            <span className="font-medium text-gray-900">${contractedRate.toFixed(2)}</span>
            <span className="ml-0.5 text-xs text-gray-400">/{unit || "unit"} contracted</span>
          </span>
        )}

        {/* Totals */}
        <span className="text-gray-700">
          <span className="font-medium text-gray-900">${billed.toFixed(2)}</span>
          <span className="ml-1 text-xs text-gray-400">billed total</span>
        </span>
        {expected !== null && (
          <span className="text-gray-700">
            <span className="font-medium text-gray-900">${expected.toFixed(2)}</span>
            <span className="ml-1 text-xs text-gray-400">expected</span>
          </span>
        )}

        {/* Variance */}
        {hasVariance && (
          <span
            className={`font-semibold ${delta! > 0 ? "text-red-600" : "text-green-600"}`}
          >
            {delta! > 0 ? "+" : ""}${delta!.toFixed(2)} variance
          </span>
        )}
      </div>
    </div>
  );
}

export default function CarrierInvoiceReviewPage({
  params,
}: {
  params: { id: string };
}) {
  const { id } = params;
  const router = useRouter();
  const queryClient = useQueryClient();

  const [showChangesDialog, setShowChangesDialog] = useState(false);
  const [carrierNotes, setCarrierNotes] = useState("");
  const [approvalNotes, setApprovalNotes] = useState("");
  const [showApproveConfirm, setShowApproveConfirm] = useState(false);
  const [expandedLines, setExpandedLines] = useState<Set<string>>(new Set());
  const [showIssuesOnly, setShowIssuesOnly] = useState(false);
  const lineItemsRef = useRef<HTMLDivElement>(null);

  const { data: invoice, isLoading: invLoading } = useQuery({
    queryKey: ["carrier-invoice", id],
    queryFn: () => getCarrierInvoice(id),
  });

  const { data: lines, isLoading: linesLoading } = useQuery({
    queryKey: ["carrier-lines", id],
    queryFn: () => getCarrierInvoiceLines(id),
    enabled: !!invoice,
  });

  const approveMutation = useMutation({
    mutationFn: () => approveCarrierInvoice(id, approvalNotes || undefined),
    onSuccess: () => {
      setShowApproveConfirm(false);
      void queryClient.invalidateQueries({ queryKey: ["carrier-queue"] });
      router.push("/carrier/queue");
    },
  });

  const changesMutation = useMutation({
    mutationFn: () => requestInvoiceChanges(id, carrierNotes),
    onSuccess: () => {
      setShowChangesDialog(false);
      setCarrierNotes("");
      void queryClient.invalidateQueries({ queryKey: ["carrier-queue"] });
      router.push("/carrier/queue");
    },
  });

  const exportMutation = useMutation({
    mutationFn: () => exportCarrierInvoice(id),
    onSuccess: (blob) => {
      downloadBlob(blob, `approved_${invoice?.invoice_number ?? id}.csv`);
      void queryClient.invalidateQueries({ queryKey: ["carrier-queue"] });
    },
  });

  function toggleLine(lineId: string) {
    setExpandedLines((prev) => {
      const next = new Set(prev);
      next.has(lineId) ? next.delete(lineId) : next.add(lineId);
      return next;
    });
  }

  if (invLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
      </div>
    );
  }

  if (!invoice) {
    return <p className="text-red-600">Invoice not found.</p>;
  }

  const canApprove =
    isCarrierAdmin() &&
    (invoice.status === "PENDING_CARRIER_REVIEW" ||
      invoice.status === "CARRIER_REVIEWING" ||
      invoice.status === "REVIEW_REQUIRED" ||
      invoice.status === "SUPPLIER_RESPONDED");

  const canExport = invoice.status === "APPROVED";

  // Count LINES with at least one open billing exception — matches Validation Summary's
  // "Exceptions" number. Excludes REQUEST_RECLASSIFICATION (classification queue items).
  const openExceptionCount = lines
    ? lines.filter((li) =>
        li.exceptions.some(
          (e) =>
            e.status === "OPEN" &&
            e.required_action !== "REQUEST_RECLASSIFICATION",
        ),
      ).length
    : 0;

  // All lines — classification-pending ones render as de-emphasized rows so the
  // reviewer can see which lines are held up without acting on them here.
  const auditLines = lines ?? [];
  const pendingCount = lines
    ? lines.filter((li) => li.status === "CLASSIFICATION_PENDING").length
    : 0;

  // Lines with at least one open exception — used for the "issues only" filter
  const issueLines = auditLines.filter((li) =>
    li.exceptions.some(
      (e) => e.status === "OPEN" || e.status === "SUPPLIER_RESPONDED",
    ),
  );
  const displayedLines = showIssuesOnly ? issueLines : auditLines;

  function jumpToIssues() {
    setShowIssuesOnly(true);
    // Don't auto-expand — let the user click individual rows to review.
    setTimeout(
      () => lineItemsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
      50,
    );
  }

  return (
    <div className="space-y-8">
      {/* Breadcrumb */}
      <div className="text-sm text-gray-500">
        <Link href="/carrier/queue" className="hover:text-blue-600">
          Action Required
        </Link>
        <span className="mx-2">›</span>
        <span className="text-gray-900 font-medium">
          {invoice.invoice_number}
        </span>
      </div>

      {/* Sticky action bar */}
      {(() => {
        // Determine which workflow strip to show — the Approve button lives
        // inside the strip so the context and action are on the same line.
        const hasWorkflowStrip =
          (invoice.status === "REVIEW_REQUIRED" && openExceptionCount > 0) ||
          invoice.status === "SUPPLIER_RESPONDED" ||
          (invoice.status === "PENDING_CARRIER_REVIEW" && openExceptionCount === 0);

        const approveButton = canApprove ? (
          <Button onClick={() => setShowApproveConfirm(true)}>
            ✓ Approve Invoice
          </Button>
        ) : null;

        return (
          <div className="sticky top-0 z-10 -mx-4 border-b bg-white px-4 shadow-sm sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
            <div className="flex flex-wrap items-center justify-between gap-4 py-3">
              <div className="flex items-center gap-3">
                <h1 className="text-xl font-bold text-gray-900">
                  {invoice.invoice_number}
                </h1>
                <StatusBadge status={invoice.status} className="text-sm" />
                {openExceptionCount > 0 && (
                  <button
                    onClick={jumpToIssues}
                    title="Jump to open exceptions"
                    className="rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-bold text-red-700 hover:bg-red-200 transition-colors cursor-pointer"
                  >
                    {openExceptionCount} open exception
                    {openExceptionCount > 1 ? "s" : ""} ↓
                  </button>
                )}
                {formatAge(invoice.submitted_at) && (
                  <span
                    className="text-xs text-gray-400"
                    title={`Submitted ${formatDate(invoice.submitted_at)}`}
                  >
                    Submitted {formatAge(invoice.submitted_at)}
                  </span>
                )}
              </div>

              <div className="flex items-center gap-2">
                {canExport && (
                  <Button
                    variant="secondary"
                    loading={exportMutation.isPending}
                    onClick={() => exportMutation.mutate()}
                  >
                    ↓ Export CSV
                  </Button>
                )}
                {canApprove && (
                  <>
                    {/* Hide "Request Changes" when already in REVIEW_REQUIRED — supplier was
                        auto-notified. Show it in other actionable statuses. */}
                    {invoice.status !== "REVIEW_REQUIRED" && (
                      <Button
                        variant="secondary"
                        onClick={() => setShowChangesDialog(true)}
                      >
                        Request Changes
                      </Button>
                    )}
                    {/* Approve button stays in the top row only when there's no
                        workflow strip below to hold it */}
                    {!hasWorkflowStrip && approveButton}
                  </>
                )}
                {!canApprove && !canExport && invoice.status !== "APPROVED" && (
                  <span className="rounded-md border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs text-gray-500">
                    {isCarrierAdmin()
                      ? "Not yet ready to approve"
                      : "View only — Carrier Admin required to approve"}
                  </span>
                )}
              </div>
            </div>
            {/* Inline workflow context — Approve button sits on the same line */}
            {invoice.status === "REVIEW_REQUIRED" && openExceptionCount > 0 && (
              <div className="flex items-center gap-3 border-t border-orange-200 bg-orange-50 -mx-4 px-4 py-2 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
                <span className="text-orange-500 text-sm">⏳</span>
                <p className="flex-1 text-xs font-medium text-orange-800">
                  Awaiting supplier response — approving now will waive all disputed charges
                </p>
                {approveButton}
              </div>
            )}
            {invoice.status === "SUPPLIER_RESPONDED" && (
              <div className="flex items-center gap-3 border-t border-indigo-200 bg-indigo-50 -mx-4 px-4 py-2 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
                <span className="text-indigo-500 text-sm">💬</span>
                <p className="flex-1 text-xs font-medium text-indigo-800">
                  Supplier has replied — review their responses before approving
                </p>
                {approveButton}
              </div>
            )}
            {invoice.status === "PENDING_CARRIER_REVIEW" && openExceptionCount === 0 && (
              <div className="flex items-center gap-3 border-t border-green-200 bg-green-50 -mx-4 px-4 py-2 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
                <span className="text-green-500 text-sm">✓</span>
                <p className="flex-1 text-xs font-medium text-green-800">
                  All exceptions resolved — ready for approval
                </p>
                {approveButton}
              </div>
            )}
          </div>
        );
      })()}

      {/* Invoice meta */}
      <div className="flex flex-wrap gap-6 text-sm text-gray-600">
        <span>Invoice date: <strong>{formatDate(invoice.invoice_date)}</strong></span>
        <span>Version: <strong>{invoice.current_version}</strong></span>
        {invoice.submission_notes && (
          <span className="italic text-gray-400">
            Note: {invoice.submission_notes}
          </span>
        )}
      </div>

      {/* Validation summary */}
      {invoice.validation_summary && (
        <div>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Validation Summary
          </h2>
          <ValidationSummaryCard
            summary={invoice.validation_summary}
            invoiceStatus={invoice.status}
          />
        </div>
      )}

      {/* PENDING_CARRIER_REVIEW with open exceptions — detail guidance below summary */}
      {invoice.status === "PENDING_CARRIER_REVIEW" && openExceptionCount > 0 && (
        <div className="rounded-lg border border-purple-200 bg-purple-50 px-5 py-4">
          <p className="text-sm font-semibold text-purple-800">
            Carrier Review Required
          </p>
          <p className="mt-1 text-sm text-purple-700">
            {openExceptionCount} exception{openExceptionCount !== 1 ? "s" : ""} need
            your attention. Expand each flagged line to resolve, or approve the invoice
            to waive all remaining exceptions.
          </p>
        </div>
      )}

      {/* Classification pending — link filtered to this invoice */}
      {pendingCount > 0 && (
        <p className="text-xs text-gray-400">
          {pendingCount} line{pendingCount !== 1 ? "s" : ""} awaiting taxonomy
          classification —{" "}
          <Link
            href={`/carrier/classification?invoice_id=${id}&invoice_number=${encodeURIComponent(invoice.invoice_number)}`}
            className="text-blue-500 hover:underline"
          >
            review in Classification Queue →
          </Link>
        </p>
      )}

      {/* AI review summary — shown to all carrier users; accept button only for admins */}
      {lines && invoice && (
        <AiReviewSummaryBar
          invoiceId={id}
          invoiceStatus={invoice.status}
          lines={lines}
          canAct={isCarrierAdmin()}
          invalidateKeys={[
            ["carrier-invoice", id],
            ["carrier-lines", id],
          ]}
        />
      )}

      {/* Line items */}
      {linesLoading && (
        <div className="flex items-center justify-center py-10">
          <div className="h-6 w-6 animate-spin rounded-full border-4 border-blue-400 border-t-transparent" />
        </div>
      )}

      {lines && (
        <div ref={lineItemsRef}>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
              Line Items ({displayedLines.length}
              {showIssuesOnly && ` of ${auditLines.length}`})
            </h2>
            {openExceptionCount > 0 && (
              <button
                onClick={() => {
                  if (showIssuesOnly) {
                    setShowIssuesOnly(false);
                  } else {
                    jumpToIssues();
                  }
                }}
                className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${
                  showIssuesOnly
                    ? "border-red-200 bg-red-50 text-red-700 hover:bg-red-100"
                    : "border-gray-200 bg-white text-gray-500 hover:bg-gray-50"
                }`}
              >
                {showIssuesOnly ? (
                  <>✕ Show all lines</>
                ) : (
                  <><span className="text-red-500">●</span> Show {openExceptionCount} issue{openExceptionCount !== 1 ? "s" : ""} only</>
                )}
              </button>
            )}
          </div>
          <div className="overflow-hidden rounded-xl border bg-white shadow-sm">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left font-semibold text-gray-600">#</th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-600">Description</th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-600">Taxonomy</th>
                  <th className="px-4 py-3 text-right font-semibold text-gray-600">Qty</th>
                  <th className="px-4 py-3 text-right font-semibold text-gray-600">Billed</th>
                  <th className="px-4 py-3 text-right font-semibold text-gray-600">Expected</th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-600">Status</th>
                  <th className="px-4 py-3 text-center font-semibold text-gray-600">Exc.</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {displayedLines.map((li) => {
                  const isPending = li.status === "CLASSIFICATION_PENDING";
                  const openExcs = li.exceptions.filter((e) => e.status === "OPEN" || e.status === "SUPPLIER_RESPONDED");
                  const expanded = expandedLines.has(li.id);
                  const hasExceptions = li.exceptions.length > 0;
                  // Derive a workflow-aware display status:
                  //   - All exceptions resolved/waived → "Resolved" (teal)
                  //   - Supplier has responded to at least one → "Supplier Replied" (indigo)
                  //   - Open exceptions, no supplier response → "Billing Issue" (red)
                  const displayStatus = (() => {
                    if (li.status === "APPROVED" || li.status === "VALIDATED") return li.status;
                    if (li.status !== "EXCEPTION") return li.status;
                    if (openExcs.length === 0) return "RESOLVED";
                    if (openExcs.some((e) => e.status === "SUPPLIER_RESPONDED")) return "SUPPLIER_RESPONDED";
                    return li.status;
                  })();

                  // ── Classification-pending row — de-emphasised, not actionable ──
                  if (isPending) {
                    return (
                      <tr key={li.id} className="opacity-50">
                        <td className="px-4 py-3 text-gray-400">{li.line_number}</td>
                        <td className="px-4 py-3 max-w-xs">
                          <span className="block truncate text-gray-400 italic" title={li.raw_description}>
                            {li.raw_description}
                          </span>
                          {li.claim_number && (
                            <span className="text-xs text-gray-300">{li.claim_number}</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <Link
                            href={`/carrier/classification?invoice_id=${id}&invoice_number=${encodeURIComponent(invoice.invoice_number)}`}
                            className="inline-flex items-center gap-1 rounded-md border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700 hover:bg-amber-100 transition-colors"
                            onClick={(e) => e.stopPropagation()}
                          >
                            Awaiting classification →
                          </Link>
                        </td>
                        <td className="px-4 py-3 text-right text-gray-300">—</td>
                        <td className="px-4 py-3 text-right font-mono text-gray-400">
                          ${parseFloat(li.raw_amount).toFixed(2)}
                        </td>
                        <td className="px-4 py-3 text-right text-gray-300">—</td>
                        <td className="px-4 py-3 text-gray-300 text-xs italic">Pending</td>
                        <td className="px-4 py-3" />
                      </tr>
                    );
                  }

                  // ── Standard billing line ──────────────────────────────────────
                  return (
                    <>
                      <tr
                        key={li.id}
                        className={`${
                          openExcs.length > 0
                            ? "bg-red-50"
                            : "hover:bg-gray-50"
                        } ${hasExceptions ? "cursor-pointer" : ""} transition-colors`}
                        onClick={() => hasExceptions && toggleLine(li.id)}
                      >
                        <td className="px-4 py-3 text-gray-500">{li.line_number}</td>
                        <td className="px-4 py-3 max-w-xs">
                          <span
                            className="block truncate text-gray-900"
                            title={li.raw_description}
                          >
                            {li.raw_description}
                          </span>
                          {li.claim_number && (
                            <span className="text-xs text-gray-400">
                              {li.claim_number}
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <span className="font-mono text-xs text-gray-600">
                            {li.taxonomy_code ?? <span className="text-gray-300">—</span>}
                          </span>
                          {li.taxonomy_label && li.taxonomy_label !== li.taxonomy_code && (
                            <span className="block text-xs text-gray-400 truncate max-w-[180px]" title={li.taxonomy_label}>
                              {li.taxonomy_label}
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-gray-600 whitespace-nowrap">
                          {formatQty(li.raw_quantity, li.raw_unit)}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-gray-900">
                          ${parseFloat(li.raw_amount).toFixed(2)}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-gray-500">
                          {li.expected_amount
                            ? `$${parseFloat(li.expected_amount).toFixed(2)}`
                            : "—"}
                        </td>
                        <td className="px-4 py-3">
                          <StatusBadge status={displayStatus} />
                        </td>
                        <td className="px-4 py-3 text-center">
                          {openExcs.length > 0 ? (
                            <span className="inline-flex items-center gap-1">
                              <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-red-100 text-xs font-bold text-red-700">
                                {openExcs.length}
                              </span>
                              {!expanded && (
                                <span className="text-xs text-blue-500 hover:text-blue-700 whitespace-nowrap">
                                  Review
                                </span>
                              )}
                            </span>
                          ) : li.exceptions.length > 0 ? (
                            <span className="text-gray-300 text-xs">✓</span>
                          ) : null}
                          {hasExceptions && (
                            <span className="ml-1 text-gray-400 text-xs">
                              {expanded ? "▲" : "▼"}
                            </span>
                          )}
                        </td>
                      </tr>

                      {/* Expanded detail — billing breakdown + exceptions */}
                      {expanded && hasExceptions && (
                        <tr key={`${li.id}-exc`}>
                          <td colSpan={8} className="px-6 pb-4 pt-0 bg-gray-50">
                            <div className="pt-3 space-y-3">
                              {/* Billing breakdown — what was billed vs what's contracted */}
                              <BillingBreakdown line={li} />

                              {/* AI description alignment (secondary context) */}
                              {li.ai_description_assessment && (
                                <div className="rounded-lg border border-gray-200 bg-white px-4 py-3">
                                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
                                    Description vs. taxonomy match
                                  </p>
                                  <AiAssessmentBadge
                                    assessment={li.ai_description_assessment}
                                    showRationale
                                  />
                                </div>
                              )}

                              <CarrierExceptionPanel
                                exceptions={li.exceptions}
                                invoiceId={id}
                              />
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-gray-400">
            Click any row with exceptions to expand / collapse the resolution panel.
          </p>
        </div>
      )}

      {/* ── Request Changes dialog ─────────────────────────────────────────── */}
      {showChangesDialog && (
        <Dialog onClose={() => setShowChangesDialog(false)}>
          <h3 className="text-lg font-semibold text-gray-900 mb-4">
            Request Changes from Supplier
          </h3>
          <p className="text-sm text-gray-500 mb-4">
            The invoice will be returned to the supplier in{" "}
            <strong>REVIEW_REQUIRED</strong> status. They will be prompted to
            address your notes and resubmit.
          </p>
          <Textarea
            id="carrier-notes"
            label="Your notes for the supplier *"
            placeholder="e.g. Line 3 billed amount exceeds the contracted rate of $600…"
            rows={4}
            value={carrierNotes}
            onChange={(e) => setCarrierNotes(e.target.value)}
          />
          {changesMutation.isError && (
            <p className="mt-2 text-sm text-red-600">
              {(changesMutation.error as Error).message}
            </p>
          )}
          <div className="mt-5 flex justify-end gap-3">
            <Button variant="ghost" onClick={() => setShowChangesDialog(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={changesMutation.isPending}
              disabled={!carrierNotes.trim() || changesMutation.isPending}
              onClick={() => changesMutation.mutate()}
            >
              Send Back to Supplier
            </Button>
          </div>
        </Dialog>
      )}

      {/* ── Approve confirmation dialog ───────────────────────────────────── */}
      {showApproveConfirm && (() => {
        const inDispute = invoice.validation_summary
          ? parseFloat(invoice.validation_summary.total_in_dispute)
          : 0;
        const supplierNotResponded =
          invoice.status === "REVIEW_REQUIRED" && openExceptionCount > 0;
        const hasOpenExceptions = openExceptionCount > 0;
        // Require notes when waiving open exceptions
        const needsNotes = hasOpenExceptions && !approvalNotes.trim();

        return (
          <Dialog onClose={() => setShowApproveConfirm(false)}>
            <h3 className="text-lg font-semibold text-gray-900 mb-4">
              {hasOpenExceptions
                ? "Approve Invoice & Waive Exceptions?"
                : "Approve Invoice?"}
            </h3>

            {/* Clean approval — no exceptions */}
            {!hasOpenExceptions && (
              <p className="text-sm text-gray-500 mb-4">
                All exceptions have been resolved. This will approve the full
                invoice and mark it ready for payment.
              </p>
            )}

            {/* Supplier hasn't responded — strongest warning */}
            {supplierNotResponded && (
              <div className="mb-4 rounded-md border border-red-300 bg-red-50 px-4 py-3">
                <p className="text-sm font-semibold text-red-800">
                  The supplier has not responded yet
                </p>
                <p className="mt-1 text-sm text-red-700">
                  Approving now will waive all {openExceptionCount} billing
                  exception{openExceptionCount !== 1 ? "s" : ""} without the
                  supplier&apos;s input. The disputed charges will be accepted
                  as billed.
                </p>
              </div>
            )}

            {/* Financial impact */}
            {hasOpenExceptions && (
              <div className="mb-4 rounded-md border border-orange-200 bg-orange-50 px-4 py-3 space-y-1">
                <p className="text-sm font-semibold text-orange-800">
                  {openExceptionCount} open exception
                  {openExceptionCount !== 1 ? "s" : ""} will be permanently
                  waived
                </p>
                {inDispute > 0 && (
                  <p className="text-sm text-orange-700">
                    ${inDispute.toLocaleString("en-US", { minimumFractionDigits: 2 })}{" "}
                    in disputed charges will be approved at the billed amount.
                  </p>
                )}
                <p className="text-xs text-orange-600 mt-1">
                  This action cannot be undone.
                </p>
              </div>
            )}

            <Textarea
              id="approval-notes"
              label={hasOpenExceptions ? "Reason for waiving exceptions *" : "Approval notes (optional)"}
              placeholder={
                hasOpenExceptions
                  ? "Explain why these exceptions are being waived…"
                  : "Any notes to record with this approval…"
              }
              rows={3}
              value={approvalNotes}
              onChange={(e) => setApprovalNotes(e.target.value)}
            />
            {approveMutation.isError && (
              <p className="mt-2 text-sm text-red-600">
                {(approveMutation.error as Error).message}
              </p>
            )}
            <div className="mt-5 flex justify-end gap-3">
              <Button
                variant="ghost"
                onClick={() => setShowApproveConfirm(false)}
              >
                Cancel
              </Button>
              <Button
                variant={hasOpenExceptions ? "danger" : "primary"}
                loading={approveMutation.isPending}
                disabled={approveMutation.isPending || needsNotes}
                onClick={() => approveMutation.mutate()}
              >
                {hasOpenExceptions
                  ? `Approve & Waive ${openExceptionCount} Exception${openExceptionCount !== 1 ? "s" : ""}`
                  : "✓ Confirm Approval"}
              </Button>
            </div>
          </Dialog>
        );
      })()}
    </div>
  );
}

// ── Inline dialog overlay ─────────────────────────────────────────────────────

function Dialog({
  children,
  onClose,
}: {
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-xl bg-white px-8 py-8 shadow-xl">
        <div className="relative">
          <button
            onClick={onClose}
            className="absolute -right-4 -top-4 rounded-full p-2 text-gray-400 hover:text-gray-600"
          >
            ✕
          </button>
          {children}
        </div>
      </div>
    </div>
  );
}
