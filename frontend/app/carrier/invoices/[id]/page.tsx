"use client";

import { useState } from "react";
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
import { StatusBadge } from "@/components/status-badge";
import { ConfidenceBadge } from "@/components/confidence-badge";
import { ValidationSummaryCard } from "@/components/validation-summary-card";
import { CarrierExceptionPanel } from "@/components/exception-panel";
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
      invoice.status === "CARRIER_REVIEWING");

  const canExport = invoice.status === "APPROVED";

  const openExceptionCount = lines
    ? lines.reduce(
        (sum, li) =>
          sum + li.exceptions.filter((e) => e.status === "OPEN").length,
        0,
      )
    : 0;

  return (
    <div className="space-y-8">
      {/* Breadcrumb */}
      <div className="text-sm text-gray-500">
        <Link href="/carrier/queue" className="hover:text-blue-600">
          Review Queue
        </Link>
        <span className="mx-2">›</span>
        <span className="text-gray-900 font-medium">
          {invoice.invoice_number}
        </span>
      </div>

      {/* Sticky action bar */}
      <div className="sticky top-0 z-10 -mx-4 border-b bg-white px-4 py-3 shadow-sm sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold text-gray-900">
              {invoice.invoice_number}
            </h1>
            <StatusBadge status={invoice.status} className="text-sm" />
            {openExceptionCount > 0 && (
              <span className="rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-bold text-red-700">
                {openExceptionCount} open exception
                {openExceptionCount > 1 ? "s" : ""}
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
                <Button
                  variant="secondary"
                  onClick={() => setShowChangesDialog(true)}
                >
                  Request Changes
                </Button>
                <Button onClick={() => setShowApproveConfirm(true)}>
                  ✓ Approve Invoice
                </Button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Invoice meta */}
      <div className="flex flex-wrap gap-6 text-sm text-gray-600">
        <span>Invoice date: <strong>{formatDate(invoice.invoice_date)}</strong></span>
        <span>Submitted: <strong>{formatDate(invoice.submitted_at)}</strong></span>
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
          <ValidationSummaryCard summary={invoice.validation_summary} />
        </div>
      )}

      {/* Line items */}
      {linesLoading && (
        <div className="flex items-center justify-center py-10">
          <div className="h-6 w-6 animate-spin rounded-full border-4 border-blue-400 border-t-transparent" />
        </div>
      )}

      {lines && (
        <div>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Line Items ({lines.length})
          </h2>
          <div className="overflow-hidden rounded-xl border bg-white shadow-sm">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left font-semibold text-gray-600">#</th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-600">Description</th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-600">Taxonomy</th>
                  <th className="px-4 py-3 text-center font-semibold text-gray-600">Confidence</th>
                  <th className="px-4 py-3 text-right font-semibold text-gray-600">Billed</th>
                  <th className="px-4 py-3 text-right font-semibold text-gray-600">Expected</th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-600">Status</th>
                  <th className="px-4 py-3 text-center font-semibold text-gray-600">Exc.</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {lines.map((li) => {
                  const openExcs = li.exceptions.filter((e) => e.status === "OPEN" || e.status === "SUPPLIER_RESPONDED");
                  const expanded = expandedLines.has(li.id);
                  const hasExceptions = li.exceptions.length > 0;

                  return (
                    <>
                      <tr
                        key={li.id}
                        className={`${openExcs.length > 0 ? "bg-red-50" : "hover:bg-gray-50"} ${hasExceptions ? "cursor-pointer" : ""} transition-colors`}
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
                        <td className="px-4 py-3 text-center">
                          <ConfidenceBadge confidence={li.mapping_confidence} />
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
                          <StatusBadge status={li.status} />
                        </td>
                        <td className="px-4 py-3 text-center">
                          {openExcs.length > 0 ? (
                            <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-red-100 text-xs font-bold text-red-700">
                              {openExcs.length}
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

                      {/* Expanded exceptions */}
                      {expanded && hasExceptions && (
                        <tr key={`${li.id}-exc`}>
                          <td colSpan={8} className="px-6 pb-4 pt-0 bg-gray-50">
                            <div className="pt-3">
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
      {showApproveConfirm && (
        <Dialog onClose={() => setShowApproveConfirm(false)}>
          <h3 className="text-lg font-semibold text-gray-900 mb-4">
            Approve Invoice?
          </h3>
          <p className="text-sm text-gray-500 mb-4">
            This will approve the full invoice. Any remaining open exceptions
            will be automatically <strong>waived</strong>. This action cannot be
            undone.
          </p>
          {openExceptionCount > 0 && (
            <div className="mb-4 rounded-md border border-orange-200 bg-orange-50 px-4 py-3">
              <p className="text-sm text-orange-800">
                ⚠ {openExceptionCount} open exception
                {openExceptionCount > 1 ? "s" : ""} will be waived.
              </p>
            </div>
          )}
          <Textarea
            id="approval-notes"
            label="Approval notes (optional)"
            placeholder="Any notes to record with this approval…"
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
              loading={approveMutation.isPending}
              disabled={approveMutation.isPending}
              onClick={() => approveMutation.mutate()}
            >
              ✓ Confirm Approval
            </Button>
          </div>
        </Dialog>
      )}
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
