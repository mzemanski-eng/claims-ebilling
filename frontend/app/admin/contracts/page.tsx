"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { listAdminContracts, listAdminSuppliers } from "@/lib/api";

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AdminContractsPage() {
  const [supplierId, setSupplierId] = useState("");

  const { data: contracts, isLoading } = useQuery({
    queryKey: ["admin-contracts", supplierId],
    queryFn: () => listAdminContracts(supplierId || undefined),
    refetchInterval: 60_000,
  });

  const { data: suppliers } = useQuery({
    queryKey: ["admin-suppliers"],
    queryFn: listAdminSuppliers,
    staleTime: 5 * 60 * 1000,
  });

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Contracts</h1>
          <p className="mt-1 text-sm text-gray-500">
            {contracts?.length ?? 0} contract{contracts?.length === 1 ? "" : "s"}
          </p>
        </div>
        <Link
          href="/admin/contracts/new"
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 transition-colors"
        >
          + New Contract
        </Link>
      </div>

      {/* Filter bar */}
      <div className="flex items-end gap-3 rounded-xl border bg-white p-4 shadow-sm">
        <div className="flex-1 min-w-[200px]">
          <label className="mb-1 block text-xs font-medium text-gray-500">
            Supplier
          </label>
          <select
            value={supplierId}
            onChange={(e) => setSupplierId(e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            <option value="">All suppliers</option>
            {suppliers?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
        {supplierId && (
          <button
            onClick={() => setSupplierId("")}
            className="rounded-md px-3 py-2 text-sm font-medium text-gray-500 hover:text-red-600 transition-colors"
          >
            Clear
          </button>
        )}
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
          </div>
        ) : contracts?.length === 0 ? (
          <div className="py-16 text-center">
            <p className="text-sm text-gray-400">No contracts found.</p>
            <Link
              href="/admin/contracts/new"
              className="mt-2 inline-block text-sm font-medium text-blue-600 hover:text-blue-800"
            >
              Create the first contract →
            </Link>
          </div>
        ) : (
          <table className="min-w-full divide-y divide-gray-100">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Contract Name
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Supplier
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Effective
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Scope
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Rate Cards
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Guidelines
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Vertical
                </th>
                <th className="w-16" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {contracts?.map((c) => (
                <tr key={c.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 text-sm font-medium text-gray-900">
                    {c.name}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">
                    {c.supplier_name ?? "—"}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">
                    {c.effective_from}
                    {c.effective_to ? (
                      <span className="text-gray-400"> → {c.effective_to}</span>
                    ) : (
                      <span className="text-gray-400"> → ongoing</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600 capitalize">
                    {c.geography_scope}
                  </td>
                  <td className="px-4 py-3 text-right text-sm text-gray-900">
                    {c.rate_card_count}
                  </td>
                  <td className="px-4 py-3 text-right text-sm text-gray-900">
                    {c.guideline_count}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                        c.is_active
                          ? "bg-green-50 text-green-700"
                          : "bg-gray-100 text-gray-500"
                      }`}
                    >
                      {c.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {c.vertical_slug ? (
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                          c.vertical_slug === "ale"
                            ? "bg-blue-50 text-blue-700"
                            : c.vertical_slug === "restoration"
                            ? "bg-green-50 text-green-700"
                            : c.vertical_slug === "legal"
                            ? "bg-purple-50 text-purple-700"
                            : "bg-gray-100 text-gray-500"
                        }`}
                      >
                        {c.vertical_slug}
                      </span>
                    ) : (
                      <span className="text-xs text-gray-400">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={`/admin/contracts/${c.id}`}
                      className="text-sm font-medium text-blue-600 hover:text-blue-800"
                    >
                      View →
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
