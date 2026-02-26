"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { listAdminInvoices } from "@/lib/api";
import { StatusBadge } from "@/components/status-badge";

const STATUS_TABS = [
  { label: "All", value: undefined },
  { label: "Pending Review", value: "PENDING_CARRIER_REVIEW" },
  { label: "Needs Changes", value: "REVIEW_REQUIRED" },
  { label: "Supplier Responded", value: "SUPPLIER_RESPONDED" },
  { label: "Approved", value: "APPROVED" },
  { label: "Exported", value: "EXPORTED" },
] as const;

type StatusTab = (typeof STATUS_TABS)[number]["value"];

export default function AdminInvoicesPage() {
  const [activeTab, setActiveTab] = useState<StatusTab>(
    "PENDING_CARRIER_REVIEW",
  );

  const { data: invoices, isLoading } = useQuery({
    queryKey: ["admin-invoices", activeTab],
    queryFn: () => listAdminInvoices(activeTab),
    refetchInterval: 30_000,
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Invoice Queue</h1>
          <p className="mt-1 text-sm text-gray-500">
            {invoices?.length ?? 0} invoices
          </p>
        </div>
        <div className="flex gap-3">
          <Link
            href="/admin/suppliers"
            className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50"
          >
            Suppliers
          </Link>
          <Link
            href="/admin/mappings"
            className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50"
          >
            Mapping Queue
          </Link>
        </div>
      </div>

      {/* Status tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex gap-1">
          {STATUS_TABS.map((tab) => {
            const active = activeTab === tab.value;
            return (
              <button
                key={String(tab.value)}
                onClick={() => setActiveTab(tab.value)}
                className={`px-4 py-2.5 text-sm font-medium transition-colors ${
                  active
                    ? "border-b-2 border-blue-600 text-blue-600"
                    : "text-gray-500 hover:border-b-2 hover:border-gray-300 hover:text-gray-700"
                }`}
              >
                {tab.label}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
          </div>
        ) : invoices?.length === 0 ? (
          <div className="py-16 text-center text-sm text-gray-400">
            No invoices in this queue.
          </div>
        ) : (
          <table className="min-w-full divide-y divide-gray-100">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Invoice #
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Date
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Status
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Billed
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Exceptions
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Submitted
                </th>
                <th className="w-16" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {invoices?.map((inv) => (
                <tr key={inv.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3">
                    <span className="font-mono text-sm font-medium text-gray-900">
                      {inv.invoice_number}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">
                    {inv.invoice_date}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={inv.status} />
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-sm text-gray-900">
                    {inv.total_billed
                      ? `$${Number(inv.total_billed).toFixed(2)}`
                      : "—"}
                  </td>
                  <td className="px-4 py-3 text-right text-sm">
                    {inv.exception_count > 0 ? (
                      <span className="font-semibold text-red-600">
                        {inv.exception_count}
                      </span>
                    ) : (
                      <span className="text-gray-400">0</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-500">
                    {inv.submitted_at
                      ? new Date(inv.submitted_at).toLocaleDateString()
                      : "—"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={`/admin/invoices/${inv.id}`}
                      className="text-sm font-medium text-blue-600 hover:text-blue-800"
                    >
                      Review →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
