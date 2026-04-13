"use client";

/**
 * Supplier Scorecard — per-supplier performance KPIs for QBR and vendor management.
 *
 * Route: /admin/suppliers/[id]
 * Fetches: GET /admin/analytics/supplier-scorecard/{id}
 */

import { useParams } from "next/navigation";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
} from "recharts";
import { getSupplierScorecard } from "@/lib/api";
import type { SupplierScorecard } from "@/lib/types";

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatCurrency(val: string | number): string {
  const n = typeof val === "string" ? parseFloat(val) : val;
  if (isNaN(n)) return "$0.00";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n);
}

function formatPct(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`;
}

const STATUS_COLORS: Record<string, string> = {
  APPROVED:               "#10B981",
  EXPORTED:               "#6B7280",
  REVIEW_REQUIRED:        "#EF4444",
  PENDING_CARRIER_REVIEW: "#F59E0B",
  CARRIER_REVIEWING:      "#3B82F6",
  SUPPLIER_RESPONDED:     "#8B5CF6",
  DISPUTED:               "#F97316",
  WITHDRAWN:              "#9CA3AF",
  SUBMITTED:              "#60A5FA",
  PROCESSING:             "#A5B4FC",
  DRAFT:                  "#D1D5DB",
};

const STATUS_FRIENDLY: Record<string, string> = {
  APPROVED:               "Approved",
  EXPORTED:               "Paid",
  REVIEW_REQUIRED:        "Exceptions Flagged",
  PENDING_CARRIER_REVIEW: "Awaiting Approval",
  CARRIER_REVIEWING:      "Awaiting Approval",
  SUPPLIER_RESPONDED:     "Supplier Replied",
  DISPUTED:               "Disputed",
  WITHDRAWN:              "Withdrawn",
  SUBMITTED:              "AI Processing",
  PROCESSING:             "AI Processing",
  DRAFT:                  "Draft",
};

const EXCEPTION_TYPE_COLORS: Record<string, string> = {
  RATE:           "#EF4444",
  GUIDELINE:      "#F97316",
  CLASSIFICATION: "#8B5CF6",
};

// ── Metric card ───────────────────────────────────────────────────────────────

function KPI({
  label,
  value,
  sub,
  accent = "default",
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: "green" | "amber" | "red" | "blue" | "default";
}) {
  const accentClass: Record<string, string> = {
    green:   "text-green-700",
    amber:   "text-amber-700",
    red:     "text-red-700",
    blue:    "text-blue-700",
    default: "text-gray-900",
  };
  return (
    <div className="rounded-xl border bg-white px-5 py-4 shadow-sm">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
      <p className={`mt-1 text-2xl font-bold tabular-nums ${accentClass[accent]}`}>{value}</p>
      {sub && <p className="mt-0.5 text-xs text-gray-400">{sub}</p>}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SupplierScorecardPage() {
  const { id } = useParams<{ id: string }>();

  const { data: scorecard, isLoading, error } = useQuery<SupplierScorecard>({
    queryKey: ["supplier-scorecard", id],
    queryFn: () => getSupplierScorecard(id),
    enabled: !!id,
  });

  if (isLoading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
      </div>
    );
  }

  if (error || !scorecard) {
    return (
      <div className="space-y-4">
        <Link href="/admin/suppliers" className="text-sm font-medium text-blue-600 hover:text-blue-800">
          ← Back to Suppliers
        </Link>
        <div className="rounded-xl border border-red-200 bg-red-50 px-5 py-8 text-center">
          <p className="text-sm font-medium text-red-700">Could not load scorecard for this supplier.</p>
        </div>
      </div>
    );
  }

  // Invoice status chart data
  const statusChartData = Object.entries(scorecard.invoice_status_counts)
    .filter(([, count]) => count > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([status, count]) => ({
      status: STATUS_FRIENDLY[status] ?? status.replace(/_/g, " "),
      count,
      fill: STATUS_COLORS[status] ?? "#9CA3AF",
    }));

  // Exception type chart data
  const excChartData = scorecard.top_exception_types.map((e) => ({
    type: e.validation_type,
    count: e.count,
    fill: EXCEPTION_TYPE_COLORS[e.validation_type] ?? "#6B7280",
  }));

  // Rate-colour helpers
  const excRatePct = scorecard.exception_rate * 100;
  const autoApprPct = scorecard.auto_approval_rate * 100;

  return (
    <div className="space-y-6">
      {/* Back + header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <Link href="/admin/suppliers" className="text-xs font-medium text-blue-600 hover:text-blue-800">
            ← All Suppliers
          </Link>
          <h1 className="mt-1 text-2xl font-bold text-gray-900">
            {scorecard.supplier_name}
          </h1>
          <p className="mt-0.5 text-sm text-gray-500">
            Supplier Scorecard · {scorecard.total_invoices} invoice{scorecard.total_invoices !== 1 ? "s" : ""} on record
          </p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <Link
            href={`/admin/invoices?supplier=${id}`}
            className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 hover:border-blue-200 hover:text-blue-700 transition-all"
          >
            View Invoices →
          </Link>
          <Link
            href={`/admin/contracts?supplier_id=${id}`}
            className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 hover:border-blue-200 hover:text-blue-700 transition-all"
          >
            Contracts →
          </Link>
        </div>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KPI
          label="Total Billed"
          value={formatCurrency(scorecard.total_billed)}
          sub="All processed invoices"
          accent="blue"
        />
        <KPI
          label="Identified Savings"
          value={formatCurrency(scorecard.total_savings)}
          sub="Billed minus contracted rate"
          accent={parseFloat(scorecard.total_savings) > 0 ? "amber" : "green"}
        />
        <KPI
          label="Exception Rate"
          value={formatPct(scorecard.exception_rate)}
          sub={`${scorecard.total_exceptions} exceptions total`}
          accent={excRatePct > 50 ? "red" : excRatePct > 20 ? "amber" : "green"}
        />
        <KPI
          label="Auto-Approval Rate"
          value={formatPct(scorecard.auto_approval_rate)}
          sub="Clean invoices approved on first pass"
          accent={autoApprPct >= 70 ? "green" : autoApprPct >= 40 ? "amber" : "red"}
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Invoice status distribution */}
        <div className="rounded-xl border bg-white p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-900">Invoice Status Breakdown</h2>
          <p className="text-xs text-gray-400 mt-0.5">Counts by current status</p>
          {statusChartData.length === 0 ? (
            <p className="mt-8 text-center text-sm text-gray-400">No invoices yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart
                data={statusChartData}
                layout="vertical"
                margin={{ top: 8, right: 24, left: 8, bottom: 8 }}
              >
                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 10 }} allowDecimals={false} />
                <YAxis type="category" dataKey="status" width={148} tick={{ fontSize: 9 }} />
                <Tooltip formatter={(v: number) => [v, "Invoices"]} />
                <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                  {statusChartData.map((entry, i) => (
                    <Cell key={i} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Exception types */}
        <div className="rounded-xl border bg-white p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-900">Top Exception Types</h2>
          <p className="text-xs text-gray-400 mt-0.5">Where billing issues originate</p>
          {excChartData.length === 0 ? (
            <p className="mt-8 text-center text-sm text-gray-400">No exceptions on record — clean supplier! ✓</p>
          ) : (
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={excChartData} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="type" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                <Tooltip formatter={(v: number) => [v, "Exceptions"]} />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {excChartData.map((entry, i) => (
                    <Cell key={i} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}

          {/* Exception rate context */}
          <div className="mt-4 border-t pt-3 space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span className="text-gray-500">Total exceptions</span>
              <span className="font-semibold text-gray-900">{scorecard.total_exceptions}</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-gray-500">Exception rate</span>
              <span className={`font-semibold ${excRatePct > 50 ? "text-red-600" : excRatePct > 20 ? "text-amber-600" : "text-green-700"}`}>
                {formatPct(scorecard.exception_rate)}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Top billed services */}
      <div className="rounded-xl border bg-white shadow-sm">
        <div className="border-b px-5 py-4">
          <h2 className="text-sm font-semibold text-gray-900">Top Billed Services</h2>
          <p className="text-xs text-gray-400 mt-0.5">Top 5 taxonomy codes by total billed amount</p>
        </div>
        {scorecard.top_taxonomy_codes.length === 0 ? (
          <div className="px-5 py-8 text-center">
            <p className="text-sm text-gray-400">No classified lines yet.</p>
          </div>
        ) : (
          <div className="p-5 space-y-3">
            {(() => {
              const maxBilled = Math.max(...scorecard.top_taxonomy_codes.map(c => parseFloat(c.total_billed)));
              return scorecard.top_taxonomy_codes.map((code, i) => {
                const billed = parseFloat(code.total_billed);
                const pct = maxBilled > 0 ? (billed / maxBilled) * 100 : 0;
                return (
                  <div key={code.taxonomy_code}>
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <span className="w-5 text-right text-xs text-gray-400 font-mono">{i + 1}</span>
                        <span className="font-mono text-xs text-gray-700 bg-gray-100 px-1.5 py-0.5 rounded">{code.taxonomy_code}</span>
                        <span className="text-xs text-gray-600">{code.label ?? "—"}</span>
                      </div>
                      <div className="flex items-center gap-3 text-xs">
                        <span className="text-gray-400">{code.line_count} line{code.line_count !== 1 ? "s" : ""}</span>
                        <span className="font-semibold text-gray-900">{formatCurrency(code.total_billed)}</span>
                      </div>
                    </div>
                    <div className="h-1.5 rounded-full bg-gray-100 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-blue-400 transition-all"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              });
            })()}
          </div>
        )}
      </div>

      {/* Footer quick links */}
      <div className="flex items-center gap-4 text-xs text-gray-400">
        <Link href={`/admin/invoices?supplier=${id}`} className="hover:text-blue-600 transition-colors">
          All invoices for this supplier →
        </Link>
        <Link href={`/admin/contracts?supplier_id=${id}`} className="hover:text-blue-600 transition-colors">
          Manage contracts →
        </Link>
        <Link href="/admin/analytics" className="hover:text-blue-600 transition-colors">
          ← Back to Analytics
        </Link>
      </div>
    </div>
  );
}
