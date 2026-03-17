"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { bulkApproveInvoices, listAdminInvoices, listAdminSuppliers } from "@/lib/api";
import { StatusBadge } from "@/components/status-badge";
import type { BulkApprovalResult } from "@/lib/types";

// ── Risk Badge ────────────────────────────────────────────────────────────────

const RISK_CONFIG: Record<string, { dot: string; label: string; text: string }> = {
  LOW:      { dot: "bg-green-400",  label: "LOW",      text: "text-green-700" },
  MEDIUM:   { dot: "bg-amber-400",  label: "MED",      text: "text-amber-700" },
  HIGH:     { dot: "bg-red-500",    label: "HIGH",     text: "text-red-700"   },
  CRITICAL: { dot: "bg-red-600",    label: "CRIT",     text: "text-red-800"   },
};

function RiskBadge({ level }: { level: string | null }) {
  if (!level) return <span className="text-gray-300 text-xs">—</span>;
  const cfg = RISK_CONFIG[level] ?? RISK_CONFIG.MEDIUM;
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-semibold ${cfg.text}`}>
      <span className={`inline-block h-2 w-2 rounded-full ${cfg.dot}`} />
      {cfg.label}
    </span>
  );
}

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

/** Statuses that a carrier admin can approve in bulk. */
const APPROVABLE_STATUSES = new Set(["PENDING_CARRIER_REVIEW", "CARRIER_REVIEWING"]);

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AdminInvoicesPage() {
  const queryClient = useQueryClient();

  // ── Filter state — initialise from URL search params ──────────────────────
  const [activeTab,  setActiveTab]  = useState<StatusTab>("PENDING_CARRIER_REVIEW");
  const [search,     setSearch]     = useState("");
  const [supplierId, setSupplierId] = useState("");
  const [dateFrom,   setDateFrom]   = useState("");
  const [dateTo,     setDateTo]     = useState("");

  // Debounce search — fire query 300 ms after user stops typing
  const [debouncedSearch, setDebouncedSearch] = useState(search);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function handleSearchChange(value: string) {
    setSearch(value);
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => setDebouncedSearch(value), 300);
  }

  const hasActiveFilters = !!(debouncedSearch || supplierId || dateFrom || dateTo);

  function clearFilters() {
    setSearch("");
    setDebouncedSearch("");
    setSupplierId("");
    setDateFrom("");
    setDateTo("");
  }

  // ── Bulk-selection state ───────────────────────────────────────────────────
  const [selectedIds,  setSelectedIds]  = useState<Set<string>>(new Set());
  const [bulkResult,   setBulkResult]   = useState<BulkApprovalResult | null>(null);

  // Clear selection + result banner whenever the filter set changes
  useEffect(() => {
    setSelectedIds(new Set());
    setBulkResult(null);
  }, [activeTab, debouncedSearch, supplierId, dateFrom, dateTo]);

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

  // ── Derived selection helpers ──────────────────────────────────────────────
  const approvableInvoices = (invoices ?? []).filter((inv) =>
    APPROVABLE_STATUSES.has(inv.status),
  );

  const allApprovableSelected =
    approvableInvoices.length > 0 &&
    approvableInvoices.every((inv) => selectedIds.has(inv.id));

  const someSelected = selectedIds.size > 0;

  function toggleSelectAll() {
    if (allApprovableSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(approvableInvoices.map((inv) => inv.id)));
    }
  }

  function toggleRow(id: string, approvable: boolean) {
    if (!approvable) return;
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  // ── Bulk approve mutation ──────────────────────────────────────────────────
  const bulkMutation = useMutation({
    mutationFn: () => bulkApproveInvoices(Array.from(selectedIds)),
    onSuccess: (result) => {
      setBulkResult(result);
      setSelectedIds(new Set());
      queryClient.invalidateQueries({ queryKey: ["admin-invoices"] });
    },
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

      {/* Bulk result banner */}
      {bulkResult && (
        <div className="flex items-center justify-between rounded-lg border border-green-200 bg-green-50 px-4 py-3">
          <span className="text-sm font-medium text-green-800">
            ✓ Approved {bulkResult.approved} invoice
            {bulkResult.approved !== 1 ? "s" : ""}
            {bulkResult.skipped > 0 && (
              <span className="ml-1 font-normal text-green-600">
                ({bulkResult.skipped} skipped — already processed)
              </span>
            )}
          </span>
          <button
            onClick={() => setBulkResult(null)}
            className="text-green-500 hover:text-green-700 text-lg leading-none"
            aria-label="Dismiss"
          >
            ×
          </button>
        </div>
      )}

      {/* Bulk approve error banner */}
      {bulkMutation.isError && (
        <div className="flex items-center justify-between rounded-lg border border-red-200 bg-red-50 px-4 py-3">
          <span className="text-sm font-medium text-red-800">
            Bulk approval failed — please try again.
          </span>
          <button
            onClick={() => bulkMutation.reset()}
            className="text-red-400 hover:text-red-600 text-lg leading-none"
            aria-label="Dismiss"
          >
            ×
          </button>
        </div>
      )}

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

      {/* Bulk action bar — visible only when items are selected */}
      {someSelected && (
        <div className="flex items-center justify-between rounded-lg border border-blue-200 bg-blue-50 px-4 py-3">
          <span className="text-sm font-medium text-blue-900">
            {selectedIds.size} invoice{selectedIds.size !== 1 ? "s" : ""} selected
          </span>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSelectedIds(new Set())}
              className="text-sm text-blue-600 hover:text-blue-800"
            >
              Clear selection
            </button>
            <button
              onClick={() => bulkMutation.mutate()}
              disabled={bulkMutation.isPending}
              className="rounded-md bg-blue-600 px-4 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {bulkMutation.isPending
                ? "Approving…"
                : `Approve ${selectedIds.size} Invoice${selectedIds.size !== 1 ? "s" : ""}`}
            </button>
          </div>
        </div>
      )}

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
                {/* Select-all checkbox — only functional when approvable rows exist */}
                <th className="w-10 px-4 py-3">
                  {approvableInvoices.length > 0 && (
                    <input
                      type="checkbox"
                      checked={allApprovableSelected}
                      onChange={toggleSelectAll}
                      aria-label="Select all approvable invoices"
                      className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
                    />
                  )}
                </th>
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
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Risk
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
              {invoices?.map((inv) => {
                const approvable = APPROVABLE_STATUSES.has(inv.status);
                const checked    = selectedIds.has(inv.id);
                return (
                  <tr
                    key={inv.id}
                    className={`transition-colors ${
                      checked
                        ? "bg-blue-50"
                        : "hover:bg-gray-50"
                    }`}
                  >
                    {/* Per-row checkbox */}
                    <td className="px-4 py-3">
                      {approvable ? (
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleRow(inv.id, approvable)}
                          aria-label={`Select invoice ${inv.invoice_number}`}
                          className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
                        />
                      ) : (
                        <span className="block h-4 w-4" />
                      )}
                    </td>
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
                    <td className="px-4 py-3">
                      <RiskBadge level={inv.triage_risk_level} />
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
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
