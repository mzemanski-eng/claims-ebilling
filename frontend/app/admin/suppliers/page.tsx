"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { listAdminSuppliers } from "@/lib/api";

export default function AdminSuppliersPage() {
  const { data: suppliers, isLoading } = useQuery({
    queryKey: ["admin-suppliers"],
    queryFn: listAdminSuppliers,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Suppliers</h1>
          <p className="mt-1 text-sm text-gray-500">
            {suppliers?.length ?? 0} suppliers on record
          </p>
        </div>
        <Link
          href="/admin/invoices"
          className="text-sm font-medium text-blue-600 hover:text-blue-800"
        >
          ← Invoice Queue
        </Link>
      </div>

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
          </div>
        ) : suppliers?.length === 0 ? (
          <div className="py-16 text-center text-sm text-gray-400">
            No suppliers found. Run the seed script to add demo data.
          </div>
        ) : (
          <table className="min-w-full divide-y divide-gray-100">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Supplier Name
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Tax ID
                </th>
                <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Contracts
                </th>
                <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Invoices
                </th>
                <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Active
                </th>
                <th className="w-32" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {suppliers?.map((s) => (
                <tr key={s.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 font-medium text-gray-900">
                    {s.name}
                  </td>
                  <td className="px-4 py-3 font-mono text-sm text-gray-500">
                    {s.tax_id ?? "—"}
                  </td>
                  <td className="px-4 py-3 text-center text-sm text-gray-700">
                    {s.contract_count}
                  </td>
                  <td className="px-4 py-3 text-center text-sm text-gray-700">
                    {s.invoice_count}
                  </td>
                  <td className="px-4 py-3 text-center">
                    {s.is_active ? (
                      <span className="inline-flex rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                        Active
                      </span>
                    ) : (
                      <span className="inline-flex rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">
                        Inactive
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={`/admin/invoices?supplier=${s.id}`}
                      className="text-sm font-medium text-blue-600 hover:text-blue-800"
                    >
                      View invoices →
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
