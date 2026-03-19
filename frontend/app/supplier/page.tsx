"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { listSupplierInvoices, listSupplierContracts } from "@/lib/api";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { getUserInfo } from "@/lib/auth";
import type { InvoiceListItem } from "@/lib/types";

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmt(val: string | number | null | undefined): string {
  const n = typeof val === "string" ? parseFloat(val) : Number(val ?? 0);
  if (isNaN(n)) return "$0";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);
}

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

// ── Status grouping ────────────────────────────────────────────────────────────

const STATUS_GROUPS = {
  action:   new Set(["REVIEW_REQUIRED", "DRAFT"]),
  progress: new Set(["SUBMITTED", "PROCESSING", "SUPPLIER_RESPONDED",
                     "PENDING_CARRIER_REVIEW", "CARRIER_REVIEWING"]),
  approved: new Set(["APPROVED", "EXPORTED"]),
  other:    new Set(["DISPUTED", "WITHDRAWN"]),
};

const STATUS_LABELS: Record<string, string> = {
  DRAFT:                  "Draft",
  SUBMITTED:              "Submitted",
  PROCESSING:             "Processing",
  REVIEW_REQUIRED:        "Action Required",
  SUPPLIER_RESPONDED:     "Response Submitted",
  PENDING_CARRIER_REVIEW: "Under Carrier Review",
  CARRIER_REVIEWING:      "Carrier Reviewing",
  APPROVED:               "Approved",
  DISPUTED:               "Disputed",
  EXPORTED:               "Payment Issued",
  WITHDRAWN:              "Withdrawn",
};

// ── Stat card ─────────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  sublabel,
  accent,
  href,
}: {
  label: string;
  value: string | number;
  sublabel?: string;
  accent: "red" | "amber" | "blue" | "green" | "gray";
  href?: string;
}) {
  const colors = {
    red:   "border-red-200 bg-red-50",
    amber: "border-amber-200 bg-amber-50",
    blue:  "border-blue-200 bg-blue-50",
    green: "border-green-200 bg-green-50",
    gray:  "border-gray-200 bg-white",
  };
  const valueColors = {
    red:   "text-red-700",
    amber: "text-amber-700",
    blue:  "text-blue-700",
    green: "text-green-700",
    gray:  "text-gray-700",
  };

  const inner = (
    <div className={`rounded-xl border p-5 ${colors[accent]} ${href ? "hover:shadow-md transition-shadow cursor-pointer" : ""}`}>
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</p>
      <p className={`mt-1 text-3xl font-bold tabular-nums ${valueColors[accent]}`}>{value}</p>
      {sublabel && <p className="mt-1 text-xs text-gray-400">{sublabel}</p>}
    </div>
  );

  return href ? <Link href={href}>{inner}</Link> : inner;
}

// ── Action-required row ───────────────────────────────────────────────────────

function ActionRow({ inv }: { inv: InvoiceListItem }) {
  return (
    <Link
      href={`/supplier/invoices/${inv.id}`}
      className="flex items-center justify-between gap-4 rounded-lg border border-orange-200 bg-orange-50 px-4 py-3 hover:bg-orange-100 transition-colors group"
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm font-semibold text-gray-900">{inv.invoice_number}</span>
          <StatusBadge status={inv.status} label={STATUS_LABELS[inv.status]} />
        </div>
        <p className="mt-0.5 text-xs text-orange-700">
          {inv.status === "REVIEW_REQUIRED"
            ? `Respond to ${inv.exception_count} exception${inv.exception_count !== 1 ? "s" : ""} to proceed`
            : "Upload invoice file to submit"}
        </p>
      </div>
      <div className="flex items-center gap-3 shrink-0">
        {inv.total_billed && (
          <span className="text-sm font-medium tabular-nums text-gray-700">
            {fmt(inv.total_billed)}
          </span>
        )}
        <span className="rounded-md bg-orange-600 px-3 py-1.5 text-xs font-semibold text-white group-hover:bg-orange-700 transition-colors">
          Respond →
        </span>
      </div>
    </Link>
  );
}

// ── Recent invoice row ────────────────────────────────────────────────────────

function RecentRow({ inv }: { inv: InvoiceListItem }) {
  return (
    <Link
      href={`/supplier/invoices/${inv.id}`}
      className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-gray-50 transition-colors group"
    >
      <div className="min-w-0">
        <p className="font-mono text-sm font-semibold text-gray-900 truncate">{inv.invoice_number}</p>
        <p className="text-xs text-gray-500 mt-0.5">Submitted {formatDate(inv.submitted_at)}</p>
      </div>
      <div className="flex items-center gap-3 shrink-0">
        {inv.total_billed && (
          <span className="text-xs tabular-nums text-gray-600 font-medium">{fmt(inv.total_billed)}</span>
        )}
        <StatusBadge status={inv.status} label={STATUS_LABELS[inv.status]} />
        <span className="text-gray-300 group-hover:text-gray-500 text-xs transition-colors">→</span>
      </div>
    </Link>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SupplierDashboard() {
  const user = getUserInfo();

  const { data: invoices, isLoading } = useQuery({
    queryKey: ["supplier-invoices"],
    queryFn: listSupplierInvoices,
  });

  const { data: contracts } = useQuery({
    queryKey: ["supplier-contracts"],
    queryFn: listSupplierContracts,
  });

  // Partition invoices into groups
  const { actionItems, inProgress, approvedTotal, recentOther } = useMemo(() => {
    if (!invoices) return { actionItems: [], inProgress: [], approvedTotal: 0, recentOther: [] };

    const actionItems = invoices.filter((i) => STATUS_GROUPS.action.has(i.status));
    const inProgress  = invoices.filter((i) => STATUS_GROUPS.progress.has(i.status));
    const approved    = invoices.filter((i) => STATUS_GROUPS.approved.has(i.status));
    const approvedTotal = approved.reduce(
      (sum, i) => sum + (i.total_billed ? parseFloat(i.total_billed) : 0),
      0
    );
    // Recent non-action items (newest first, cap at 5)
    const recentOther = invoices
      .filter((i) => !STATUS_GROUPS.action.has(i.status))
      .sort((a, b) => {
        const at = a.submitted_at ? new Date(a.submitted_at).getTime() : 0;
        const bt = b.submitted_at ? new Date(b.submitted_at).getTime() : 0;
        return bt - at;
      })
      .slice(0, 5);

    return { actionItems, inProgress, approvedTotal, recentOther };
  }, [invoices]);

  const greeting = (() => {
    const hour = new Date().getHours();
    if (hour < 12) return "Good morning";
    if (hour < 17) return "Good afternoon";
    return "Good evening";
  })();

  const supplierName = user?.supplier_name ?? "Supplier";

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {greeting}, {supplierName}
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            Here&apos;s your billing status at a glance
          </p>
        </div>
        <Link href="/supplier/invoices/new">
          <Button>+ New Invoice</Button>
        </Link>
      </div>

      {/* Action required banner */}
      {!isLoading && actionItems.length > 0 && (
        <div className="flex items-center gap-3 rounded-xl border border-orange-300 bg-orange-50 px-5 py-4">
          <span className="text-xl">⚠️</span>
          <div className="flex-1">
            <p className="text-sm font-semibold text-orange-800">
              {actionItems.length} invoice{actionItems.length !== 1 ? "s" : ""} need{actionItems.length === 1 ? "s" : ""} your attention
            </p>
            <p className="text-xs text-orange-600 mt-0.5">
              Respond to exceptions or upload missing files to keep your invoice moving.
            </p>
          </div>
          <Link href="/supplier/invoices" className="shrink-0 rounded-lg bg-orange-600 px-4 py-2 text-xs font-semibold text-white hover:bg-orange-700 transition-colors">
            View all →
          </Link>
        </div>
      )}

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Action Required"
          value={isLoading ? "…" : actionItems.length}
          sublabel="Need your response"
          accent={actionItems.length > 0 ? "red" : "gray"}
          href={actionItems.length > 0 ? "/supplier/invoices" : undefined}
        />
        <StatCard
          label="Under Review"
          value={isLoading ? "…" : inProgress.length}
          sublabel="Carrier is reviewing"
          accent="amber"
        />
        <StatCard
          label="Approved"
          value={isLoading ? "…" : fmt(approvedTotal)}
          sublabel="Total approved amount"
          accent="green"
        />
        <StatCard
          label="Active Contracts"
          value={contracts ? contracts.length : "…"}
          sublabel="Rate cards in effect"
          accent="blue"
          href="/supplier/invoices"
        />
      </div>

      {/* Action required list */}
      {!isLoading && actionItems.length > 0 && (
        <div>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Needs Your Attention
          </h2>
          <div className="space-y-2">
            {actionItems.map((inv) => (
              <ActionRow key={inv.id} inv={inv} />
            ))}
          </div>
        </div>
      )}

      {/* Recent submissions */}
      {!isLoading && recentOther.length > 0 && (
        <div>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Recent Submissions
          </h2>
          <div className="overflow-hidden rounded-xl border bg-white shadow-sm divide-y divide-gray-100">
            {recentOther.map((inv) => (
              <RecentRow key={inv.id} inv={inv} />
            ))}
            <div className="px-4 py-3">
              <Link
                href="/supplier/invoices"
                className="text-xs font-medium text-blue-600 hover:text-blue-800 transition-colors"
              >
                View all invoices →
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Empty state */}
      {!isLoading && (!invoices || invoices.length === 0) && (
        <div className="rounded-xl border-2 border-dashed border-gray-200 py-20 text-center">
          <p className="text-4xl">📄</p>
          <p className="mt-3 font-medium text-gray-700">No invoices yet</p>
          <p className="text-sm text-gray-400 mt-1">Submit your first invoice to get started.</p>
          <Link href="/supplier/invoices/new">
            <Button className="mt-4" variant="secondary">
              Submit your first invoice
            </Button>
          </Link>
        </div>
      )}

      {/* Active contracts */}
      {contracts && contracts.length > 0 && (
        <div>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Active Contracts
          </h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {contracts.map((c) => (
              <div
                key={c.id}
                className="rounded-xl border bg-white p-4 shadow-sm"
              >
                <p className="text-sm font-semibold text-gray-900">{c.name}</p>
                <p className="text-xs text-gray-400 mt-1">
                  Effective {formatDate(c.effective_from)}
                  {c.effective_to ? ` – ${formatDate(c.effective_to)}` : " · No expiry"}
                </p>
                <div className="mt-3 flex gap-3 text-xs text-gray-500">
                  <span>{c.rate_cards?.length ?? 0} rate cards</span>
                  <span>·</span>
                  <span>{c.guidelines?.length ?? 0} guidelines</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
