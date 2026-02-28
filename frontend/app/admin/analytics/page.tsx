"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";
import { MetricCard } from "@/components/metric-card";
import {
  getAnalyticsSummary,
  getSpendByDomain,
  getSpendBySupplier,
  getSpendByTaxonomy,
  getExceptionBreakdown,
} from "@/lib/api";
import type { SpendByTaxonomy } from "@/lib/types";

// ── Constants ─────────────────────────────────────────────────────────────────

const DOMAIN_LABELS: Record<string, string> = {
  IME:     "Independent Medical Exam",
  ENG:     "Engineering & Forensic",
  IA:      "Independent Adjusting",
  INV:     "Investigation & Surveillance",
  REC:     "Record Retrieval",
  XDOMAIN: "Cross-Domain / Admin",
};

const DOMAIN_COLORS: Record<string, string> = {
  IME:     "#3B82F6",
  ENG:     "#F59E0B",
  IA:      "#8B5CF6",
  INV:     "#EF4444",
  REC:     "#10B981",
  XDOMAIN: "#6B7280",
};

const DOMAIN_ORDER = ["IME", "ENG", "IA", "INV", "REC", "XDOMAIN"];

// Statuses to show in the bar chart (excludes DRAFT and PROCESSING noise)
const STATUS_ORDER = [
  "REVIEW_REQUIRED",
  "PENDING_CARRIER_REVIEW",
  "CARRIER_REVIEWING",
  "SUPPLIER_RESPONDED",
  "APPROVED",
  "DISPUTED",
  "EXPORTED",
  "WITHDRAWN",
  "SUBMITTED",
];

const STATUS_COLORS: Record<string, string> = {
  REVIEW_REQUIRED:        "#EF4444",
  PENDING_CARRIER_REVIEW: "#F59E0B",
  CARRIER_REVIEWING:      "#3B82F6",
  SUPPLIER_RESPONDED:     "#8B5CF6",
  APPROVED:               "#10B981",
  DISPUTED:               "#F97316",
  EXPORTED:               "#6B7280",
  WITHDRAWN:              "#9CA3AF",
  SUBMITTED:              "#60A5FA",
};

const EXCEPTION_COLORS: Record<string, string> = {
  RATE:           "#EF4444",
  GUIDELINE:      "#F97316",
  CLASSIFICATION: "#8B5CF6",
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatCurrency(value: string | number): string {
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) return "$0.00";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num);
}

function formatCurrencyShort(value: number): string {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(0)}K`;
  return formatCurrency(value);
}

// ── Tooltip components ────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function DomainTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="rounded-lg border bg-white p-3 shadow-md">
      <p className="text-xs font-semibold text-gray-900 mb-1">{d.name}</p>
      <p className="text-xs text-gray-600">Billed: {formatCurrency(d.value)}</p>
      <p className="text-xs text-gray-600">Approved: {formatCurrency(d.approved)}</p>
      <p className="text-xs text-gray-400">{d.line_count} lines</p>
    </div>
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function SupplierTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border bg-white p-3 shadow-md">
      <p className="text-xs font-semibold text-gray-900 mb-1">{label}</p>
      {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
      {payload.map((p: any) => (
        <p key={p.name} className="text-xs" style={{ color: p.fill }}>
          {p.name}: {formatCurrency(p.value)}
        </p>
      ))}
    </div>
  );
}

// ── Sort types ────────────────────────────────────────────────────────────────

type SortKey = "taxonomy_code" | "label" | "line_count" | "total_billed" | "total_approved" | "variance";
type SortDir = "asc" | "desc";

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AdminAnalyticsPage() {
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>({
    key: "total_billed",
    dir: "desc",
  });

  const { data: summary, isLoading: loadingSummary } = useQuery({
    queryKey: ["analytics-summary"],
    queryFn: getAnalyticsSummary,
  });
  const { data: byDomain, isLoading: loadingDomain } = useQuery({
    queryKey: ["analytics-by-domain"],
    queryFn: getSpendByDomain,
  });
  const { data: bySupplier, isLoading: loadingSupplier } = useQuery({
    queryKey: ["analytics-by-supplier"],
    queryFn: getSpendBySupplier,
  });
  const { data: byTaxonomy, isLoading: loadingTaxonomy } = useQuery({
    queryKey: ["analytics-by-taxonomy"],
    queryFn: getSpendByTaxonomy,
  });
  const { data: exBreakdown, isLoading: loadingEx } = useQuery({
    queryKey: ["analytics-exceptions"],
    queryFn: getExceptionBreakdown,
  });

  const isLoading =
    loadingSummary || loadingDomain || loadingSupplier || loadingTaxonomy || loadingEx;

  // ── Derived data ────────────────────────────────────────────────────────────

  // Domain pie chart data — sorted by DOMAIN_ORDER for consistent layout
  const domainPieData = (byDomain ?? [])
    .sort(
      (a, b) =>
        DOMAIN_ORDER.indexOf(a.domain) - DOMAIN_ORDER.indexOf(b.domain),
    )
    .map((d) => ({
      name: DOMAIN_LABELS[d.domain] ?? d.domain,
      value: parseFloat(d.total_billed),
      approved: parseFloat(d.total_approved),
      domain: d.domain,
      line_count: d.line_count,
    }));

  // Invoice status bar data — filter and sort by STATUS_ORDER
  const statusBarData = (summary?.invoice_status_counts ?? [])
    .filter(
      (s) =>
        s.status !== "DRAFT" && s.status !== "PROCESSING" && s.count > 0,
    )
    .sort(
      (a, b) =>
        STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status),
    )
    .map((s) => ({
      status: s.status.replace(/_/g, " "),
      count: s.count,
      fill: STATUS_COLORS[s.status] ?? "#9CA3AF",
    }));

  // Supplier chart data
  const supplierChartData = (bySupplier ?? []).map((s) => ({
    name: s.supplier_name,
    Billed: parseFloat(s.total_billed),
    Approved: parseFloat(s.total_approved),
  }));
  const supplierChartHeight = Math.max(200, (bySupplier?.length ?? 0) * 52 + 40);

  // Exception chart data
  const exChartData = (exBreakdown ?? []).map((e) => ({
    type: e.validation_type,
    count: e.count,
    fill: EXCEPTION_COLORS[e.validation_type] ?? "#6B7280",
  }));

  // Taxonomy table — sortable + grouped by domain
  const sortedTaxonomy = [...(byTaxonomy ?? [])].sort(
    (a: SpendByTaxonomy, b: SpendByTaxonomy) => {
      let va: number | string = 0;
      let vb: number | string = 0;
      switch (sort.key) {
        case "taxonomy_code":
          va = a.taxonomy_code;
          vb = b.taxonomy_code;
          break;
        case "label":
          va = a.label ?? "";
          vb = b.label ?? "";
          break;
        case "line_count":
          va = a.line_count;
          vb = b.line_count;
          break;
        case "total_billed":
          va = parseFloat(a.total_billed);
          vb = parseFloat(b.total_billed);
          break;
        case "total_approved":
          va = parseFloat(a.total_approved);
          vb = parseFloat(b.total_approved);
          break;
        case "variance":
          va = parseFloat(a.total_billed) - parseFloat(a.total_approved);
          vb = parseFloat(b.total_billed) - parseFloat(b.total_approved);
          break;
      }
      if (va < vb) return sort.dir === "asc" ? -1 : 1;
      if (va > vb) return sort.dir === "asc" ? 1 : -1;
      return 0;
    },
  );

  // Group taxonomy rows by domain
  const taxonomyByDomain: Record<string, SpendByTaxonomy[]> = {};
  sortedTaxonomy.forEach((row) => {
    const domain = row.domain ?? "Unknown";
    if (!taxonomyByDomain[domain]) taxonomyByDomain[domain] = [];
    taxonomyByDomain[domain].push(row);
  });

  function toggleSort(key: SortKey) {
    setSort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === "desc" ? "asc" : "desc" }
        : { key, dir: "desc" },
    );
  }

  function SortIcon({ col }: { col: SortKey }) {
    if (sort.key !== col)
      return <span className="ml-1 text-gray-300">↕</span>;
    return (
      <span className="ml-1 text-blue-500">
        {sort.dir === "desc" ? "↓" : "↑"}
      </span>
    );
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Analytics</h1>
        <p className="mt-1 text-sm text-gray-500">
          Claims ALAE spend intelligence — all-time baseline
        </p>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-24">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
        </div>
      ) : (
        <>
          {/* ── Section 1: KPI cards ─────────────────────────────────────── */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <MetricCard
              label="Total ALAE Billed"
              value={formatCurrency(summary?.total_billed ?? "0")}
              sublabel="All non-draft invoices"
              accent="blue"
            />
            <MetricCard
              label="Total Approved / Payable"
              value={formatCurrency(summary?.total_approved ?? "0")}
              sublabel="Approved + exported invoices"
              accent="green"
            />
            <MetricCard
              label="Identified Savings"
              value={formatCurrency(summary?.total_savings ?? "0")}
              sublabel="Rate enforcement variance"
              accent="amber"
            />
            <MetricCard
              label="Open Exceptions"
              value={String(summary?.open_exceptions ?? 0)}
              sublabel={`${summary?.total_exceptions ?? 0} total exceptions`}
              accent={
                (summary?.open_exceptions ?? 0) > 0 ? "red" : "green"
              }
            />
          </div>

          {/* ── Section 2: Domain donut + Invoice status ─────────────────── */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* Domain pie chart */}
            <div className="rounded-xl border bg-white p-5 shadow-sm">
              <h2 className="text-sm font-semibold text-gray-900">
                Spend by Service Domain
              </h2>
              <p className="text-xs text-gray-400 mt-0.5">
                Billed amount by service category (classified lines only)
              </p>
              {domainPieData.length === 0 ? (
                <p className="mt-8 text-center text-sm text-gray-400">
                  No classified spend data yet.
                </p>
              ) : (
                <ResponsiveContainer width="100%" height={280}>
                  <PieChart>
                    <Pie
                      data={domainPieData}
                      cx="50%"
                      cy="50%"
                      innerRadius={70}
                      outerRadius={110}
                      paddingAngle={2}
                      dataKey="value"
                    >
                      {domainPieData.map((entry) => (
                        <Cell
                          key={entry.domain}
                          fill={DOMAIN_COLORS[entry.domain] ?? "#9CA3AF"}
                        />
                      ))}
                    </Pie>
                    <Tooltip content={<DomainTooltip />} />
                    <Legend
                      formatter={(value: string) => (
                        <span className="text-xs text-gray-700">{value}</span>
                      )}
                    />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>

            {/* Invoice status bar chart */}
            <div className="rounded-xl border bg-white p-5 shadow-sm">
              <h2 className="text-sm font-semibold text-gray-900">
                Invoice Status Distribution
              </h2>
              <p className="text-xs text-gray-400 mt-0.5">
                Count of invoices by current status
              </p>
              {statusBarData.length === 0 ? (
                <p className="mt-8 text-center text-sm text-gray-400">
                  No invoice data yet.
                </p>
              ) : (
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart
                    data={statusBarData}
                    layout="vertical"
                    margin={{ top: 8, right: 24, left: 8, bottom: 8 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" tick={{ fontSize: 11 }} />
                    <YAxis
                      type="category"
                      dataKey="status"
                      width={148}
                      tick={{ fontSize: 10 }}
                    />
                    <Tooltip
                      formatter={(value: number) => [value, "Invoices"]}
                    />
                    <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                      {statusBarData.map((entry, idx) => (
                        <Cell key={idx} fill={entry.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          {/* ── Section 3: Supplier spend + Exception breakdown ───────────── */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
            {/* Supplier spend (60%) */}
            <div className="rounded-xl border bg-white p-5 shadow-sm lg:col-span-3">
              <h2 className="text-sm font-semibold text-gray-900">
                Spend by Supplier
              </h2>
              <p className="text-xs text-gray-400 mt-0.5">
                Billed vs. approved per supplier
              </p>
              {supplierChartData.length === 0 ? (
                <p className="mt-8 text-center text-sm text-gray-400">
                  No supplier spend data yet.
                </p>
              ) : (
                <ResponsiveContainer
                  width="100%"
                  height={supplierChartHeight}
                >
                  <BarChart
                    data={supplierChartData}
                    layout="vertical"
                    margin={{ top: 8, right: 24, left: 8, bottom: 8 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis
                      type="number"
                      tickFormatter={formatCurrencyShort}
                      tick={{ fontSize: 10 }}
                    />
                    <YAxis
                      type="category"
                      dataKey="name"
                      width={140}
                      tick={{ fontSize: 10 }}
                    />
                    <Tooltip content={<SupplierTooltip />} />
                    <Legend
                      formatter={(v: string) => (
                        <span className="text-xs text-gray-700">{v}</span>
                      )}
                    />
                    <Bar
                      dataKey="Billed"
                      fill="#93C5FD"
                      radius={[0, 4, 4, 0]}
                    />
                    <Bar
                      dataKey="Approved"
                      fill="#1D4ED8"
                      radius={[0, 4, 4, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>

            {/* Exception breakdown (40%) */}
            <div className="rounded-xl border bg-white p-5 shadow-sm lg:col-span-2">
              <h2 className="text-sm font-semibold text-gray-900">
                Exception Breakdown
              </h2>
              <p className="text-xs text-gray-400 mt-0.5">
                Where billing issues originate
              </p>
              {exChartData.length === 0 ? (
                <p className="mt-8 text-center text-sm text-gray-400">
                  No exceptions on record.
                </p>
              ) : (
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart
                    data={exChartData}
                    margin={{ top: 8, right: 16, left: 0, bottom: 8 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis
                      dataKey="type"
                      tick={{ fontSize: 10 }}
                    />
                    <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                    <Tooltip
                      formatter={(v: number) => [v, "Exceptions"]}
                    />
                    <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                      {exChartData.map((entry, idx) => (
                        <Cell key={idx} fill={entry.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}

              {/* Exception totals */}
              {exBreakdown && exBreakdown.length > 0 && (
                <div className="mt-4 space-y-1 border-t pt-3">
                  {exBreakdown.map((e) => (
                    <div
                      key={e.validation_type}
                      className="flex items-center justify-between text-xs"
                    >
                      <span className="text-gray-600">{e.validation_type}</span>
                      <span
                        className="font-semibold"
                        style={{
                          color:
                            EXCEPTION_COLORS[e.validation_type] ?? "#6B7280",
                        }}
                      >
                        {e.count}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* ── Section 4: Taxonomy spend table ──────────────────────────── */}
          <div className="rounded-xl border bg-white shadow-sm">
            <div className="flex items-center justify-between border-b px-5 py-4">
              <div>
                <h2 className="text-sm font-semibold text-gray-900">
                  Spend by Taxonomy Code
                </h2>
                <p className="text-xs text-gray-400 mt-0.5">
                  Full line-item breakdown — click column headers to sort
                </p>
              </div>
              <span className="text-xs text-gray-400">
                {byTaxonomy?.length ?? 0} codes with activity
              </span>
            </div>

            {sortedTaxonomy.length === 0 ? (
              <p className="py-16 text-center text-sm text-gray-400">
                No classified spend data yet.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b bg-gray-50 text-left">
                      <th
                        className="cursor-pointer px-4 py-3 font-semibold text-gray-600 hover:text-blue-600"
                        onClick={() => toggleSort("taxonomy_code")}
                      >
                        Code <SortIcon col="taxonomy_code" />
                      </th>
                      <th
                        className="cursor-pointer px-4 py-3 font-semibold text-gray-600 hover:text-blue-600"
                        onClick={() => toggleSort("label")}
                      >
                        Service <SortIcon col="label" />
                      </th>
                      <th
                        className="cursor-pointer px-4 py-3 font-semibold text-gray-600 text-right hover:text-blue-600"
                        onClick={() => toggleSort("line_count")}
                      >
                        Lines <SortIcon col="line_count" />
                      </th>
                      <th
                        className="cursor-pointer px-4 py-3 font-semibold text-gray-600 text-right hover:text-blue-600"
                        onClick={() => toggleSort("total_billed")}
                      >
                        Billed <SortIcon col="total_billed" />
                      </th>
                      <th
                        className="cursor-pointer px-4 py-3 font-semibold text-gray-600 text-right hover:text-blue-600"
                        onClick={() => toggleSort("total_approved")}
                      >
                        Approved <SortIcon col="total_approved" />
                      </th>
                      <th
                        className="cursor-pointer px-4 py-3 font-semibold text-gray-600 text-right hover:text-blue-600"
                        onClick={() => toggleSort("variance")}
                      >
                        Variance <SortIcon col="variance" />
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {Object.entries(taxonomyByDomain).map(
                      ([domain, rows]) => (
                        <>
                          {/* Domain group header */}
                          <tr
                            key={`header-${domain}`}
                            className="bg-gray-50"
                          >
                            <td
                              colSpan={6}
                              className="px-4 py-2 font-semibold text-gray-500"
                              style={{
                                borderLeft: `3px solid ${DOMAIN_COLORS[domain] ?? "#9CA3AF"}`,
                              }}
                            >
                              {DOMAIN_LABELS[domain] ?? domain}
                            </td>
                          </tr>
                          {rows.map((row) => {
                            const billed = parseFloat(row.total_billed);
                            const approved = parseFloat(row.total_approved);
                            const variance = billed - approved;
                            return (
                              <tr
                                key={row.taxonomy_code}
                                className="hover:bg-gray-50"
                              >
                                <td className="px-4 py-2.5 font-mono text-gray-700">
                                  {row.taxonomy_code}
                                </td>
                                <td className="px-4 py-2.5 text-gray-600 max-w-xs">
                                  {row.label ?? row.taxonomy_code}
                                </td>
                                <td className="px-4 py-2.5 text-right tabular-nums text-gray-700">
                                  {row.line_count}
                                </td>
                                <td className="px-4 py-2.5 text-right tabular-nums text-gray-900 font-medium">
                                  {formatCurrency(row.total_billed)}
                                </td>
                                <td className="px-4 py-2.5 text-right tabular-nums text-gray-900">
                                  {formatCurrency(row.total_approved)}
                                </td>
                                <td
                                  className={`px-4 py-2.5 text-right tabular-nums font-medium ${
                                    variance > 0
                                      ? "text-amber-600"
                                      : "text-green-600"
                                  }`}
                                >
                                  {variance > 0
                                    ? `−${formatCurrency(variance)}`
                                    : "—"}
                                </td>
                              </tr>
                            );
                          })}
                        </>
                      ),
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
