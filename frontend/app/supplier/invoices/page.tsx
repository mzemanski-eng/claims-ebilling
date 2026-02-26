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

export default function SupplierInvoicesPage() {
  const { data: invoices, isLoading, isError, error } = useQuery({
    queryKey: ["supplier-invoices"],
    queryFn: listSupplierInvoices,
  });

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
        <div className="overflow-hidden rounded-xl border bg-white shadow-sm">
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
                  <td className="px-4 py-3 text-gray-600">
                    {formatDate(inv.invoice_date)}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={inv.status} />
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
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
