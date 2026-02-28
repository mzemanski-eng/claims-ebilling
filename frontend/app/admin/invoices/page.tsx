"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { listAdminInvoices, listAdminSuppliers } from "@/lib/api";
import { StatusBadge } from "@/components/status-badge";

// ── Constants ─────────────────────────────────────────────────────────────────

const STATUS_TABS = [
  { label: "All",                value: undefined },
  { label: "Pending Review",     value: "PENDING_CARRIER_REVIEW" },
  { label: "Needs Changes",      value: "REVIEW_REQUIRED" },
  { label: "Supplier Responded", value: "SUPPLIER_RESPONDED" },
  { label: "Approved",           value: "APPROVED" },
  { label: "Exported",           value: "EXPORTED" },
] as const;

type StatusTab = (typeof STATUS_TABS)[number]["value"];

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AdminInvoicesPage() {
  const router       = useRouter();
  const searchParams = useSearchParams();

  // ── Filter state — initialise from URL ─────────────────────────────────────
  const [activeTab,  setActiveTab]  = useState<StatusTab>(
    (searchParams.get("status") as StatusTab) ?? "PENDING_CARRIER_REVIEW",
  );
  const [search,     setSearch]     = useState(searchParams.get("search")      ?? "");
  const [supplierId, setSupplierId] = useState(searchParams.get("supplier_id") ?? "");
  const [dateFrom,   setDateFrom]   = useState(searchParams.get("date_from")   ?? "");
  const [dateTo,     setDateTo]     = useState(searchParams.get("date_to")     ?? "");

  // Debounce search — fire query 300 ms after user stops typing
  const [debouncedSearch, setDebouncedSearch] = useState(search);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function handleSearchChange(value: string) {
    setSearch(value);
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => setDebouncedSearch(value), 300);
  }

  // ── Sync URL when filters change ───────────────────────────────────────────
  useEffect(() => {
    const qs = new URLSearchParams();
    if (activeTab)        qs.set("status",      activeTab);
    if (debouncedSearch)  qs.set("search",      debouncedSearch);
    if (supplierId)       qs.set("supplier_id", supplierId);
    if (dateFrom)         qs.set("date_from",   dateFrom);
    if (dateTo)           qs.set("date_to",     dateTo);
    router.replace(`?${qs.toString()}`, { scroll: false });
  }, [activeTab, debouncedSearch, supplierId, dateFrom, dateTo, router]);

  const hasActiveFilters = !!(debouncedSearch || supplierId || dateFrom || dateTo);

  function clearFilters() {
    setSearch("");
    setDebouncedSearch("");
    setSupplierId("");
    setDateFrom("");
    setDateTo("");
  }

  // ── Data queries ───────────────────────────────────────────────────────────
  const { data: invoices, isLoading } = useQuery({
    queryKey: ["admin-invoices", activeTab, debouncedSearch, supplierId, dateFrom, dateTo],
    queryFn: () =>
      listAdminInvoices({
        statusFilter: activeTab,
        search:       debouncedSearch || undefined,
        supplierId:   supplierId      || undefined,
        dateFrom:     dateFrom        || undefined,
        dateTo:       dateTo          || undefined,
      }),
    refetchInterval: 30_000,
  });

  const { data: suppliers } = useQuery({
    queryKey: ["admin-suppliers"],
    queryFn:  listAdminSuppliers,
    staleTime: 5 * 60 * 1000,
  });

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Invoice Queue</h1>
          <p className="mt-1 text-sm text-gray-500">
            {invoices?.length ?? 0} invoice{invoices?.length === 1 ? "" : "s"}
            {hasActiveFilters && (
              <span className="ml-1 text-gray-400">(filtered)</span>
            )}
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

      {/* Filter bar */}
      <div className="flex flex-wrap items-end gap-3 rounded-xl border bg-white p-4 shadow-sm">
        {/* Search */}
        <div className="flex-1 min-w-[180px]">
          <label className="mb-1 block text-xs font-medium text-gray-500">
            Invoice #
          </label>
          <input
            type="text"
            value={search}
            onChange={(e) => handleSearchChange(e.target.value)}
            placeholder="Search invoice number…"
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        {/* Supplier */}
        <div className="flex-1 min-w-[180px]">
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

        {/* Date from */}
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-500">
            Submitted from
          </label>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        {/* Date to */}
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-500">
            To
          </label>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        {/* Clear */}
        {hasActiveFilters && (
          <button
            onClick={clearFilters}
            className="rounded-md px-3 py-2 text-sm font-medium text-gray-500 hover:text-red-600 transition-colors"
          >
            Clear filters
          </button>
        )}
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
          <div className="py-16 text-center">
            <p className="text-sm text-gray-400">
              {hasActiveFilters
                ? "No invoices match the current filters."
                : "No invoices in this queue."}
            </p>
            {hasActiveFilters && (
              <button
                onClick={clearFilters}
                className="mt-2 text-sm font-medium text-blue-600 hover:text-blue-800"
              >
                Clear filters
              </button>
            )}
          </div>
        ) : (
          <table className="min-w-full divide-y divide-gray-100">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Invoice #
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Supplier
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Invoice Date
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
                    {inv.supplier_name ?? "—"}
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
