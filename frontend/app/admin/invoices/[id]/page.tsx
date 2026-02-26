"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getAdminInvoice,
  getAdminInvoiceLines,
  approveAdminInvoice,
  exportAdminInvoice,
  resolveAdminException,
  downloadBlob,
} from "@/lib/api";
import { StatusBadge } from "@/components/status-badge";
import { ConfidenceBadge } from "@/components/confidence-badge";
import { ValidationSummaryCard } from "@/components/validation-summary-card";
import { Button } from "@/components/ui/button";
import type { LineItemCarrierView } from "@/lib/types";
import { ResolutionActions } from "@/lib/types";

// ── Inline Dialog ─────────────────────────────────────────────────────────────
function Dialog({
  open,
  title,
  children,
  onClose,
}: {
  open: boolean;
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b px-6 py-4">
          <h2 className="text-base font-semibold text-gray-900">{title}</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
          >
            ✕
          </button>
        </div>
        <div className="px-6 py-5">{children}</div>
      </div>
    </div>
  );
}

// ── Exception resolve row ─────────────────────────────────────────────────────
function ExceptionRow({
  exc,
  invoiceId,
}: {
  exc: LineItemCarrierView["exceptions"][number];
  invoiceId: string;
}) {
  const qc = useQueryClient();
  const [action, setAction] = useState<string>(ResolutionActions.WAIVED);
  const [notes, setNotes] = useState("");

  const resolveMut = useMutation({
    mutationFn: () => resolveAdminException(exc.exception_id, action, notes),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-invoice", invoiceId] });
      qc.invalidateQueries({ queryKey: ["admin-invoice-lines", invoiceId] });
    },
  });

  if (exc.status !== "OPEN" && exc.status !== "SUPPLIER_RESPONDED") {
    return (
      <div className="flex items-center gap-2 rounded bg-gray-50 px-3 py-2 text-xs text-gray-500">
        <StatusBadge status={exc.status} />
        <span>{exc.message}</span>
      </div>
    );
  }

  return (
    <div className="rounded border border-orange-200 bg-orange-50 p-3 text-xs space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div>
          <StatusBadge status={exc.status} />
          <p className="mt-1 text-gray-700">{exc.message}</p>
          {exc.supplier_response && (
            <p className="mt-1 italic text-gray-500">
              Supplier: {exc.supplier_response}
            </p>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <select
          value={action}
          onChange={(e) => setAction(e.target.value)}
          className="rounded border border-gray-300 bg-white px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
        >
          {Object.values(ResolutionActions).map((a) => (
            <option key={a} value={a}>
              {a.replace(/_/g, " ")}
            </option>
          ))}
        </select>
        <input
          type="text"
          placeholder="Notes (optional)"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          className="flex-1 rounded border border-gray-300 bg-white px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
        <Button
          size="sm"
          loading={resolveMut.isPending}
          onClick={() => resolveMut.mutate()}
        >
          Resolve
        </Button>
      </div>
      {resolveMut.isError && (
        <p className="text-red-600">{(resolveMut.error as Error).message}</p>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function AdminInvoiceDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const { id } = params;
  const router = useRouter();
  const qc = useQueryClient();

  const [expandedLines, setExpandedLines] = useState<Set<string>>(new Set());
  const [showApproveConfirm, setShowApproveConfirm] = useState(false);
  const [approvalNotes, setApprovalNotes] = useState("");
  const [exportError, setExportError] = useState<string | null>(null);

  const { data: invoice, isLoading: loadingInvoice } = useQuery({
    queryKey: ["admin-invoice", id],
    queryFn: () => getAdminInvoice(id),
  });

  const { data: lines, isLoading: loadingLines } = useQuery({
    queryKey: ["admin-invoice-lines", id],
    queryFn: () => getAdminInvoiceLines(id),
    enabled: !!invoice,
  });

  const approveMut = useMutation({
    mutationFn: () => approveAdminInvoice(id, undefined, approvalNotes || undefined),
    onSuccess: () => {
      setShowApproveConfirm(false);
      qc.invalidateQueries({ queryKey: ["admin-invoice", id] });
    },
  });

  async function handleExport() {
    setExportError(null);
    try {
      const blob = await exportAdminInvoice(id);
      downloadBlob(
        blob,
        `approved_${invoice?.invoice_number ?? id}_${new Date().toISOString().slice(0, 10)}.csv`,
      );
      qc.invalidateQueries({ queryKey: ["admin-invoice", id] });
    } catch (e) {
      setExportError((e as Error).message);
    }
  }

  function toggleLine(lineId: string) {
    setExpandedLines((prev) => {
      const next = new Set(prev);
      if (next.has(lineId)) next.delete(lineId);
      else next.add(lineId);
      return next;
    });
  }

  if (loadingInvoice) {
    return (
      <div className="flex min-h-64 items-center justify-center">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
      </div>
    );
  }

  if (!invoice) {
    return (
      <div className="py-16 text-center text-gray-500">Invoice not found.</div>
    );
  }

  const canApprove =
    invoice.status === "PENDING_CARRIER_REVIEW" ||
    invoice.status === "CARRIER_REVIEWING";
  const canExport = invoice.status === "APPROVED";

  return (
    <>
      {/* Approve confirmation dialog */}
      <Dialog
        open={showApproveConfirm}
        title="Approve Invoice"
        onClose={() => setShowApproveConfirm(false)}
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-600">
            Approving{" "}
            <strong className="font-mono">{invoice.invoice_number}</strong> will
            mark it ready for export. Any remaining open exceptions will be
            recorded.
          </p>
          <div>
            <label className="block text-sm font-medium text-gray-700">
              Approval notes (optional)
            </label>
            <textarea
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
              rows={3}
              value={approvalNotes}
              onChange={(e) => setApprovalNotes(e.target.value)}
              placeholder="Any notes for the record…"
            />
          </div>
          {approveMut.isError && (
            <p className="text-sm text-red-600">
              {(approveMut.error as Error).message}
            </p>
          )}
          <div className="flex justify-end gap-3">
            <Button
              variant="ghost"
              onClick={() => setShowApproveConfirm(false)}
            >
              Cancel
            </Button>
            <Button
              loading={approveMut.isPending}
              onClick={() => approveMut.mutate()}
            >
              Confirm Approval
            </Button>
          </div>
        </div>
      </Dialog>

      {/* Sticky action bar */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.back()}
            className="text-sm text-gray-500 hover:text-gray-700"
          >
            ← Back
          </button>
          <h1 className="text-xl font-bold text-gray-900 font-mono">
            {invoice.invoice_number}
          </h1>
          <StatusBadge status={invoice.status} />
        </div>
        <div className="flex items-center gap-3">
          {canApprove && (
            <Button onClick={() => setShowApproveConfirm(true)}>
              ✓ Approve
            </Button>
          )}
          {canExport && (
            <Button variant="secondary" onClick={handleExport}>
              ↓ Export CSV
            </Button>
          )}
        </div>
      </div>

      {exportError && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {exportError}
        </div>
      )}

      {/* Invoice metadata */}
      <div className="mb-6 grid grid-cols-2 gap-4 rounded-xl border bg-white p-6 shadow-sm sm:grid-cols-4">
        <div>
          <p className="text-xs font-medium uppercase text-gray-400">
            Supplier
          </p>
          <p className="mt-1 text-sm font-semibold text-gray-900">
            {invoice.supplier_name ?? "—"}
          </p>
        </div>
        <div>
          <p className="text-xs font-medium uppercase text-gray-400">
            Contract
          </p>
          <p className="mt-1 text-sm text-gray-700">
            {invoice.contract_name ?? "—"}
          </p>
        </div>
        <div>
          <p className="text-xs font-medium uppercase text-gray-400">
            Invoice date
          </p>
          <p className="mt-1 text-sm text-gray-700">{invoice.invoice_date}</p>
        </div>
        <div>
          <p className="text-xs font-medium uppercase text-gray-400">
            Submitted
          </p>
          <p className="mt-1 text-sm text-gray-700">
            {invoice.submitted_at
              ? new Date(invoice.submitted_at).toLocaleDateString()
              : "—"}
          </p>
        </div>
      </div>

      {/* Validation summary */}
      {invoice.validation_summary && (
        <div className="mb-6">
          <ValidationSummaryCard summary={invoice.validation_summary} />
        </div>
      )}

      {/* Line items */}
      <div className="rounded-xl border bg-white shadow-sm overflow-hidden">
        <div className="border-b px-6 py-4">
          <h2 className="font-semibold text-gray-900">Line Items</h2>
        </div>
        {loadingLines ? (
          <div className="flex justify-center py-10">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
          </div>
        ) : (
          <table className="min-w-full divide-y divide-gray-100 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500 w-10">
                  #
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">
                  Description
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">
                  Taxonomy
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">
                  Conf.
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold uppercase text-gray-500">
                  Billed
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold uppercase text-gray-500">
                  Expected
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">
                  Status
                </th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {lines?.map((line) => {
                const isExpanded = expandedLines.has(line.id);
                const hasIssues =
                  line.exceptions.length > 0 || line.needs_review;
                return (
                  <>
                    <tr
                      key={line.id}
                      className={`transition-colors ${hasIssues ? "cursor-pointer hover:bg-amber-50" : "hover:bg-gray-50"}`}
                      onClick={() => hasIssues && toggleLine(line.id)}
                    >
                      <td className="px-4 py-3 text-gray-400">
                        {line.line_number}
                      </td>
                      <td className="px-4 py-3">
                        <p className="font-medium text-gray-900 leading-snug">
                          {line.raw_description}
                        </p>
                        {line.claim_number && (
                          <p className="text-xs text-gray-400 mt-0.5">
                            Claim {line.claim_number}
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {line.taxonomy_code ? (
                          <div>
                            <p className="font-mono text-xs text-gray-700">
                              {line.taxonomy_code}
                            </p>
                            {line.taxonomy_label && (
                              <p className="text-xs text-gray-400 mt-0.5 truncate max-w-40">
                                {line.taxonomy_label}
                              </p>
                            )}
                          </div>
                        ) : (
                          <span className="text-gray-300">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {line.mapping_confidence ? (
                          <ConfidenceBadge confidence={line.mapping_confidence} />
                        ) : (
                          <span className="text-gray-300">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-gray-900">
                        ${Number(line.raw_amount).toFixed(2)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono">
                        {line.expected_amount ? (
                          <span
                            className={
                              Number(line.raw_amount) >
                              Number(line.expected_amount)
                                ? "text-red-600"
                                : "text-gray-700"
                            }
                          >
                            ${Number(line.expected_amount).toFixed(2)}
                          </span>
                        ) : (
                          <span className="text-gray-300">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <StatusBadge status={line.status} />
                          {line.exceptions.length > 0 && (
                            <span className="rounded-full bg-red-100 px-1.5 py-0.5 text-xs font-semibold text-red-700">
                              {line.exceptions.length}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-gray-400 text-xs">
                        {hasIssues && (isExpanded ? "▲" : "▼")}
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr key={`${line.id}-expanded`}>
                        <td colSpan={8} className="bg-amber-50 px-8 py-4">
                          <div className="space-y-3">
                            {line.needs_review &&
                              line.exceptions.length === 0 && (
                                <div className="rounded bg-yellow-100 px-3 py-2 text-xs text-yellow-800">
                                  ⚠ Low mapping confidence — consider overriding
                                  via{" "}
                                  <a
                                    href="/admin/mappings"
                                    className="underline"
                                  >
                                    Mapping Queue
                                  </a>
                                  .
                                </div>
                              )}
                            {line.exceptions.map((exc) => (
                              <ExceptionRow
                                key={exc.exception_id}
                                exc={exc}
                                invoiceId={id}
                              />
                            ))}
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
