"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { listCarrierInvoices, approveCarrierInvoice } from "@/lib/api";
import { StatusBadge } from "@/components/status-badge";
import { useToast } from "@/components/toast";
import type { InvoiceListItem } from "@/lib/types";

// ── Risk badge — shown for HIGH / CRITICAL triage ─────────────────────────────
const RISK_BADGE: Record<string, string> = {
  HIGH:     "bg-red-100 text-red-700 border border-red-200",
  CRITICAL: "bg-red-600 text-white",
};

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatMoney(val: string | null) {
  if (!val) return "—";
  return `$${parseFloat(val).toLocaleString("en-US", { minimumFractionDigits: 2 })}`;
}

function formatAge(iso: string | null): { label: string; colorClass: string } | null {
  if (!iso) return null;
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days === 0) return { label: "today", colorClass: "text-gray-400" };
  if (days === 1) return { label: "1d ago", colorClass: "text-gray-400" };
  if (days < 3)  return { label: `${days}d ago`, colorClass: "text-gray-400" };
  if (days < 7)  return { label: `${days}d ago`, colorClass: "text-amber-500" };
  return { label: `${days}d ago`, colorClass: "text-red-500 font-semibold" };
}

type SortKey = "submitted_at" | "exception_count" | "total_billed";
type SortDir = "asc" | "desc";

function sortInvoices(list: InvoiceListItem[], key: SortKey, dir: SortDir) {
  return [...list].sort((a, b) => {
    let diff = 0;
    if (key === "submitted_at") {
      const aDate = a.submitted_at ? new Date(a.submitted_at).getTime() : 0;
      const bDate = b.submitted_at ? new Date(b.submitted_at).getTime() : 0;
      diff = aDate - bDate;
    } else if (key === "exception_count") {
      diff = (a.exception_count ?? 0) - (b.exception_count ?? 0);
    } else if (key === "total_billed") {
      diff = parseFloat(a.total_billed ?? "0") - parseFloat(b.total_billed ?? "0");
    }
    return dir === "asc" ? diff : -diff;
  });
}

// ── Shared invoice row ─────────────────────────────────────────────────────────

function InvoiceRow({
  inv,
  approvingId,
  approveMut,
  setApprovingId,
}: {
  inv: InvoiceListItem;
  approvingId: string | null;
  approveMut: { isPending: boolean; mutate: (id: string) => void };
  setApprovingId: (id: string) => void;
}) {
  const age = formatAge(inv.submitted_at);
  const canQuickApprove =
    inv.exception_count === 0 && inv.status === "PENDING_CARRIER_REVIEW";
  const isApproving = approvingId === inv.id && approveMut.isPending;

  return (
    <tr className="hover:bg-gray-50 transition-colors">
      <td className="px-4 py-3 font-medium text-gray-900">
        {inv.invoice_number}
      </td>
      <td className="px-4 py-3 text-sm text-gray-600">
        {inv.supplier_name ?? "—"}
      </td>
      <td className="px-4 py-3 text-gray-600">
        {formatDate(inv.invoice_date)}
      </td>
      <td className="px-4 py-3">
        <div className="flex flex-wrap items-center gap-1.5">
          {inv.triage_risk_level && RISK_BADGE[inv.triage_risk_level] && (
            <span
              className={`inline-flex rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide shrink-0 ${RISK_BADGE[inv.triage_risk_level]}`}
              title={`AI triage risk: ${inv.triage_risk_level}`}
            >
              {inv.triage_risk_level}
            </span>
          )}
          <StatusBadge status={inv.status} />
          {inv.ai_recommendations_ready > 0 && inv.exception_count > 0 && (
            <span
              title={
                inv.ai_recommendations_ready >= inv.exception_count
                  ? "AI has recommendations for all open exceptions"
                  : `AI has recommendations for ${inv.ai_recommendations_ready} of ${inv.exception_count} exceptions`
              }
              className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold whitespace-nowrap ${
                inv.ai_recommendations_ready >= inv.exception_count
                  ? "border-blue-200 bg-blue-50 text-blue-700"
                  : "border-amber-200 bg-amber-50 text-amber-700"
              }`}
            >
              {inv.ai_recommendations_ready >= inv.exception_count
                ? "AI Ready"
                : `${inv.ai_recommendations_ready}/${inv.exception_count} AI`}
            </span>
          )}
        </div>
      </td>
      <td className="px-4 py-3 text-right font-mono text-gray-700">
        {formatMoney(inv.total_billed)}
      </td>
      <td className="px-4 py-3 text-center">
        {inv.exception_count > 0 ? (
          <div className="inline-flex flex-col items-center gap-0.5">
            <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-red-100 text-xs font-bold text-red-700">
              {inv.exception_count}
            </span>
            <span className={`text-[10px] font-medium ${
              inv.status === "REVIEW_REQUIRED" ||
              inv.status === "SUPPLIER_RESPONDED" ||
              inv.status === "CARRIER_REVIEWING"
                ? "text-red-400"
                : "text-amber-400"
            }`}>
              {inv.status === "REVIEW_REQUIRED" ||
              inv.status === "SUPPLIER_RESPONDED" ||
              inv.status === "CARRIER_REVIEWING"
                ? "spend"
                : "classif."}
            </span>
          </div>
        ) : (
          <span className="text-gray-300">—</span>
        )}
      </td>
      <td className="px-4 py-3">
        <div className="flex flex-col">
          <span className="text-gray-500">{formatDate(inv.submitted_at)}</span>
          {age && (
            <span className={`text-[11px] ${age.colorClass}`}>
              {age.label}
            </span>
          )}
        </div>
      </td>
      <td className="px-4 py-3 text-right">
        <div className="flex items-center justify-end gap-2">
          {canQuickApprove && (
            <button
              disabled={approveMut.isPending}
              onClick={() => {
                setApprovingId(inv.id);
                approveMut.mutate(inv.id);
              }}
              className="rounded-md border border-green-300 bg-green-50 px-2.5 py-1 text-xs font-semibold text-green-700 hover:bg-green-100 disabled:opacity-50 transition-colors"
            >
              {isApproving ? "…" : "✓ Approve"}
            </button>
          )}
          <Link
            href={`/carrier/invoices/${inv.id}`}
            className="whitespace-nowrap rounded-md bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 transition-colors"
          >
            Review
          </Link>
        </div>
      </td>
    </tr>
  );
}

// ── Table wrapper ──────────────────────────────────────────────────────────────

function InvoiceTable({
  invoices,
  approvingId,
  approveMut,
  setApprovingId,
  sortKey,
  sortDir,
  toggleSort,
}: {
  invoices: InvoiceListItem[];
  approvingId: string | null;
  approveMut: { isPending: boolean; mutate: (id: string) => void };
  setApprovingId: (id: string) => void;
  sortKey: SortKey;
  sortDir: SortDir;
  toggleSort: (k: SortKey) => void;
}) {
  const sortIndicator = (key: SortKey) =>
    sortKey === key ? (sortDir === "asc" ? " ▲" : " ▼") : "";

  return (
    <div className="overflow-hidden rounded-xl border bg-white shadow-sm">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left font-semibold text-gray-600">Invoice #</th>
            <th className="px-4 py-3 text-left font-semibold text-gray-600">Supplier</th>
            <th className="px-4 py-3 text-left font-semibold text-gray-600">Invoice Date</th>
            <th className="px-4 py-3 text-left font-semibold text-gray-600">Status</th>
            <th
              className="px-4 py-3 text-right font-semibold text-gray-600 cursor-pointer select-none hover:text-blue-600"
              onClick={() => toggleSort("total_billed")}
              title="Click to sort by billed amount"
            >
              Total Billed{sortIndicator("total_billed")}
            </th>
            <th
              className="px-4 py-3 text-center font-semibold text-gray-600 cursor-pointer select-none hover:text-blue-600"
              onClick={() => toggleSort("exception_count")}
              title="Click to sort by exception count"
            >
              Exceptions{sortIndicator("exception_count")}
            </th>
            <th
              className="px-4 py-3 text-left font-semibold text-gray-600 cursor-pointer select-none hover:text-blue-600"
              onClick={() => toggleSort("submitted_at")}
              title="Click to sort by submission date"
            >
              Submitted{sortIndicator("submitted_at")}
            </th>
            <th className="px-4 py-3" />
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {invoices.map((inv) => (
            <InvoiceRow
              key={inv.id}
              inv={inv}
              approvingId={approvingId}
              approveMut={approveMut}
              setApprovingId={setApprovingId}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function CarrierQueuePage() {
  const qc = useQueryClient();
  const toast = useToast();

  const [sortKey, setSortKey] = useState<SortKey>("submitted_at");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [approvingId, setApprovingId] = useState<string | null>(null);

  // REVIEW_REQUIRED: billing exceptions flagged after bill audit — carrier must resolve
  const { data: reviewRequiredInvoices, isLoading: loadingReviewRequired } = useQuery({
    queryKey: ["carrier-queue", "REVIEW_REQUIRED"],
    queryFn: () => listCarrierInvoices("REVIEW_REQUIRED"),
    refetchInterval: 30_000,
  });

  // PENDING_CARRIER_REVIEW: exceptions resolved, ready for final carrier approval
  const { data: pendingInvoices, isLoading: loadingPending } = useQuery({
    queryKey: ["carrier-queue", "PENDING_CARRIER_REVIEW"],
    queryFn: () => listCarrierInvoices("PENDING_CARRIER_REVIEW"),
    refetchInterval: 30_000,
  });

  // CARRIER_REVIEWING: invoices a reviewer is actively working through
  const { data: reviewingInvoices, isLoading: loadingReviewing } = useQuery({
    queryKey: ["carrier-queue", "CARRIER_REVIEWING"],
    queryFn: () => listCarrierInvoices("CARRIER_REVIEWING"),
    refetchInterval: 30_000,
  });

  const isLoading = loadingReviewRequired || loadingPending || loadingReviewing;

  const approveMut = useMutation({
    mutationFn: (invoiceId: string) => approveCarrierInvoice(invoiceId),
    onSuccess: () => {
      setApprovingId(null);
      qc.invalidateQueries({ queryKey: ["carrier-queue"] });
      toast.success("Invoice approved");
    },
    onError: (err: Error) => {
      setApprovingId(null);
      toast.error("Could not approve invoice", err.message);
    },
  });

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "submitted_at" ? "asc" : "desc");
    }
  }

  const exceptionInvoices = useMemo(
    () => sortInvoices(reviewRequiredInvoices ?? [], sortKey, sortDir),
    [reviewRequiredInvoices, sortKey, sortDir],
  );

  const approvalInvoices = useMemo(
    () =>
      sortInvoices(
        [...(pendingInvoices ?? []), ...(reviewingInvoices ?? [])],
        sortKey,
        sortDir,
      ),
    [pendingInvoices, reviewingInvoices, sortKey, sortDir],
  );

  const totalCount = exceptionInvoices.length + approvalInvoices.length;

  const tableProps = { approvingId, approveMut, setApprovingId, sortKey, sortDir, toggleSort };

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Action Required</h1>
        <p className="mt-1 text-sm text-gray-500">
          Invoices that need your attention
          {totalCount > 0 && ` · ${totalCount} invoice${totalCount !== 1 ? "s" : ""}`}
        </p>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
        </div>
      )}

      {!isLoading && totalCount === 0 && (
        <div className="rounded-xl border-2 border-dashed border-gray-200 py-20 text-center">
          <p className="text-4xl">🎉</p>
          <p className="mt-3 font-medium text-gray-700">Queue is empty!</p>
          <p className="text-sm text-gray-400 mt-1">
            All invoices have been reviewed.
          </p>
        </div>
      )}

      {!isLoading && exceptionInvoices.length > 0 && (
        <div className="mb-8">
          <div className="mb-3 flex items-center gap-2">
            <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-red-100 text-xs font-bold text-red-700">
              {exceptionInvoices.length}
            </span>
            <h2 className="text-sm font-semibold text-gray-800">
              Exceptions Requiring Review
            </h2>
            <span className="text-xs text-gray-400">
              — resolve billing exceptions before these can be approved
            </span>
          </div>
          <InvoiceTable invoices={exceptionInvoices} {...tableProps} />
        </div>
      )}

      {!isLoading && approvalInvoices.length > 0 && (
        <div>
          {exceptionInvoices.length > 0 && (
            <div className="mb-3 flex items-center gap-2">
              <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-green-100 text-xs font-bold text-green-700">
                {approvalInvoices.length}
              </span>
              <h2 className="text-sm font-semibold text-gray-800">
                Ready for Final Approval
              </h2>
            </div>
          )}
          <InvoiceTable invoices={approvalInvoices} {...tableProps} />
        </div>
      )}
    </div>
  );
}
