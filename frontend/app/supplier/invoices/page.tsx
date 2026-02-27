"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { listSupplierInvoices } from "@/lib/api";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";

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

// Human-readable labels for supplier-facing status badges
const STATUS_LABELS: Record<string, string> = {
  DRAFT: "Draft",
  SUBMITTED: "Submitted",
  PROCESSING: "Processing",
  REVIEW_REQUIRED: "Action Required",
  SUPPLIER_RESPONDED: "Response Submitted",
  PENDING_CARRIER_REVIEW: "Under Carrier Review",
  CARRIER_REVIEWING: "Carrier Reviewing",
  APPROVED: "Approved",
  DISPUTED: "Disputed",
  EXPORTED: "Payment Issued",
  WITHDRAWN: "Withdrawn",
};

// Plain-English next-step guidance per status
function getNextStep(status: string, exceptionCount: number): string {
  switch (status) {
    case "REVIEW_REQUIRED":
      return `Respond to ${exceptionCount} exception${exceptionCount !== 1 ? "s" : ""} and resubmit`;
    case "DRAFT":
      return "Upload your invoice file to submit";
    case "SUBMITTED":
    case "PROCESSING":
      return "Validation in progress — no action needed";
    case "SUPPLIER_RESPONDED":
    case "PENDING_CARRIER_REVIEW":
    case "CARRIER_REVIEWING":
      return "Under carrier review — no action needed";
    case "APPROVED":
      return "Payment will be issued";
    case "DISPUTED":
      return "Contact your carrier representative";
    case "EXPORTED":
      return "Payment processed";
    case "WITHDRAWN":
      return "—";
    default:
      return "—";
  }
}

const ACTION_NEEDED = new Set(["REVIEW_REQUIRED", "DRAFT"]);

export default function SupplierInvoicesPage() {
  const { data: invoices, isLoading, isError, error } = useQuery({
    queryKey: ["supplier-invoices"],
    queryFn: listSupplierInvoices,
  });

  // Sort: action-needed invoices first, then newest-first within each group
  const sorted = invoices
    ? [...invoices].sort((a, b) => {
        const ap = ACTION_NEEDED.has(a.status) ? 0 : 1;
        const bp = ACTION_NEEDED.has(b.status) ? 0 : 1;
        if (ap !== bp) return ap - bp;
        const aDate = a.submitted_at ? new Date(a.submitted_at).getTime() : 0;
        const bDate = b.submitted_at ? new Date(b.submitted_at).getTime() : 0;
        return bDate - aDate;
      })
    : [];

  return (
    <div>
      {/* Page header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">My Invoices</h1>
          <p className="text-sm text-gray-500 mt-1">
            Submit and track your invoice submissions
          </p>
        </div>
        <Link href="/supplier/invoices/new">
          <Button>+ New Invoice</Button>
        </Link>
      </div>

      {/* Content */}
      {isLoading && (
        <div className="flex items-center justify-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
        </div>
      )}

      {isError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3">
          <p className="text-sm text-red-700">
            {(error as Error).message ?? "Failed to load invoices."}
          </p>
        </div>
      )}

      {invoices && invoices.length === 0 && (
        <div className="rounded-xl border-2 border-dashed border-gray-200 py-20 text-center">
          <p className="text-gray-400">No invoices yet.</p>
          <Link href="/supplier/invoices/new">
            <Button className="mt-4" variant="secondary">
              Submit your first invoice
            </Button>
          </Link>
        </div>
      )}

      {invoices && invoices.length > 0 && (
        <div className="overflow-x-auto rounded-xl border bg-white shadow-sm">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left font-semibold text-gray-600">
                  Invoice #
                </th>
                <th className="px-4 py-3 text-left font-semibold text-gray-600">
                  Invoice Date
                </th>
                <th className="px-4 py-3 text-left font-semibold text-gray-600">
                  Status
                </th>
                <th className="px-4 py-3 text-left font-semibold text-gray-600">
                  Next Step
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
              {sorted.map((inv) => {
                const needsAction = ACTION_NEEDED.has(inv.status);
                const nextStep = getNextStep(inv.status, inv.exception_count);
                return (
                  <tr
                    key={inv.id}
                    className={`transition-colors ${needsAction ? "bg-orange-50 hover:bg-orange-100" : "hover:bg-gray-50"}`}
                  >
                    <td className="px-4 py-3 font-medium text-gray-900">
                      {inv.invoice_number}
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      {formatDate(inv.invoice_date)}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge
                        status={inv.status}
                        label={STATUS_LABELS[inv.status]}
                      />
                    </td>
                    <td className="px-4 py-3 max-w-xs">
                      <span
                        className={`text-xs ${needsAction ? "font-medium text-orange-700" : "text-gray-500"}`}
                      >
                        {nextStep}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-gray-700">
                      {formatMoney(inv.total_billed)}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {inv.exception_count > 0 ? (
                        <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-red-100 text-xs font-bold text-red-700">
                          {inv.exception_count}
                        </span>
                      ) : (
                        <span className="text-gray-300">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-500">
                      {formatDate(inv.submitted_at)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link
                        href={`/supplier/invoices/${inv.id}`}
                        className="text-blue-600 hover:text-blue-800 font-medium"
                      >
                        View →
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
