"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  getAnalyticsSummary,
  listAdminInvoices,
  getMappingReviewQueue,
} from "@/lib/api";
import { MetricCard } from "@/components/metric-card";
import { StatusBadge } from "@/components/status-badge";
import { getUserInfo, isCarrierAdmin } from "@/lib/auth";
import type { InvoiceListItem } from "@/lib/types";

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmt(value: string | number | null | undefined): string {
  const n = typeof value === "string" ? parseFloat(value) : Number(value ?? 0);
  if (isNaN(n)) return "$0";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);
}

// ── Invoice queue card ────────────────────────────────────────────────────────

function InvoiceQueueCard({
  title,
  subtitle,
  invoices,
  loading,
  viewAllHref,
  viewAllLabel,
  accent,
}: {
  title: string;
  subtitle: string;
  invoices: InvoiceListItem[] | undefined;
  loading: boolean;
  viewAllHref: string;
  viewAllLabel: string;
  accent: "red" | "green";
}) {
  const borderColor = accent === "red" ? "border-red-200" : "border-green-200";
  const headerColor = accent === "red" ? "text-red-700" : "text-green-700";
  const countBg    = accent === "red" ? "bg-red-100 text-red-700" : "bg-green-100 text-green-700";

  return (
    <div className={`rounded-xl border bg-white shadow-sm overflow-hidden ${borderColor}`}>
      {/* Header */}
      <div className="flex items-center justify-between border-b px-5 py-4">
        <div>
          <h2 className={`text-sm font-semibold ${headerColor}`}>{title}</h2>
          <p className="text-xs text-gray-400 mt-0.5">{subtitle}</p>
        </div>
        {invoices !== undefined && (
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${countBg}`}>
            {invoices.length}
          </span>
        )}
      </div>

      {/* Body */}
      {loading ? (
        <div className="flex justify-center py-8">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-gray-300 border-t-gray-600" />
        </div>
      ) : !invoices || invoices.length === 0 ? (
        <p className="py-8 text-center text-sm text-gray-400">Nothing here — all clear.</p>
      ) : (
        <ul className="divide-y divide-gray-100">
          {invoices.slice(0, 6).map((inv) => (
            <li key={inv.id}>
              <Link
                href={`/admin/invoices/${inv.id}`}
                className="flex items-center justify-between gap-3 px-5 py-3 hover:bg-gray-50 transition-colors group"
              >
                <div className="min-w-0">
                  <p className="font-mono text-xs font-semibold text-gray-900 truncate">
                    {inv.invoice_number}
                  </p>
                  <p className="text-xs text-gray-500 truncate mt-0.5">
                    {inv.supplier_name ?? "Unknown supplier"}
                  </p>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  {inv.total_billed && (
                    <span className="text-xs tabular-nums text-gray-700 font-medium">
                      {fmt(inv.total_billed)}
                    </span>
                  )}
                  {inv.exception_count > 0 && (
                    <span className="rounded-full bg-red-100 px-1.5 py-0.5 text-xs font-semibold text-red-700">
                      {inv.exception_count}
                    </span>
                  )}
                  <StatusBadge status={inv.status} />
                  <span className="text-gray-300 group-hover:text-gray-500 text-xs transition-colors">→</span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {/* Footer link */}
      <div className="border-t px-5 py-3">
        <Link
          href={viewAllHref}
          className="text-xs font-medium text-blue-600 hover:text-blue-800 transition-colors"
        >
          {viewAllLabel} →
        </Link>
      </div>
    </div>
  );
}

// ── Quick action button ───────────────────────────────────────────────────────

function QuickAction({
  href,
  icon,
  label,
  description,
}: {
  href: string;
  icon: string;
  label: string;
  description: string;
}) {
  return (
    <Link
      href={href}
      className="flex flex-col gap-1 rounded-xl border bg-white p-4 shadow-sm hover:border-blue-200 hover:shadow-md transition-all group"
    >
      <span className="text-xl">{icon}</span>
      <span className="text-sm font-semibold text-gray-900 group-hover:text-blue-700 transition-colors">
        {label}
      </span>
      <span className="text-xs text-gray-400">{description}</span>
    </Link>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AdminDashboard() {
  const user = getUserInfo();
  const isAdmin = isCarrierAdmin() || user?.role === "SYSTEM_ADMIN";

  const { data: summary, isLoading: loadingSummary } = useQuery({
    queryKey: ["analytics-summary"],
    queryFn: () => getAnalyticsSummary(),
  });

  const { data: flaggedInvoices, isLoading: loadingFlagged } = useQuery({
    queryKey: ["admin-invoices", "REVIEW_REQUIRED"],
    queryFn: () => listAdminInvoices({ statusFilter: "REVIEW_REQUIRED" }),
  });

  const { data: pendingInvoices, isLoading: loadingPending } = useQuery({
    queryKey: ["admin-invoices", "PENDING_CARRIER_REVIEW"],
    queryFn: () => listAdminInvoices({ statusFilter: "PENDING_CARRIER_REVIEW" }),
  });

  const { data: mappingQueue } = useQuery({
    queryKey: ["mapping-queue"],
    queryFn: getMappingReviewQueue,
  });

  // Approval rate: APPROVED / (APPROVED + REVIEW_REQUIRED + PENDING + EXPORTED)
  const approvalRateLabel = (() => {
    if (!summary?.invoice_status_counts) return "—";
    const counts = Object.fromEntries(
      summary.invoice_status_counts.map((s) => [s.status, s.count]),
    );
    const approved = (counts["APPROVED"] ?? 0) + (counts["EXPORTED"] ?? 0);
    const total =
      approved +
      (counts["REVIEW_REQUIRED"] ?? 0) +
      (counts["PENDING_CARRIER_REVIEW"] ?? 0) +
      (counts["CARRIER_REVIEWING"] ?? 0);
    if (total === 0) return "—";
    return `${Math.round((approved / total) * 100)}%`;
  })();

  const flaggedCount  = flaggedInvoices?.length ?? 0;
  const mappingCount  = mappingQueue?.length ?? 0;
  const hasAlerts     = flaggedCount > 0 || mappingCount > 0;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          {user?.role === "CARRIER_REVIEWER" ? "My Dashboard" : "Dashboard"}
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          {user?.carrier_name
            ? `${user.carrier_name} · Invoice processing overview`
            : "Invoice processing overview"}
        </p>
      </div>

      {/* Alert strip */}
      {hasAlerts && (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
          {flaggedCount > 0 && (
            <Link
              href="/admin/invoices?status=REVIEW_REQUIRED"
              className="flex flex-1 items-center gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 hover:bg-red-100 transition-colors"
            >
              <span className="text-lg">🚨</span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-red-800">
                  {flaggedCount} invoice{flaggedCount !== 1 ? "s" : ""} flagged for review
                </p>
                <p className="text-xs text-red-500">Unresolved validation exceptions · click to open queue</p>
              </div>
              <span className="shrink-0 text-xs font-semibold text-red-600">View →</span>
            </Link>
          )}
          {mappingCount > 0 && (
            <Link
              href="/admin/mappings"
              className="flex flex-1 items-center gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 hover:bg-amber-100 transition-colors"
            >
              <span className="text-lg">🗂</span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-amber-800">
                  {mappingCount} line{mappingCount !== 1 ? "s" : ""} need mapping review
                </p>
                <p className="text-xs text-amber-500">Low-confidence AI classifications · click to review</p>
              </div>
              <span className="shrink-0 text-xs font-semibold text-amber-600">Review →</span>
            </Link>
          )}
        </div>
      )}

      {/* KPI strip */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MetricCard
          label="Total ALAE Billed"
          value={fmt(summary?.total_billed)}
          sublabel="All processed invoices"
          accent="blue"
        />
        <MetricCard
          label="Identified Savings"
          value={fmt(summary?.total_savings)}
          sublabel="Rate enforcement variance"
          accent="amber"
        />
        <MetricCard
          label="Open Exceptions"
          value={String(summary?.open_exceptions ?? "—")}
          sublabel={`${summary?.total_exceptions ?? 0} total raised`}
          accent={(summary?.open_exceptions ?? 0) > 0 ? "red" : "green"}
        />
        <MetricCard
          label="Approval Rate"
          value={approvalRateLabel}
          sublabel="Approved + exported invoices"
          accent="green"
        />
      </div>

      {/* Invoice queues */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <InvoiceQueueCard
          title="⚠ Needs Attention"
          subtitle="Invoices with unresolved validation errors"
          invoices={flaggedInvoices}
          loading={loadingFlagged}
          viewAllHref="/admin/invoices?status=REVIEW_REQUIRED"
          viewAllLabel="View all flagged invoices"
          accent="red"
        />
        <InvoiceQueueCard
          title="✓ Ready to Approve"
          subtitle="Validated invoices awaiting carrier sign-off"
          invoices={pendingInvoices}
          loading={loadingPending}
          viewAllHref="/admin/invoices?status=PENDING_CARRIER_REVIEW"
          viewAllLabel="View all pending approval"
          accent="green"
        />
      </div>

      {/* Quick actions */}
      <div>
        <h2 className="mb-3 text-sm font-semibold text-gray-600 uppercase tracking-wide">
          Quick Actions
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <QuickAction
            href="/admin/invoices/new"
            icon="📄"
            label="Upload Invoice"
            description="Submit a new invoice for processing"
          />
          <QuickAction
            href="/admin/contracts"
            icon="📋"
            label="Contracts"
            description="Rate cards, guidelines & billing rules"
          />
          <QuickAction
            href="/admin/analytics"
            icon="📊"
            label="Analytics"
            description="Spend intelligence & exception trends"
          />
          <QuickAction
            href="/admin/mappings"
            icon="🗂"
            label="Mapping Queue"
            description="Review low-confidence classifications"
          />
        </div>
      </div>
    </div>
  );
}
