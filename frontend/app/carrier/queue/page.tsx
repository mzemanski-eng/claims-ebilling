"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { listCarrierInvoices } from "@/lib/api";
import { StatusBadge } from "@/components/status-badge";

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

export default function CarrierQueuePage() {
  // Fetch both PENDING_CARRIER_REVIEW and CARRIER_REVIEWING — invoices stay
  // visible while a reviewer is actively working on them.
  const { data: pendingInvoices, isLoading: loadingPending } = useQuery({
    queryKey: ["carrier-queue", "PENDING_CARRIER_REVIEW"],
    queryFn: () => listCarrierInvoices("PENDING_CARRIER_REVIEW"),
    refetchInterval: 30_000,
  });

  const { data: reviewingInvoices, isLoading: loadingReviewing } = useQuery({
    queryKey: ["carrier-queue", "CARRIER_REVIEWING"],
    queryFn: () => listCarrierInvoices("CARRIER_REVIEWING"),
    refetchInterval: 30_000,
  });

  const isLoading = loadingPending || loadingReviewing;

  // Merge and sort: oldest submitted first (soonest deadline)
  const invoices = useMemo(() => {
    const all = [...(pendingInvoices ?? []), ...(reviewingInvoices ?? [])];
    return all.sort((a, b) => {
      const aDate = a.submitted_at ? new Date(a.submitted_at).getTime() : 0;
      const bDate = b.submitted_at ? new Date(b.submitted_at).getTime() : 0;
      return aDate - bDate;
    });
  }, [pendingInvoices, reviewingInvoices]);

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Review Queue</h1>
        <p className="mt-1 text-sm text-gray-500">
          Invoices awaiting or currently under carrier review · oldest first
        </p>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
        </div>
      )}

      {!isLoading && invoices.length === 0 && (
        <div className="rounded-xl border-2 border-dashed border-gray-200 py-20 text-center">
          <p className="text-4xl">🎉</p>
          <p className="mt-3 font-medium text-gray-700">Queue is empty!</p>
          <p className="text-sm text-gray-400 mt-1">
            All invoices have been reviewed.
          </p>
        </div>
      )}

      {!isLoading && invoices.length > 0 && (
        <div className="overflow-hidden rounded-xl border bg-white shadow-sm">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left font-semibold text-gray-600">
                  Invoice #
                </th>
                <th className="px-4 py-3 text-left font-semibold text-gray-600">
                  Supplier
                </th>
                <th className="px-4 py-3 text-left font-semibold text-gray-600">
                  Invoice Date
                </th>
                <th className="px-4 py-3 text-left font-semibold text-gray-600">
                  Status
                </th>
                <th className="px-4 py-3 text-right font-semibold text-gray-600">
                  Total Billed
                </th>
                <th className="px-4 py-3 text-center font-semibold text-gray-600">
                  Exceptions
                </th>
                <th className="px-4 py-3 text-left font-semibold text-gray-600">
                  Submitted
                </th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {invoices.map((inv) => (
                <tr key={inv.id} className="hover:bg-gray-50 transition-colors">
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
                  <td className="px-4 py-3 text-gray-500">
                    {formatDate(inv.submitted_at)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={`/carrier/invoices/${inv.id}`}
                      className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 transition-colors"
                    >
                      Review →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
