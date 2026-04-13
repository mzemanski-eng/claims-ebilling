"use client";

import { useState, useEffect, useMemo } from "react";
import dynamic from "next/dynamic";
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
  Area,
  AreaChart,
} from "recharts";
import { MetricCard } from "@/components/metric-card";
import Link from "next/link";
import {
  getAnalyticsSummary,
  getSpendByDomain,
  getSpendBySupplier,
  getSpendByTaxonomy,
  getExceptionBreakdown,
  getRateGaps,
  getAiAccuracy,
  getSupplierComparison,
  getSupplierComparisonCsv,
  getSpendByState,
  getSpendByZip,
  getSpendTrend,
  getContractHealth,
  getSavingsRealization,
  getUtilization,
  getClaimStacking,
  getRateBenchmarks,
  getValueSummary,
  downloadBlob,
} from "@/lib/api";
import type {
  AiAccuracyByAction,
  AnalyticsFilters,
  ContractHealth,
  RateGap,
  RateBenchmarkRow,
  SpendByState,
  SpendByTaxonomy,
  SpendByZip,
  SpendTrend,
  SupplierComparisonRow,
  UtilizationRow,
  ClaimStackingRow,
  ValueSummary,
} from "@/lib/types";
import { DOMAIN_LABELS } from "@/lib/taxonomy";

// ── Dynamic map import (avoids SSR issues with react-simple-maps) ─────────────
const USSpendMap = dynamic(() => import("@/components/us-spend-map"), {
  ssr: false,
  loading: () => (
    <div className="flex h-64 items-center justify-center">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
    </div>
  ),
});

// ── Constants ─────────────────────────────────────────────────────────────────


const DOMAIN_COLORS: Record<string, string> = {
  IA:      "#8B5CF6",
  ENG:     "#F59E0B",
  REC:     "#10B981",
  LA:      "#14B8A6",
  INSP:    "#F97316",
  VIRT:    "#06B6D4",
  CR:      "#3B82F6",
  INV:     "#EF4444",
  DRNE:    "#84CC16",
  APPR:    "#F43F5E",
  XDOMAIN: "#6B7280",
};

const DOMAIN_ORDER = ["IA", "ENG", "REC", "LA", "INSP", "VIRT", "CR", "INV", "DRNE", "APPR", "XDOMAIN"];

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

const STATUS_FRIENDLY: Record<string, string> = {
  REVIEW_REQUIRED:        "Exceptions Flagged",
  PENDING_CARRIER_REVIEW: "Awaiting Approval",
  CARRIER_REVIEWING:      "Awaiting Approval",
  SUPPLIER_RESPONDED:     "Supplier Replied",
  APPROVED:               "Approved",
  DISPUTED:               "Disputed",
  EXPORTED:               "Paid",
  WITHDRAWN:              "Withdrawn",
  SUBMITTED:              "AI Processing",
  PROCESSING:             "AI Processing",
};

const EXCEPTION_COLORS: Record<string, string> = {
  RATE:           "#EF4444",
  GUIDELINE:      "#F97316",
  CLASSIFICATION: "#8B5CF6",
};

// ── Tab and filter types ───────────────────────────────────────────────────────

type TabId = "performance" | "overview" | "spend" | "suppliers" | "utilization" | "geographic";

interface FilterState {
  dateRange: "30d" | "90d" | "12mo" | "ytd";
  supplierId: string;
  domain: string;
}

const DEFAULT_FILTERS: FilterState = {
  dateRange: "12mo",
  supplierId: "",
  domain: "",
};

const LS_TAB    = "analytics_tab";
const LS_FILTER = "analytics_filters";

const TABS: { id: TabId; label: string }[] = [
  { id: "performance",  label: "Performance" },
  { id: "overview",     label: "Overview" },
  { id: "spend",        label: "Spend & Rates" },
  { id: "suppliers",    label: "Suppliers" },
  { id: "utilization",  label: "Utilization" },
  { id: "geographic",   label: "Geographic" },
];

// ── Sort types ────────────────────────────────────────────────────────────────

type SortKey = "taxonomy_code" | "label" | "line_count" | "total_billed" | "total_approved" | "variance" | "total_quantity" | "avg_billed_rate";
type SortDir = "asc" | "desc";

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

function toApiFilters(f: FilterState): AnalyticsFilters {
  const today = new Date();
  const fmt = (d: Date) => d.toISOString().split("T")[0];
  const to = fmt(today);
  let from = "";
  if (f.dateRange === "30d") {
    const d = new Date(today); d.setDate(today.getDate() - 30); from = fmt(d);
  } else if (f.dateRange === "90d") {
    const d = new Date(today); d.setDate(today.getDate() - 90); from = fmt(d);
  } else if (f.dateRange === "12mo") {
    const d = new Date(today); d.setMonth(today.getMonth() - 12); from = fmt(d);
  } else if (f.dateRange === "ytd") {
    from = `${today.getFullYear()}-01-01`;
  }
  return {
    date_from:   from || undefined,
    date_to:     to || undefined,
    supplier_id: f.supplierId || undefined,
    domain:      f.domain || undefined,
  };
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

// ── Performance Tab ───────────────────────────────────────────────────────────

function PerformanceTab({
  valueSummary,
  loading,
  onExportCsv,
  csvDownloading,
}: {
  valueSummary: ValueSummary | undefined;
  loading: boolean;
  onExportCsv: () => void;
  csvDownloading: boolean;
}) {
  const fmt = (val: string | number | undefined) => {
    const n = typeof val === "string" ? parseFloat(val) : Number(val ?? 0);
    if (isNaN(n)) return "$0";
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
  };

  const pct = (val: number | undefined) => `${Math.round((val ?? 0) * 100)}%`;

  const recoveryAccent = (() => {
    const r = (valueSummary?.totals.recovery_rate ?? 0);
    if (r >= 0.7) return "green" as const;
    if (r >= 0.4) return "amber" as const;
    return "red" as const;
  })();

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
      </div>
    );
  }

  const hasSavings = parseFloat(valueSummary?.totals.identified_savings ?? "0") > 0;

  return (
    <div className="space-y-6 print:space-y-8">
      {/* Print header — hidden on screen */}
      <div className="hidden print:block mb-6">
        <h2 className="text-xl font-bold text-gray-900">Performance Report</h2>
        <p className="text-sm text-gray-500 mt-0.5">
          {valueSummary?.period.from} → {valueSummary?.period.to}
          {" "}· {valueSummary?.period.days} days
          {" "}· Generated {new Date().toLocaleDateString()}
        </p>
      </div>

      {/* Hero KPI row */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MetricCard
          label="Total Reviewed"
          value={fmt(valueSummary?.totals.total_billed)}
          sublabel={`${valueSummary?.totals.invoices_processed ?? 0} invoices processed`}
          accent="blue"
        />
        <MetricCard
          label="Billing Issues Found"
          value={fmt(valueSummary?.totals.identified_savings)}
          sublabel="Rate + guideline variances"
          accent="amber"
        />
        <MetricCard
          label="Recovered for You"
          value={fmt(valueSummary?.totals.recovered_savings)}
          sublabel={`${fmt(valueSummary?.totals.pending_savings)} still pending`}
          accent="green"
        />
        <MetricCard
          label="Recovery Rate"
          value={pct(valueSummary?.totals.recovery_rate)}
          sublabel="Recovered / identified"
          accent={recoveryAccent}
        />
      </div>

      {/* Empty state */}
      {!hasSavings && (
        <div className="rounded-xl border border-dashed border-gray-200 bg-white py-16 text-center">
          <p className="text-sm font-medium text-gray-500">No billing variances identified yet</p>
          <p className="mt-1 text-xs text-gray-400">Process invoices with active contracts to see savings data</p>
        </div>
      )}

      {hasSavings && (
        <>
          {/* Savings trend */}
          {(valueSummary?.savings_trend?.length ?? 0) > 1 && (
            <div className="rounded-xl border bg-white p-5 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-700 mb-4">Savings Trend</h3>
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={valueSummary?.savings_trend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                  <YAxis tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 11 }} width={55} />
                  <Tooltip formatter={(v: number) => fmt(v)} />
                  <Legend />
                  <Area type="monotone" dataKey="identified" name="Identified" stroke="#F59E0B" fill="#FEF3C7" strokeWidth={2} />
                  <Area type="monotone" dataKey="recovered"  name="Recovered"  stroke="#10B981" fill="#D1FAE5" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Exception breakdown by type */}
          <div className="rounded-xl border bg-white p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-700 mb-5">Where Savings Come From</h3>
            <div className="space-y-4">
              {(["RATE", "GUIDELINE", "CLASSIFICATION"] as const).map((type) => {
                const d = valueSummary?.by_type?.[type];
                const typeLabels = { RATE: "Rate violations", GUIDELINE: "Guideline issues", CLASSIFICATION: "Classification" };
                const typeDesc = { RATE: "Billed above contracted rate", GUIDELINE: "Billing guideline breaches", CLASSIFICATION: "Unrecognized service codes" };
                return (
                  <div key={type} className="grid grid-cols-[7rem_5rem_7rem_7rem_1fr_2.5rem] items-center gap-3">
                    <div>
                      <p className="text-xs font-semibold text-gray-800">{typeLabels[type]}</p>
                      <p className="text-[10px] text-gray-400 leading-tight">{typeDesc[type]}</p>
                    </div>
                    <span className="text-xs tabular-nums text-gray-500">{d?.flagged ?? 0} flagged</span>
                    <span className="text-xs tabular-nums font-semibold text-amber-700">{fmt(d?.identified_savings ?? 0)} ID&apos;d</span>
                    <span className="text-xs tabular-nums font-semibold text-green-700">{fmt(d?.recovered_savings ?? 0)} rec&apos;d</span>
                    <div className="h-1.5 rounded-full bg-gray-100">
                      <div
                        className="h-1.5 rounded-full bg-green-500 transition-all"
                        style={{ width: `${Math.round((d?.recovery_rate ?? 0) * 100)}%` }}
                      />
                    </div>
                    <span className="text-xs tabular-nums text-gray-400 text-right">{pct(d?.recovery_rate)}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* AI Performance */}
          <div className="grid grid-cols-3 gap-4">
            {[
              {
                value: pct(valueSummary?.efficiency.auto_classification_rate),
                label: "AI Auto-Classified",
                sub: `${valueSummary?.efficiency.auto_classified_lines ?? 0} of ${valueSummary?.efficiency.total_lines ?? 0} lines`,
              },
              {
                value: pct(valueSummary?.efficiency.ai_recommendation_acceptance_rate),
                label: "AI Recommendation Acceptance",
                sub: "Carrier agreed with AI resolution",
              },
              {
                value: `${Math.round(valueSummary?.efficiency.estimated_hours_saved ?? 0)}h`,
                label: "Est. Hours Saved",
                sub: valueSummary?.efficiency.avg_exception_resolution_days
                  ? `~${valueSummary.efficiency.avg_exception_resolution_days.toFixed(1)}d avg exception resolution`
                  : "Based on auto-classified lines",
              },
            ].map(({ value, label, sub }) => (
              <div key={label} className="rounded-xl border bg-white p-5 shadow-sm text-center">
                <p className="text-3xl font-bold text-gray-900 tabular-nums">{value}</p>
                <p className="mt-1 text-xs font-semibold uppercase tracking-wide text-gray-500">{label}</p>
                <p className="mt-0.5 text-xs text-gray-400">{sub}</p>
              </div>
            ))}
          </div>

          {/* Top suppliers by exception rate */}
          {(valueSummary?.top_suppliers_by_exception_rate?.length ?? 0) > 0 && (
            <div className="rounded-xl border bg-white p-5 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-700 mb-4">Suppliers by Exception Rate</h3>
              <ResponsiveContainer width="100%" height={Math.max(160, (valueSummary?.top_suppliers_by_exception_rate?.length ?? 3) * 44 + 30)}>
                <BarChart
                  data={valueSummary?.top_suppliers_by_exception_rate}
                  layout="vertical"
                  margin={{ left: 8, right: 32, top: 4, bottom: 4 }}
                >
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickFormatter={(v: number) => `${Math.round(v * 100)}%`} tick={{ fontSize: 11 }} />
                  <YAxis type="category" dataKey="supplier_name" width={140} tick={{ fontSize: 11 }} />
                  <Tooltip
                    formatter={(v: number, _name: string, item: { payload?: { exception_lines?: number; total_lines?: number; identified_savings?: number } }) => [
                      `${Math.round(v * 100)}% (${item.payload?.exception_lines ?? 0} of ${item.payload?.total_lines ?? 0} lines)`,
                      "Exception Rate",
                    ]}
                  />
                  <Bar dataKey="exception_rate" name="Exception Rate" fill="#EF4444" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </>
      )}

      {/* Actions */}
      <div className="flex justify-end gap-3 print:hidden">
        <button
          onClick={() => window.print()}
          className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors"
        >
          Print / Save PDF
        </button>
        <button
          onClick={onExportCsv}
          disabled={csvDownloading}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 transition-colors disabled:opacity-50"
        >
          {csvDownloading ? "Exporting…" : "Export CSV"}
        </button>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AdminAnalyticsPage() {
  // ── Persistent state ──────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<TabId>("performance");
  const [filters, setFilters]     = useState<FilterState>(DEFAULT_FILTERS);
  const [initialized, setInitialized] = useState(false);

  // Load from localStorage on first mount
  useEffect(() => {
    try {
      const savedTab = localStorage.getItem(LS_TAB);
      const savedFilters = localStorage.getItem(LS_FILTER);
      if (savedTab) setActiveTab(savedTab as TabId);
      if (savedFilters) setFilters(JSON.parse(savedFilters));
    } catch { /* ignore */ }
    setInitialized(true);
  }, []);

  // Persist tab selection
  useEffect(() => {
    if (!initialized) return;
    localStorage.setItem(LS_TAB, activeTab);
  }, [activeTab, initialized]);

  // Persist filter state
  useEffect(() => {
    if (!initialized) return;
    localStorage.setItem(LS_FILTER, JSON.stringify(filters));
  }, [filters, initialized]);

  // ── UI state ──────────────────────────────────────────────────────────────
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>({
    key: "total_billed",
    dir: "desc",
  });
  const [csvDownloading, setCsvDownloading] = useState(false);
  const [selectedState, setSelectedState] = useState<string | null>(null);
  const [compSortKey, setCompSortKey] = useState<"total_billed" | "total_savings" | "exception_rate">("total_billed");
  const [compSortDir, setCompSortDir] = useState<SortDir>("desc");
  const [expandedBenchmark, setExpandedBenchmark] = useState<string | null>(null);

  // ── Derived API filters ───────────────────────────────────────────────────
  const apiFilters: AnalyticsFilters = useMemo(() => toApiFilters(filters), [filters]);
  const fk = [filters.dateRange, filters.supplierId, filters.domain]; // queryKey fragment

  // ── Queries ───────────────────────────────────────────────────────────────
  const { data: summary, isLoading: loadingSummary } = useQuery({
    queryKey: ["analytics-summary", ...fk],
    queryFn: () => getAnalyticsSummary(apiFilters),
  });
  const { data: byDomain, isLoading: loadingDomain } = useQuery({
    queryKey: ["analytics-domain", ...fk],
    queryFn: () => getSpendByDomain(apiFilters),
  });
  const { data: bySupplier, isLoading: loadingSupplier } = useQuery({
    queryKey: ["analytics-supplier", ...fk],
    queryFn: () => getSpendBySupplier(apiFilters),
  });
  const { data: byTaxonomy, isLoading: loadingTaxonomy } = useQuery({
    queryKey: ["analytics-taxonomy", ...fk],
    queryFn: () => getSpendByTaxonomy(apiFilters),
  });
  const { data: exBreakdown, isLoading: loadingEx } = useQuery({
    queryKey: ["analytics-exceptions", ...fk],
    queryFn: () => getExceptionBreakdown({ date_from: apiFilters.date_from, date_to: apiFilters.date_to, supplier_id: apiFilters.supplier_id }),
  });
  const { data: rateGaps } = useQuery({
    queryKey: ["analytics-rate-gaps", ...fk],
    queryFn: () => getRateGaps(apiFilters),
  });
  const { data: aiAccuracy } = useQuery({
    queryKey: ["analytics-ai-accuracy"],
    queryFn: getAiAccuracy,
  });
  const { data: supplierComparison } = useQuery({
    queryKey: ["analytics-supplier-comparison", ...fk],
    queryFn: () => getSupplierComparison(apiFilters),
  });
  const { data: spendTrend } = useQuery({
    queryKey: ["analytics-spend-trend", ...fk],
    queryFn: () => getSpendTrend("month", apiFilters),
  });
  const { data: contractHealth } = useQuery({
    queryKey: ["analytics-contract-health"],
    queryFn: getContractHealth,
  });
  const { data: byState } = useQuery({
    queryKey: ["analytics-by-state", ...fk],
    queryFn: () => getSpendByState(apiFilters),
  });
  const { data: byZip } = useQuery({
    queryKey: ["analytics-by-zip", selectedState, ...fk],
    queryFn: () => getSpendByZip(selectedState ?? undefined, apiFilters),
  });
  // New queries
  const { data: savingsReal } = useQuery({
    queryKey: ["analytics-savings-realization", ...fk],
    queryFn: () => getSavingsRealization(apiFilters),
  });
  const { data: utilization } = useQuery({
    queryKey: ["analytics-utilization", ...fk],
    queryFn: () => getUtilization(apiFilters),
  });
  const { data: claimStacking } = useQuery({
    queryKey: ["analytics-claim-stacking", ...fk],
    queryFn: () => getClaimStacking(apiFilters),
  });
  const { data: rateBenchmarks } = useQuery({
    queryKey: ["analytics-rate-benchmarks", ...fk],
    queryFn: () => getRateBenchmarks(apiFilters),
  });
  const { data: valueSummary, isLoading: loadingValue } = useQuery({
    queryKey: ["analytics-value-summary", filters.dateRange],
    queryFn: () => getValueSummary({ date_from: apiFilters.date_from, date_to: apiFilters.date_to }),
  });

  const isLoading = loadingSummary || loadingDomain || loadingSupplier || loadingTaxonomy || loadingEx;

  // ── CSV export ────────────────────────────────────────────────────────────
  async function handleCsvExport() {
    setCsvDownloading(true);
    try {
      const blob = await getSupplierComparisonCsv(apiFilters);
      downloadBlob(blob, "supplier-comparison.csv");
    } finally {
      setCsvDownloading(false);
    }
  }

  // ── Derived data ──────────────────────────────────────────────────────────

  const domainPieData = (byDomain ?? [])
    .sort((a, b) => DOMAIN_ORDER.indexOf(a.domain) - DOMAIN_ORDER.indexOf(b.domain))
    .map((d) => ({
      name: DOMAIN_LABELS[d.domain] ?? d.domain,
      value: parseFloat(d.total_billed),
      approved: parseFloat(d.total_approved),
      domain: d.domain,
      line_count: d.line_count,
    }));

  const statusBarData = (summary?.invoice_status_counts ?? [])
    .filter((s) => s.status !== "DRAFT" && s.status !== "PROCESSING" && s.count > 0)
    .sort((a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status))
    .map((s) => ({
      status: STATUS_FRIENDLY[s.status] ?? s.status.replace(/_/g, " "),
      count: s.count,
      fill: STATUS_COLORS[s.status] ?? "#9CA3AF",
    }));

  const supplierChartData = (bySupplier ?? []).map((s) => ({
    name: s.supplier_name,
    Billed: parseFloat(s.total_billed),
    Approved: parseFloat(s.total_approved),
  }));
  const supplierChartHeight = Math.max(200, (bySupplier?.length ?? 0) * 52 + 40);

  const exChartData = (exBreakdown ?? []).map((e) => ({
    type: e.validation_type,
    count: e.count,
    fill: EXCEPTION_COLORS[e.validation_type] ?? "#6B7280",
  }));

  const sortedTaxonomy = [...(byTaxonomy ?? [])].sort((a: SpendByTaxonomy, b: SpendByTaxonomy) => {
    let va: number | string = 0;
    let vb: number | string = 0;
    switch (sort.key) {
      case "taxonomy_code": va = a.taxonomy_code; vb = b.taxonomy_code; break;
      case "label":         va = a.label ?? ""; vb = b.label ?? ""; break;
      case "line_count":    va = a.line_count; vb = b.line_count; break;
      case "total_billed":  va = parseFloat(a.total_billed); vb = parseFloat(b.total_billed); break;
      case "total_approved":va = parseFloat(a.total_approved); vb = parseFloat(b.total_approved); break;
      case "variance":      va = parseFloat(a.total_billed) - parseFloat(a.total_approved); vb = parseFloat(b.total_billed) - parseFloat(b.total_approved); break;
      case "total_quantity":va = parseFloat(a.total_quantity ?? "0"); vb = parseFloat(b.total_quantity ?? "0"); break;
      case "avg_billed_rate":va = parseFloat(a.avg_billed_rate ?? "0"); vb = parseFloat(b.avg_billed_rate ?? "0"); break;
    }
    if (va < vb) return sort.dir === "asc" ? -1 : 1;
    if (va > vb) return sort.dir === "asc" ? 1 : -1;
    return 0;
  });

  const taxonomyByDomain: Record<string, SpendByTaxonomy[]> = {};
  sortedTaxonomy.forEach((row) => {
    const d = row.domain ?? "Unknown";
    if (!taxonomyByDomain[d]) taxonomyByDomain[d] = [];
    taxonomyByDomain[d].push(row);
  });

  function toggleSort(key: SortKey) {
    setSort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === "desc" ? "asc" : "desc" }
        : { key, dir: "desc" }
    );
  }

  function SortIcon({ col }: { col: SortKey }) {
    if (sort.key !== col) return <span className="ml-1 text-gray-300">↕</span>;
    return <span className="ml-1 text-blue-500">{sort.dir === "desc" ? "↓" : "↑"}</span>;
  }

  // ── Filter bar derived options ────────────────────────────────────────────
  const domainOpts = useMemo(
    () => Array.from(new Set((byDomain ?? []).map((d) => d.domain))).sort(),
    [byDomain]
  );

  const isFiltered = filters.supplierId !== "" || filters.domain !== "" || filters.dateRange !== "12mo";

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-gray-50">
      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4 bg-white border-b px-6 py-5">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Analytics</h1>
          <p className="mt-1 text-sm text-gray-500">
            Claims ALAE spend and demand management intelligence
          </p>
        </div>
        <button
          onClick={handleCsvExport}
          disabled={csvDownloading}
          className="shrink-0 inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:border-blue-200 hover:text-blue-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {csvDownloading ? (
            <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-gray-400 border-t-gray-700 inline-block" />
          ) : <span>⬇</span>}
          Export CSV
        </button>
      </div>

      {/* ── Sticky filter bar + tab nav ───────────────────────────────────── */}
      <div className="sticky top-0 z-20 bg-white border-b shadow-sm">
        {/* Filter row */}
        <div className="flex flex-wrap items-center gap-2 px-6 py-2 border-b border-gray-100">
          {/* Period buttons */}
          <div className="flex items-center gap-1">
            <span className="text-xs text-gray-400 mr-1.5 font-medium">Period:</span>
            {(["30d", "90d", "12mo", "ytd"] as FilterState["dateRange"][]).map((r) => (
              <button
                key={r}
                onClick={() => setFilters((f) => ({ ...f, dateRange: r }))}
                className={`px-2.5 py-1 text-xs rounded-md font-medium transition-colors ${
                  filters.dateRange === r
                    ? "bg-blue-600 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                }`}
              >
                {r === "12mo" ? "12M" : r === "ytd" ? "YTD" : r.toUpperCase()}
              </button>
            ))}
          </div>

          {/* Supplier filter */}
          <select
            value={filters.supplierId}
            onChange={(e) => setFilters((f) => ({ ...f, supplierId: e.target.value }))}
            className="text-xs border border-gray-200 rounded-md px-2.5 py-1 bg-white text-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-400"
          >
            <option value="">All Suppliers</option>
            {(bySupplier ?? []).map((s) => (
              <option key={s.supplier_id} value={s.supplier_id}>
                {s.supplier_name}
              </option>
            ))}
          </select>

          {/* Domain filter */}
          <select
            value={filters.domain}
            onChange={(e) => setFilters((f) => ({ ...f, domain: e.target.value }))}
            className="text-xs border border-gray-200 rounded-md px-2.5 py-1 bg-white text-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-400"
          >
            <option value="">All Domains</option>
            {domainOpts.map((d) => (
              <option key={d} value={d}>
                {DOMAIN_LABELS[d] ?? d}
              </option>
            ))}
          </select>

          {/* Roadmap placeholders */}
          <span
            title="Line of Business filter (Property / Auto / Casualty / WC) — roadmap item"
            className="px-2.5 py-1 text-xs bg-gray-50 text-gray-400 border border-dashed border-gray-300 rounded-md cursor-not-allowed select-none"
          >
            LOB
            <span className="ml-1.5 text-[10px] text-gray-300 font-medium uppercase tracking-wide">Soon</span>
          </span>
          <span
            title="Insurer / underwriting entity filter — roadmap item"
            className="px-2.5 py-1 text-xs bg-gray-50 text-gray-400 border border-dashed border-gray-300 rounded-md cursor-not-allowed select-none"
          >
            Insurer
            <span className="ml-1.5 text-[10px] text-gray-300 font-medium uppercase tracking-wide">Soon</span>
          </span>

          {/* Reset */}
          {isFiltered && (
            <button
              onClick={() => setFilters(DEFAULT_FILTERS)}
              className="ml-auto text-xs text-blue-600 hover:text-blue-800 font-medium"
            >
              Reset filters ×
            </button>
          )}
        </div>

        {/* Tab nav */}
        <nav className="flex items-end px-6">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors -mb-px ${
                activeTab === tab.id
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* ── Tab content ───────────────────────────────────────────────────── */}
      <div className="p-6 space-y-8">

        {/* ════════════════════════════════════════════════════════════
            PERFORMANCE TAB
        ════════════════════════════════════════════════════════════ */}
        {activeTab === "performance" && (
          <PerformanceTab valueSummary={valueSummary} loading={loadingValue} onExportCsv={handleCsvExport} csvDownloading={csvDownloading} />
        )}

        {isLoading ? (
          <div className="flex items-center justify-center py-24">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
          </div>
        ) : (
          <>
            {/* ════════════════════════════════════════════════════════════
                OVERVIEW TAB
            ════════════════════════════════════════════════════════════ */}
            {activeTab === "overview" && (
              <>
                {/* KPI cards */}
                <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                  <MetricCard
                    label="Submitted Amount"
                    value={new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(parseFloat(summary?.total_billed ?? "0"))}
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
                    accent={(summary?.open_exceptions ?? 0) > 0 ? "red" : "green"}
                  />
                </div>

                {/* Savings Realization */}
                <div className="rounded-xl border bg-white shadow-sm">
                  <div className="flex items-center justify-between border-b px-5 py-4">
                    <div>
                      <h2 className="text-sm font-semibold text-gray-900">
                        💰 Savings Realization
                      </h2>
                      <p className="text-xs text-gray-400 mt-0.5">
                        How much of what we identify are we actually capturing?
                      </p>
                    </div>
                    {savingsReal && savingsReal.total_invoices_with_exceptions > 0 && (
                      <span className={`rounded-full px-3 py-1 text-sm font-bold ${
                        savingsReal.recovery_rate >= 0.75
                          ? "bg-green-100 text-green-800"
                          : savingsReal.recovery_rate >= 0.4
                          ? "bg-amber-100 text-amber-800"
                          : "bg-red-100 text-red-800"
                      }`}>
                        {Math.round(savingsReal.recovery_rate * 100)}% recovery rate
                      </span>
                    )}
                  </div>
                  {!savingsReal || savingsReal.total_invoices_with_exceptions === 0 ? (
                    <div className="px-5 py-10 text-center">
                      <p className="text-sm text-gray-400">No exception data yet — savings realization will populate once invoices with exceptions are resolved.</p>
                    </div>
                  ) : (
                    <div className="p-5">
                      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                        {/* Identified */}
                        <div className="rounded-lg border-2 border-blue-100 bg-blue-50 p-4">
                          <p className="text-xs font-semibold uppercase tracking-wide text-blue-600 mb-1">Identified</p>
                          <p className="text-2xl font-bold text-blue-800 tabular-nums">
                            {formatCurrency(savingsReal.identified_savings)}
                          </p>
                          <p className="mt-1 text-xs text-blue-500">
                            Across {savingsReal.total_invoices_with_exceptions} invoices with exceptions
                          </p>
                        </div>
                        {/* Recovered */}
                        <div className="rounded-lg border-2 border-green-100 bg-green-50 p-4">
                          <p className="text-xs font-semibold uppercase tracking-wide text-green-600 mb-1">Recovered</p>
                          <p className="text-2xl font-bold text-green-800 tabular-nums">
                            {formatCurrency(savingsReal.recovered_savings)}
                          </p>
                          <p className="mt-1 text-xs text-green-500">
                            Applied on {savingsReal.invoices_with_recovery} approved invoices
                          </p>
                        </div>
                        {/* Pending */}
                        <div className="rounded-lg border-2 border-amber-100 bg-amber-50 p-4">
                          <p className="text-xs font-semibold uppercase tracking-wide text-amber-600 mb-1">Pending / Waived</p>
                          <p className="text-2xl font-bold text-amber-800 tabular-nums">
                            {formatCurrency(savingsReal.pending_savings)}
                          </p>
                          <p className="mt-1 text-xs text-amber-500">
                            Still in review or waived
                          </p>
                        </div>
                      </div>
                      {/* Visual recovery bar */}
                      <div className="mt-5">
                        <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
                          <span>Recovery rate</span>
                          <span className="font-semibold">{Math.round(savingsReal.recovery_rate * 100)}% of identified savings captured</span>
                        </div>
                        <div className="h-3 rounded-full bg-gray-100 overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all ${
                              savingsReal.recovery_rate >= 0.75 ? "bg-green-500" :
                              savingsReal.recovery_rate >= 0.4  ? "bg-amber-500" :
                              "bg-red-500"
                            }`}
                            style={{ width: `${Math.min(savingsReal.recovery_rate * 100, 100)}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* Spend Trend */}
                <div className="rounded-xl border bg-white shadow-sm">
                  <div className="flex items-center justify-between border-b px-5 py-4">
                    <div>
                      <h2 className="text-sm font-semibold text-gray-900">📈 Spend Trend</h2>
                      <p className="text-xs text-gray-400 mt-0.5">
                        Monthly billed vs. approved — within selected period
                      </p>
                    </div>
                  </div>
                  {!spendTrend || spendTrend.length === 0 ? (
                    <div className="px-5 py-10 text-center">
                      <p className="text-sm text-gray-400">No trend data yet — submit invoices with invoice dates to populate this chart.</p>
                    </div>
                  ) : (
                    <div className="p-5">
                      <ResponsiveContainer width="100%" height={280}>
                        <AreaChart
                          data={spendTrend.map((r: SpendTrend) => ({
                            period: r.period,
                            billed: parseFloat(r.total_billed),
                            approved: parseFloat(r.total_approved),
                            invoices: r.invoice_count,
                          }))}
                          margin={{ top: 8, right: 24, left: 8, bottom: 8 }}
                        >
                          <defs>
                            <linearGradient id="billedGrad" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%"  stopColor="#93C5FD" stopOpacity={0.4} />
                              <stop offset="95%" stopColor="#93C5FD" stopOpacity={0} />
                            </linearGradient>
                            <linearGradient id="approvedGrad" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%"  stopColor="#1D4ED8" stopOpacity={0.3} />
                              <stop offset="95%" stopColor="#1D4ED8" stopOpacity={0} />
                            </linearGradient>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" vertical={false} />
                          <XAxis dataKey="period" tick={{ fontSize: 10 }} tickFormatter={(v: string) => v.slice(5)} />
                          <YAxis tickFormatter={formatCurrencyShort} tick={{ fontSize: 10 }} width={64} />
                          <Tooltip
                            formatter={(value: number, name: string) => [formatCurrency(value), name === "billed" ? "Billed" : "Approved"]}
                            labelFormatter={(label: string) => `Month: ${label}`}
                          />
                          <Legend formatter={(v: string) => <span className="text-xs text-gray-700">{v === "billed" ? "Billed" : "Approved"}</span>} />
                          <Area type="monotone" dataKey="billed"   stroke="#93C5FD" strokeWidth={2} fill="url(#billedGrad)"   dot={false} />
                          <Area type="monotone" dataKey="approved" stroke="#1D4ED8" strokeWidth={2} fill="url(#approvedGrad)" dot={false} />
                        </AreaChart>
                      </ResponsiveContainer>
                      <div className="mt-3 flex items-center justify-end gap-6 text-xs text-gray-400">
                        <span>{spendTrend.length} month{spendTrend.length !== 1 ? "s" : ""} of data</span>
                        <span>Peak: <span className="font-medium text-gray-700">{formatCurrencyShort(Math.max(...spendTrend.map((r: SpendTrend) => parseFloat(r.total_billed))))}</span> billed</span>
                      </div>
                    </div>
                  )}
                </div>

                {/* AI Accuracy */}
                <div className="rounded-xl border bg-white shadow-sm">
                  <div className="flex items-center justify-between border-b px-5 py-4">
                    <div>
                      <h2 className="text-sm font-semibold text-gray-900">✦ AI Recommendation Performance</h2>
                      <p className="text-xs text-gray-400 mt-0.5">How often carriers follow AI exception resolution recommendations</p>
                    </div>
                    {aiAccuracy && aiAccuracy.total_resolved > 0 && (
                      <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${
                        (aiAccuracy.acceptance_rate ?? 0) >= 0.75 ? "bg-green-100 text-green-800" :
                        (aiAccuracy.acceptance_rate ?? 0) >= 0.5  ? "bg-amber-100 text-amber-800" :
                        "bg-red-100 text-red-800"
                      }`}>
                        {Math.round((aiAccuracy.acceptance_rate ?? 0) * 100)}% acceptance
                      </span>
                    )}
                  </div>
                  {!aiAccuracy || aiAccuracy.total_with_recommendation === 0 ? (
                    <div className="px-5 py-8 text-center">
                      <p className="text-sm text-gray-500 font-medium">No AI recommendation data yet</p>
                      <p className="mt-1 text-xs text-gray-400">Acceptance rates will appear once exceptions with AI recommendations are resolved.</p>
                    </div>
                  ) : (
                    <div className="p-5 space-y-5">
                      <div className="grid grid-cols-3 gap-4">
                        <div className="rounded-lg border bg-gray-50 px-4 py-3 text-center">
                          <p className="text-2xl font-bold text-gray-900 tabular-nums">{aiAccuracy.total_with_recommendation}</p>
                          <p className="mt-0.5 text-xs text-gray-500">Recommendations made</p>
                        </div>
                        <div className="rounded-lg border bg-gray-50 px-4 py-3 text-center">
                          <p className="text-2xl font-bold text-gray-900 tabular-nums">{aiAccuracy.total_resolved}</p>
                          <p className="mt-0.5 text-xs text-gray-500">Resolved with data</p>
                        </div>
                        <div className={`rounded-lg border px-4 py-3 text-center ${
                          aiAccuracy.total_resolved === 0 ? "bg-gray-50" :
                          (aiAccuracy.acceptance_rate ?? 0) >= 0.75 ? "bg-green-50 border-green-200" :
                          (aiAccuracy.acceptance_rate ?? 0) >= 0.5  ? "bg-amber-50 border-amber-200" :
                          "bg-red-50 border-red-200"
                        }`}>
                          <p className={`text-2xl font-bold tabular-nums ${
                            aiAccuracy.total_resolved === 0 ? "text-gray-400" :
                            (aiAccuracy.acceptance_rate ?? 0) >= 0.75 ? "text-green-700" :
                            (aiAccuracy.acceptance_rate ?? 0) >= 0.5  ? "text-amber-700" :
                            "text-red-700"
                          }`}>
                            {aiAccuracy.total_resolved === 0 ? "—" : `${Math.round((aiAccuracy.acceptance_rate ?? 0) * 100)}%`}
                          </p>
                          <p className="mt-0.5 text-xs text-gray-500">Acceptance rate</p>
                        </div>
                      </div>
                      {aiAccuracy.by_recommended_action.length > 0 && (
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">By Recommended Action</p>
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="border-b text-left">
                                <th className="pb-2 font-semibold text-gray-500">Action</th>
                                <th className="pb-2 text-right font-semibold text-gray-500">Recommended</th>
                                <th className="pb-2 text-right font-semibold text-gray-500">Resolved</th>
                                <th className="pb-2 text-right font-semibold text-gray-500">Followed</th>
                                <th className="pb-2 text-right font-semibold text-gray-500">Rate</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-50">
                              {aiAccuracy.by_recommended_action.map((row: AiAccuracyByAction) => {
                                const rate = row.acceptance_rate;
                                const rateColor =
                                  rate === null ? "text-gray-400" :
                                  rate >= 0.75 ? "text-green-700 font-semibold" :
                                  rate >= 0.5  ? "text-amber-700 font-semibold" :
                                  "text-red-700 font-semibold";
                                return (
                                  <tr key={row.action} className="hover:bg-gray-50">
                                    <td className="py-2 font-mono text-gray-700">{row.action}</td>
                                    <td className="py-2 text-right tabular-nums text-gray-600">{row.recommended}</td>
                                    <td className="py-2 text-right tabular-nums text-gray-600">{row.resolved}</td>
                                    <td className="py-2 text-right tabular-nums text-gray-600">{row.accepted}</td>
                                    <td className={`py-2 text-right tabular-nums ${rateColor}`}>
                                      {rate !== null ? `${Math.round(rate * 100)}%` : "—"}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </>
            )}

            {/* ════════════════════════════════════════════════════════════
                SPEND & RATES TAB
            ════════════════════════════════════════════════════════════ */}
            {activeTab === "spend" && (
              <>
                {/* Domain donut + Invoice status */}
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <div className="rounded-xl border bg-white p-5 shadow-sm">
                    <h2 className="text-sm font-semibold text-gray-900">Spend by Service Domain</h2>
                    <p className="text-xs text-gray-400 mt-0.5">Billed amount by service category (classified lines only)</p>
                    {domainPieData.length === 0 ? (
                      <p className="mt-8 text-center text-sm text-gray-400">No classified spend data yet.</p>
                    ) : (
                      <ResponsiveContainer width="100%" height={280}>
                        <PieChart>
                          <Pie data={domainPieData} cx="50%" cy="50%" innerRadius={70} outerRadius={110} paddingAngle={2} dataKey="value">
                            {domainPieData.map((entry) => (
                              <Cell key={entry.domain} fill={DOMAIN_COLORS[entry.domain] ?? "#9CA3AF"} />
                            ))}
                          </Pie>
                          <Tooltip content={<DomainTooltip />} />
                          <Legend formatter={(value: string) => <span className="text-xs text-gray-700">{value}</span>} />
                        </PieChart>
                      </ResponsiveContainer>
                    )}
                  </div>
                  <div className="rounded-xl border bg-white p-5 shadow-sm">
                    <h2 className="text-sm font-semibold text-gray-900">Invoice Status Distribution</h2>
                    <p className="text-xs text-gray-400 mt-0.5">Count of invoices by current status</p>
                    {statusBarData.length === 0 ? (
                      <p className="mt-8 text-center text-sm text-gray-400">No invoice data yet.</p>
                    ) : (
                      <ResponsiveContainer width="100%" height={280}>
                        <BarChart data={statusBarData} layout="vertical" margin={{ top: 8, right: 24, left: 8, bottom: 8 }}>
                          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                          <XAxis type="number" tick={{ fontSize: 11 }} />
                          <YAxis type="category" dataKey="status" width={148} tick={{ fontSize: 10 }} />
                          <Tooltip formatter={(value: number) => [value, "Invoices"]} />
                          <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                            {statusBarData.map((entry, idx) => <Cell key={idx} fill={entry.fill} />)}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    )}
                  </div>
                </div>

                {/* Supplier spend + Exception breakdown */}
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
                  <div className="rounded-xl border bg-white p-5 shadow-sm lg:col-span-3">
                    <h2 className="text-sm font-semibold text-gray-900">Spend by Supplier</h2>
                    <p className="text-xs text-gray-400 mt-0.5">Billed vs. approved per supplier</p>
                    {supplierChartData.length === 0 ? (
                      <p className="mt-8 text-center text-sm text-gray-400">No supplier spend data yet.</p>
                    ) : (
                      <ResponsiveContainer width="100%" height={supplierChartHeight}>
                        <BarChart data={supplierChartData} layout="vertical" margin={{ top: 8, right: 24, left: 8, bottom: 8 }}>
                          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                          <XAxis type="number" tickFormatter={formatCurrencyShort} tick={{ fontSize: 10 }} />
                          <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 10 }} />
                          <Tooltip content={<SupplierTooltip />} />
                          <Legend formatter={(v: string) => <span className="text-xs text-gray-700">{v}</span>} />
                          <Bar dataKey="Billed"   fill="#93C5FD" radius={[0, 4, 4, 0]} />
                          <Bar dataKey="Approved" fill="#1D4ED8" radius={[0, 4, 4, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    )}
                  </div>
                  <div className="rounded-xl border bg-white p-5 shadow-sm lg:col-span-2">
                    <h2 className="text-sm font-semibold text-gray-900">Exception Breakdown</h2>
                    <p className="text-xs text-gray-400 mt-0.5">Where billing issues originate</p>
                    {exChartData.length === 0 ? (
                      <p className="mt-8 text-center text-sm text-gray-400">No exceptions on record.</p>
                    ) : (
                      <ResponsiveContainer width="100%" height={220}>
                        <BarChart data={exChartData} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                          <CartesianGrid strokeDasharray="3 3" vertical={false} />
                          <XAxis dataKey="type" tick={{ fontSize: 10 }} />
                          <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                          <Tooltip formatter={(v: number) => [v, "Exceptions"]} />
                          <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                            {exChartData.map((entry, idx) => <Cell key={idx} fill={entry.fill} />)}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    )}
                    {exBreakdown && exBreakdown.length > 0 && (
                      <div className="mt-4 space-y-1 border-t pt-3">
                        {exBreakdown.map((e) => (
                          <div key={e.validation_type} className="flex items-center justify-between text-xs">
                            <span className="text-gray-600">{e.validation_type}</span>
                            <span className="font-semibold" style={{ color: EXCEPTION_COLORS[e.validation_type] ?? "#6B7280" }}>
                              {e.count}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {/* Taxonomy table */}
                <div className="rounded-xl border bg-white shadow-sm">
                  <div className="flex items-center justify-between border-b px-5 py-4">
                    <div>
                      <h2 className="text-sm font-semibold text-gray-900">Spend by Taxonomy Code</h2>
                      <p className="text-xs text-gray-400 mt-0.5">Full line-item breakdown — click column headers to sort</p>
                    </div>
                    <span className="text-xs text-gray-400">{byTaxonomy?.length ?? 0} codes with activity</span>
                  </div>
                  {sortedTaxonomy.length === 0 ? (
                    <p className="py-16 text-center text-sm text-gray-400">No classified spend data yet.</p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="border-b bg-gray-50 text-left">
                            <th className="cursor-pointer px-4 py-3 font-semibold text-gray-600 hover:text-blue-600" onClick={() => toggleSort("taxonomy_code")}>Code <SortIcon col="taxonomy_code" /></th>
                            <th className="cursor-pointer px-4 py-3 font-semibold text-gray-600 hover:text-blue-600" onClick={() => toggleSort("label")}>Service <SortIcon col="label" /></th>
                            <th className="cursor-pointer px-4 py-3 font-semibold text-gray-600 text-right hover:text-blue-600" onClick={() => toggleSort("line_count")}>Lines <SortIcon col="line_count" /></th>
                            <th className="cursor-pointer px-4 py-3 font-semibold text-gray-600 text-right hover:text-blue-600" onClick={() => toggleSort("total_quantity")} title="Total units / hours billed">Units <SortIcon col="total_quantity" /></th>
                            <th className="cursor-pointer px-4 py-3 font-semibold text-gray-600 text-right hover:text-blue-600" onClick={() => toggleSort("avg_billed_rate")} title="Average billed amount per unit">Avg Rate <SortIcon col="avg_billed_rate" /></th>
                            <th className="cursor-pointer px-4 py-3 font-semibold text-gray-600 text-right hover:text-blue-600" onClick={() => toggleSort("total_billed")}>Billed <SortIcon col="total_billed" /></th>
                            <th className="cursor-pointer px-4 py-3 font-semibold text-gray-600 text-right hover:text-blue-600" onClick={() => toggleSort("total_approved")}>Approved <SortIcon col="total_approved" /></th>
                            <th className="cursor-pointer px-4 py-3 font-semibold text-gray-600 text-right hover:text-blue-600" onClick={() => toggleSort("variance")}>Variance <SortIcon col="variance" /></th>
                          </tr>
                        </thead>
                        <tbody className="divide-y">
                          {Object.entries(taxonomyByDomain).map(([domain, rows]) => (
                            <>
                              <tr key={`header-${domain}`} className="bg-gray-50">
                                <td colSpan={8} className="px-4 py-2 font-semibold text-gray-500" style={{ borderLeft: `3px solid ${DOMAIN_COLORS[domain] ?? "#9CA3AF"}` }}>
                                  {DOMAIN_LABELS[domain] ?? domain}
                                </td>
                              </tr>
                              {rows.map((row) => {
                                const billed = parseFloat(row.total_billed);
                                const approved = parseFloat(row.total_approved);
                                const variance = billed - approved;
                                const qty = parseFloat(row.total_quantity ?? "0");
                                const avgRate = row.avg_billed_rate ? parseFloat(row.avg_billed_rate) : null;
                                return (
                                  <tr key={row.taxonomy_code} className="hover:bg-gray-50">
                                    <td className="px-4 py-2.5 font-mono text-gray-700">{row.taxonomy_code}</td>
                                    <td className="px-4 py-2.5 text-gray-600 max-w-xs">{row.label ?? row.taxonomy_code}</td>
                                    <td className="px-4 py-2.5 text-right tabular-nums text-gray-700">{row.line_count}</td>
                                    <td className="px-4 py-2.5 text-right tabular-nums text-gray-600">{qty > 0 ? qty.toLocaleString("en-US", { maximumFractionDigits: 1 }) : "—"}</td>
                                    <td className="px-4 py-2.5 text-right tabular-nums text-gray-600">{avgRate != null ? formatCurrency(avgRate) : "—"}</td>
                                    <td className="px-4 py-2.5 text-right tabular-nums text-gray-900 font-medium">{formatCurrency(row.total_billed)}</td>
                                    <td className="px-4 py-2.5 text-right tabular-nums text-gray-900">{formatCurrency(row.total_approved)}</td>
                                    <td className={`px-4 py-2.5 text-right tabular-nums font-medium ${variance > 0 ? "text-amber-600" : "text-green-600"}`}>
                                      {variance > 0 ? `−${formatCurrency(variance)}` : "—"}
                                    </td>
                                  </tr>
                                );
                              })}
                            </>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                {/* Rate Card Gaps */}
                <div className="rounded-xl border bg-white shadow-sm">
                  <div className="flex items-center justify-between border-b px-5 py-4">
                    <div>
                      <h2 className="text-sm font-semibold text-gray-900">Rate Card Gaps</h2>
                      <p className="text-xs text-gray-400 mt-0.5">Services being billed with no contracted rate — add a rate card to resolve each gap</p>
                    </div>
                    {rateGaps && rateGaps.length > 0 ? (
                      <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-800">
                        {rateGaps.length} gap{rateGaps.length !== 1 ? "s" : ""}
                      </span>
                    ) : (
                      <span className="rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-semibold text-green-700">✓ Clean</span>
                    )}
                  </div>
                  {!rateGaps || rateGaps.length === 0 ? (
                    <div className="px-5 py-8 text-center">
                      <p className="text-sm text-green-700 font-medium">✓ No rate card gaps detected</p>
                      <p className="mt-1 text-xs text-gray-400">All billed taxonomy codes have matching contracted rates.</p>
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="min-w-full divide-y divide-gray-100 text-sm">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">Taxonomy Code</th>
                            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">Service</th>
                            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">Supplier</th>
                            <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-gray-500">Open Exceptions</th>
                            <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-gray-500">Amount at Risk</th>
                            <th className="w-16" />
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                          {rateGaps.map((gap: RateGap) => (
                            <tr key={`${gap.taxonomy_code}-${gap.supplier_id}`} className="hover:bg-amber-50 transition-colors">
                              <td className="px-4 py-3"><span className="font-mono text-xs text-gray-700 bg-gray-100 px-1.5 py-0.5 rounded">{gap.taxonomy_code}</span></td>
                              <td className="px-4 py-3 text-gray-600">{gap.taxonomy_label ?? "—"}</td>
                              <td className="px-4 py-3 font-medium text-gray-900">{gap.supplier_name}</td>
                              <td className="px-4 py-3 text-right tabular-nums text-amber-700 font-medium">{gap.open_count}</td>
                              <td className="px-4 py-3 text-right tabular-nums font-medium text-gray-900">{formatCurrency(Number(gap.total_billed))}</td>
                              <td className="px-4 py-3 text-right">
                                <Link href={`/admin/contracts?supplier_id=${gap.supplier_id}`} className="text-xs font-medium text-blue-600 hover:text-blue-800">Fix →</Link>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                {/* Rate Benchmarks */}
                <div className="rounded-xl border bg-white shadow-sm">
                  <div className="flex items-center justify-between border-b px-5 py-4">
                    <div>
                      <h2 className="text-sm font-semibold text-gray-900">📊 Intra-Panel Rate Benchmarks</h2>
                      <p className="text-xs text-gray-400 mt-0.5">Average effective rate per supplier vs. panel average — sourcing and negotiation intelligence</p>
                    </div>
                    <span className="text-xs text-gray-400">{rateBenchmarks?.length ?? 0} codes with multi-supplier data</span>
                  </div>
                  {!rateBenchmarks || rateBenchmarks.length === 0 ? (
                    <div className="px-5 py-8 text-center">
                      <p className="text-sm text-gray-400">No benchmark data yet — requires at least 2 suppliers billing the same taxonomy code.</p>
                    </div>
                  ) : (
                    <div className="divide-y">
                      {rateBenchmarks.map((row: RateBenchmarkRow) => {
                        const isOpen = expandedBenchmark === row.taxonomy_code;
                        return (
                          <div key={row.taxonomy_code}>
                            <button
                              className="w-full flex items-center justify-between px-5 py-3.5 hover:bg-gray-50 transition-colors text-left"
                              onClick={() => setExpandedBenchmark(isOpen ? null : row.taxonomy_code)}
                            >
                              <div className="flex items-center gap-3">
                                <span className="font-mono text-xs text-gray-600 bg-gray-100 px-1.5 py-0.5 rounded">{row.taxonomy_code}</span>
                                <span className="text-xs text-gray-700">{row.taxonomy_label ?? row.taxonomy_code}</span>
                                {row.domain && (
                                  <span className="text-xs text-gray-400" style={{ color: DOMAIN_COLORS[row.domain] }}>• {row.domain}</span>
                                )}
                              </div>
                              <div className="flex items-center gap-6 text-xs">
                                <span className="text-gray-500">Panel avg: <span className="font-semibold text-gray-900">{formatCurrency(Number(row.panel_avg_rate))}</span></span>
                                <span className="text-gray-400">{row.supplier_count} suppliers</span>
                                <span className="text-gray-400">{isOpen ? "▲" : "▼"}</span>
                              </div>
                            </button>
                            {isOpen && (
                              <div className="px-5 pb-4 bg-gray-50">
                                <table className="w-full text-xs">
                                  <thead>
                                    <tr className="border-b text-left">
                                      <th className="py-2 font-semibold text-gray-500">Supplier</th>
                                      <th className="py-2 text-right font-semibold text-gray-500">Avg Rate</th>
                                      <th className="py-2 text-right font-semibold text-gray-500">vs. Panel</th>
                                      <th className="py-2 text-right font-semibold text-gray-500">Lines</th>
                                    </tr>
                                  </thead>
                                  <tbody className="divide-y divide-gray-100">
                                    {row.supplier_rates.map((sr) => {
                                      const pct = parseFloat(sr.pct_vs_panel);
                                      const pctColor = pct > 10 ? "text-red-600 font-semibold" : pct > 0 ? "text-amber-600" : "text-green-600";
                                      return (
                                        <tr key={sr.supplier_id} className="hover:bg-white">
                                          <td className="py-2 text-gray-700">{sr.supplier_name}</td>
                                          <td className="py-2 text-right tabular-nums font-medium text-gray-900">{formatCurrency(Number(sr.avg_rate))}</td>
                                          <td className={`py-2 text-right tabular-nums ${pctColor}`}>
                                            {pct > 0 ? `+${pct}%` : `${pct}%`}
                                          </td>
                                          <td className="py-2 text-right tabular-nums text-gray-500">{sr.line_count}</td>
                                        </tr>
                                      );
                                    })}
                                  </tbody>
                                </table>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </>
            )}

            {/* ════════════════════════════════════════════════════════════
                SUPPLIERS TAB
            ════════════════════════════════════════════════════════════ */}
            {activeTab === "suppliers" && (
              <>
                {/* Supplier Comparison */}
                <div className="rounded-xl border bg-white shadow-sm">
                  <div className="flex items-center justify-between border-b px-5 py-4">
                    <div>
                      <h2 className="text-sm font-semibold text-gray-900">Supplier × Service Comparison</h2>
                      <p className="text-xs text-gray-400 mt-0.5">Side-by-side billed vs. expected per supplier and taxonomy code</p>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-gray-400">{supplierComparison?.length ?? 0} rows</span>
                      <button
                        onClick={handleCsvExport}
                        disabled={csvDownloading}
                        className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 px-2.5 py-1 text-xs font-medium text-gray-600 hover:border-blue-200 hover:text-blue-700 transition-all disabled:opacity-50"
                      >
                        {csvDownloading ? <span className="h-3 w-3 animate-spin rounded-full border-2 border-gray-400 border-t-gray-700 inline-block" /> : "⬇"} CSV
                      </button>
                    </div>
                  </div>
                  {!supplierComparison || supplierComparison.length === 0 ? (
                    <div className="px-5 py-8 text-center"><p className="text-sm text-gray-400">No comparison data yet.</p></div>
                  ) : (
                    <div className="overflow-x-auto">
                      {(() => {
                        const sorted = [...supplierComparison].sort((a: SupplierComparisonRow, b: SupplierComparisonRow) => {
                          const va = compSortKey === "exception_rate" ? parseFloat(a.exception_rate) : parseFloat(a[compSortKey]);
                          const vb = compSortKey === "exception_rate" ? parseFloat(b.exception_rate) : parseFloat(b[compSortKey]);
                          return compSortDir === "desc" ? vb - va : va - vb;
                        });
                        const bySupplierMap: Record<string, SupplierComparisonRow[]> = {};
                        sorted.forEach((r) => {
                          if (!bySupplierMap[r.supplier_name]) bySupplierMap[r.supplier_name] = [];
                          bySupplierMap[r.supplier_name].push(r);
                        });
                        function CompSortBtn({ col, label }: { col: typeof compSortKey; label: string }) {
                          const active = compSortKey === col;
                          return (
                            <button
                              className={`cursor-pointer font-semibold hover:text-blue-600 ${active ? "text-blue-600" : "text-gray-600"}`}
                              onClick={() => {
                                if (active) setCompSortDir((d) => (d === "desc" ? "asc" : "desc"));
                                else { setCompSortKey(col); setCompSortDir("desc"); }
                              }}
                            >
                              {label} {active ? (compSortDir === "desc" ? "↓" : "↑") : <span className="text-gray-300">↕</span>}
                            </button>
                          );
                        }
                        return (
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="border-b bg-gray-50 text-left">
                                <th className="px-4 py-3 font-semibold text-gray-600">Supplier</th>
                                <th className="px-4 py-3 font-semibold text-gray-600">Code</th>
                                <th className="px-4 py-3 font-semibold text-gray-600">Service</th>
                                <th className="px-4 py-3 text-right font-semibold text-gray-600">Lines</th>
                                <th className="px-4 py-3 text-right"><CompSortBtn col="total_billed" label="Billed" /></th>
                                <th className="px-4 py-3 text-right font-semibold text-gray-600">Expected</th>
                                <th className="px-4 py-3 text-right"><CompSortBtn col="total_savings" label="Savings" /></th>
                                <th className="px-4 py-3 text-right"><CompSortBtn col="exception_rate" label="Exc. Rate" /></th>
                              </tr>
                            </thead>
                            <tbody className="divide-y">
                              {Object.entries(bySupplierMap).map(([supplierName, supplierRows]) => (
                                <>
                                  <tr key={`sup-${supplierName}`} className="bg-gray-50">
                                    <td colSpan={8} className="px-4 py-2 font-semibold text-gray-700 border-l-2 border-blue-300">{supplierName}</td>
                                  </tr>
                                  {supplierRows.map((r: SupplierComparisonRow) => {
                                    const savings = parseFloat(r.total_savings);
                                    const excRate = parseFloat(r.exception_rate);
                                    return (
                                      <tr key={`${r.supplier_id}-${r.taxonomy_code}`} className="hover:bg-gray-50">
                                        <td className="px-4 py-2.5" />
                                        <td className="px-4 py-2.5 font-mono text-gray-600">{r.taxonomy_code}</td>
                                        <td className="px-4 py-2.5 text-gray-600 max-w-[200px] truncate">{r.taxonomy_label ?? "—"}</td>
                                        <td className="px-4 py-2.5 text-right tabular-nums text-gray-600">{r.invoice_count}</td>
                                        <td className="px-4 py-2.5 text-right tabular-nums font-medium text-gray-900">{formatCurrency(r.total_billed)}</td>
                                        <td className="px-4 py-2.5 text-right tabular-nums text-gray-700">{formatCurrency(r.total_expected)}</td>
                                        <td className={`px-4 py-2.5 text-right tabular-nums font-medium ${savings > 0 ? "text-green-700" : "text-gray-400"}`}>
                                          {savings > 0 ? formatCurrency(savings) : "—"}
                                        </td>
                                        <td className={`px-4 py-2.5 text-right tabular-nums font-medium ${excRate > 50 ? "text-red-600" : excRate > 20 ? "text-amber-600" : "text-gray-500"}`}>
                                          {excRate > 0 ? `${excRate}%` : "—"}
                                        </td>
                                      </tr>
                                    );
                                  })}
                                </>
                              ))}
                            </tbody>
                          </table>
                        );
                      })()}
                    </div>
                  )}
                </div>

                {/* Contract Health */}
                <div className="rounded-xl border bg-white shadow-sm">
                  <div className="flex items-center justify-between border-b px-5 py-4">
                    <div>
                      <h2 className="text-sm font-semibold text-gray-900">📋 Contract Health</h2>
                      <p className="text-xs text-gray-400 mt-0.5">Rate card coverage, expiry alerts, and per-contract exception rates</p>
                    </div>
                    {contractHealth && contractHealth.length > 0 && (
                      <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                        contractHealth.some((c) => c.expiry_status === "EXPIRED") ? "bg-red-100 text-red-800" :
                        contractHealth.some((c) => c.expiry_status === "EXPIRING_SOON") ? "bg-amber-100 text-amber-800" :
                        "bg-green-100 text-green-700"
                      }`}>
                        {contractHealth.filter((c) => c.expiry_status !== "ACTIVE").length > 0
                          ? `${contractHealth.filter((c) => c.expiry_status !== "ACTIVE").length} need attention`
                          : "✓ All healthy"}
                      </span>
                    )}
                  </div>
                  {!contractHealth || contractHealth.length === 0 ? (
                    <div className="px-5 py-8 text-center"><p className="text-sm text-gray-400">No contracts on record yet.</p></div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="border-b bg-gray-50 text-left">
                            <th className="px-4 py-3 font-semibold text-gray-600">Contract</th>
                            <th className="px-4 py-3 font-semibold text-gray-600">Supplier</th>
                            <th className="px-4 py-3 text-center font-semibold text-gray-600">Rate Cards</th>
                            <th className="px-4 py-3 text-right font-semibold text-gray-600">Invoices</th>
                            <th className="px-4 py-3 text-right font-semibold text-gray-600">Exc. Rate</th>
                            <th className="px-4 py-3 font-semibold text-gray-600">Expires</th>
                            <th className="px-4 py-3 font-semibold text-gray-600">Status</th>
                            <th className="w-16" />
                          </tr>
                        </thead>
                        <tbody className="divide-y">
                          {contractHealth.map((c: ContractHealth) => {
                            const excRatePct = (c.exception_rate * 100).toFixed(1);
                            const expiryBadge =
                              c.expiry_status === "EXPIRED" ? { bg: "bg-red-100 text-red-800", label: "Expired" } :
                              c.expiry_status === "EXPIRING_SOON" ? { bg: "bg-amber-100 text-amber-800", label: c.days_to_expiry != null ? `${c.days_to_expiry}d left` : "Expiring soon" } :
                              { bg: "bg-green-100 text-green-700", label: "Active" };
                            return (
                              <tr key={c.contract_id} className={`hover:bg-gray-50 ${c.expiry_status !== "ACTIVE" ? "bg-amber-50/30" : ""}`}>
                                <td className="px-4 py-2.5 font-medium text-gray-900">{c.contract_name}</td>
                                <td className="px-4 py-2.5 text-gray-600">{c.supplier_name}</td>
                                <td className="px-4 py-2.5 text-center">
                                  {c.rate_card_count > 0 ? (
                                    <span className="inline-flex items-center gap-1 text-gray-700"><span className="font-semibold">{c.rate_card_count}</span><span className="text-gray-400">rates</span></span>
                                  ) : (
                                    <span className="text-amber-600 font-semibold">⚠ 0</span>
                                  )}
                                </td>
                                <td className="px-4 py-2.5 text-right tabular-nums text-gray-700">{c.invoice_count}</td>
                                <td className={`px-4 py-2.5 text-right tabular-nums font-medium ${parseFloat(excRatePct) > 50 ? "text-red-600" : parseFloat(excRatePct) > 20 ? "text-amber-600" : "text-gray-500"}`}>
                                  {c.invoice_count > 0 ? `${excRatePct}%` : "—"}
                                </td>
                                <td className="px-4 py-2.5 text-gray-600">{c.effective_to ?? "Open-ended"}</td>
                                <td className="px-4 py-2.5">
                                  <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${expiryBadge.bg}`}>{expiryBadge.label}</span>
                                </td>
                                <td className="px-4 py-2.5 text-right">
                                  <Link href={`/admin/contracts/${c.contract_id}`} className="text-xs font-medium text-blue-600 hover:text-blue-800">Edit →</Link>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </>
            )}

            {/* ════════════════════════════════════════════════════════════
                UTILIZATION TAB
            ════════════════════════════════════════════════════════════ */}
            {activeTab === "utilization" && (
              <>
                {/* Utilization / Frequency Analysis */}
                <div className="rounded-xl border bg-white shadow-sm">
                  <div className="flex items-center justify-between border-b px-5 py-4">
                    <div>
                      <h2 className="text-sm font-semibold text-gray-900">📈 Utilization & Frequency Analysis</h2>
                      <p className="text-xs text-gray-400 mt-0.5">
                        Average units billed per invoice by taxonomy code and supplier — flags potential over-utilization
                      </p>
                    </div>
                    <span className="text-xs text-gray-400">{utilization?.length ?? 0} code × supplier pairs</span>
                  </div>
                  {!utilization || utilization.length === 0 ? (
                    <div className="px-5 py-10 text-center">
                      <p className="text-sm text-gray-400">No utilization data yet — requires invoices with quantity data to populate.</p>
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="border-b bg-gray-50 text-left">
                            <th className="px-4 py-3 font-semibold text-gray-600">Domain</th>
                            <th className="px-4 py-3 font-semibold text-gray-600">Service Code</th>
                            <th className="px-4 py-3 font-semibold text-gray-600">Supplier</th>
                            <th className="px-4 py-3 text-right font-semibold text-gray-600">Invoices</th>
                            <th className="px-4 py-3 text-right font-semibold text-gray-600">Total Units</th>
                            <th className="px-4 py-3 text-right font-semibold text-gray-600" title="Average units per invoice">Avg / Invoice</th>
                            <th className="px-4 py-3 text-right font-semibold text-gray-600" title="Highest single-invoice unit count">Max Single</th>
                            <th className="px-4 py-3 text-right font-semibold text-gray-600" title="Contracted max unit cap from rate card">Cap</th>
                            <th className="px-4 py-3 text-right font-semibold text-gray-600" title="Avg units as % of contracted cap">Cap Util.</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y">
                          {utilization.map((row: UtilizationRow) => {
                            const capPct = row.cap_utilization_pct ? parseFloat(row.cap_utilization_pct) : null;
                            const capColor =
                              capPct === null ? "" :
                              capPct >= 90 ? "text-red-600 font-bold" :
                              capPct >= 70 ? "text-amber-600 font-semibold" :
                              "text-gray-500";
                            return (
                              <tr key={`${row.taxonomy_code}-${row.supplier_id}`} className="hover:bg-gray-50">
                                <td className="px-4 py-2.5">
                                  {row.domain ? (
                                    <span className="text-xs font-medium" style={{ color: DOMAIN_COLORS[row.domain] }}>
                                      {row.domain}
                                    </span>
                                  ) : "—"}
                                </td>
                                <td className="px-4 py-2.5">
                                  <div>
                                    <span className="font-mono text-gray-700">{row.taxonomy_code}</span>
                                    {row.taxonomy_label && (
                                      <p className="text-gray-400 text-[10px] mt-0.5 truncate max-w-[160px]">{row.taxonomy_label}</p>
                                    )}
                                  </div>
                                </td>
                                <td className="px-4 py-2.5 text-gray-700">{row.supplier_name}</td>
                                <td className="px-4 py-2.5 text-right tabular-nums text-gray-600">{row.total_invoices}</td>
                                <td className="px-4 py-2.5 text-right tabular-nums text-gray-600">{parseFloat(row.total_units).toLocaleString("en-US", { maximumFractionDigits: 1 })}</td>
                                <td className="px-4 py-2.5 text-right tabular-nums font-medium text-gray-900">{parseFloat(row.avg_units_per_invoice).toFixed(2)}</td>
                                <td className="px-4 py-2.5 text-right tabular-nums text-gray-600">{parseFloat(row.max_single_invoice).toFixed(2)}</td>
                                <td className="px-4 py-2.5 text-right tabular-nums text-gray-400">{row.max_units_cap ?? "—"}</td>
                                <td className={`px-4 py-2.5 text-right tabular-nums ${capColor}`}>
                                  {capPct !== null ? `${capPct}%` : "—"}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                {/* Claim Stacking / Vendor Overlap */}
                <div className="rounded-xl border bg-white shadow-sm">
                  <div className="flex items-center justify-between border-b px-5 py-4">
                    <div>
                      <h2 className="text-sm font-semibold text-gray-900">🔍 Claim Service Stacking & Vendor Overlap</h2>
                      <p className="text-xs text-gray-400 mt-0.5">
                        Claims where the same service is billed by multiple vendors, or billed more than twice — demand leakage signals
                      </p>
                    </div>
                    <span className="text-xs text-gray-400">{claimStacking?.length ?? 0} flagged patterns</span>
                  </div>
                  {!claimStacking || claimStacking.length === 0 ? (
                    <div className="px-5 py-10 text-center">
                      <p className="text-sm text-gray-400">No stacking patterns detected — this is the expected result for well-managed claims.</p>
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="border-b bg-gray-50 text-left">
                            <th className="px-4 py-3 font-semibold text-gray-600">Claim #</th>
                            <th className="px-4 py-3 font-semibold text-gray-600">Service Code</th>
                            <th className="px-4 py-3 font-semibold text-gray-600">Domain</th>
                            <th className="px-4 py-3 font-semibold text-gray-600">Flag</th>
                            <th className="px-4 py-3 text-right font-semibold text-gray-600">Suppliers</th>
                            <th className="px-4 py-3 text-right font-semibold text-gray-600">Occurrences</th>
                            <th className="px-4 py-3 text-right font-semibold text-gray-600">Total Billed</th>
                            <th className="px-4 py-3 font-semibold text-gray-600">Vendors</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y">
                          {claimStacking.map((row: ClaimStackingRow) => {
                            const isOverlap = row.supplier_count > 1;
                            const flagBg = isOverlap ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700";
                            const flagLabel = isOverlap ? "Multi-vendor overlap" : "High frequency";
                            return (
                              <tr key={`${row.claim_number}-${row.taxonomy_code}`} className={`hover:bg-gray-50 ${isOverlap ? "border-l-2 border-red-300" : ""}`}>
                                <td className="px-4 py-2.5 font-mono font-semibold text-gray-900">{row.claim_number}</td>
                                <td className="px-4 py-2.5">
                                  <div>
                                    <span className="font-mono text-gray-700">{row.taxonomy_code}</span>
                                    {row.taxonomy_label && <p className="text-gray-400 text-[10px] mt-0.5">{row.taxonomy_label}</p>}
                                  </div>
                                </td>
                                <td className="px-4 py-2.5">
                                  {row.domain ? (
                                    <span className="text-xs font-medium" style={{ color: DOMAIN_COLORS[row.domain] }}>{row.domain}</span>
                                  ) : "—"}
                                </td>
                                <td className="px-4 py-2.5">
                                  <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${flagBg}`}>{flagLabel}</span>
                                </td>
                                <td className="px-4 py-2.5 text-right tabular-nums font-semibold text-gray-900">{row.supplier_count}</td>
                                <td className="px-4 py-2.5 text-right tabular-nums text-gray-700">{row.line_item_count}</td>
                                <td className="px-4 py-2.5 text-right tabular-nums font-medium text-gray-900">{formatCurrency(row.total_billed)}</td>
                                <td className="px-4 py-2.5 text-gray-500 text-[10px]">{row.supplier_names.join(", ")}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </>
            )}

            {/* ════════════════════════════════════════════════════════════
                GEOGRAPHIC TAB
            ════════════════════════════════════════════════════════════ */}
            {activeTab === "geographic" && (
              <div className="rounded-xl border bg-white shadow-sm">
                <div className="flex items-center justify-between border-b px-5 py-4">
                  <div>
                    <h2 className="text-sm font-semibold text-gray-900">🗺 Geographic Spend Distribution</h2>
                    <p className="text-xs text-gray-400 mt-0.5">Where services are being performed — based on supplier-reported state and ZIP</p>
                  </div>
                  {byState && byState.length === 0 && (
                    <span className="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs text-gray-500">No location data yet</span>
                  )}
                  {selectedState && (
                    <button onClick={() => setSelectedState(null)} className="text-xs font-medium text-blue-600 hover:text-blue-800">← All states</button>
                  )}
                </div>
                {!byState || byState.length === 0 ? (
                  <div className="px-5 py-10 text-center">
                    <p className="text-2xl">🗺</p>
                    <p className="mt-2 text-sm font-medium text-gray-600">No geographic data yet</p>
                    <p className="mt-1 text-xs text-gray-400 max-w-sm mx-auto">
                      Ask suppliers to include <code className="bg-gray-100 px-1 rounded">service_state</code> and{" "}
                      <code className="bg-gray-100 px-1 rounded">service_zip</code> columns in their invoice CSVs.
                    </p>
                  </div>
                ) : (
                  <div className="p-5 space-y-6">
                    <USSpendMap
                      data={byState}
                      selectedState={selectedState}
                      onStateClick={(state) => setSelectedState((prev) => (prev === state ? null : state))}
                    />
                    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                      {/* State breakdown */}
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
                          Spend by State {selectedState ? `— filtered to ${selectedState}` : ""}
                        </p>
                        <div className="overflow-hidden rounded-lg border">
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="border-b bg-gray-50 text-left">
                                <th className="px-3 py-2 font-semibold text-gray-600">State</th>
                                <th className="px-3 py-2 text-right font-semibold text-gray-600">Lines</th>
                                <th className="px-3 py-2 text-right font-semibold text-gray-600">Billed</th>
                                <th className="px-3 py-2 text-right font-semibold text-gray-600">% of Total</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y">
                              {(() => {
                                const totalBilled = byState.reduce((s, r) => s + parseFloat(r.total_billed), 0);
                                const rows = selectedState ? byState.filter((r) => r.state === selectedState) : byState.slice(0, 10);
                                return rows.map((row: SpendByState) => {
                                  const billed = parseFloat(row.total_billed);
                                  const pct = totalBilled > 0 ? ((billed / totalBilled) * 100).toFixed(1) : "0.0";
                                  return (
                                    <tr
                                      key={row.state}
                                      className={`cursor-pointer transition-colors ${selectedState === row.state ? "bg-blue-50" : "hover:bg-gray-50"}`}
                                      onClick={() => setSelectedState((prev) => (prev === row.state ? null : row.state))}
                                    >
                                      <td className="px-3 py-2 font-semibold text-gray-900">{row.state}</td>
                                      <td className="px-3 py-2 text-right tabular-nums text-gray-600">{row.line_count}</td>
                                      <td className="px-3 py-2 text-right tabular-nums font-medium text-gray-900">{formatCurrency(row.total_billed)}</td>
                                      <td className="px-3 py-2 text-right tabular-nums text-gray-500">{pct}%</td>
                                    </tr>
                                  );
                                });
                              })()}
                            </tbody>
                          </table>
                        </div>
                      </div>
                      {/* ZIP breakdown */}
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
                          Top ZIP Codes {selectedState ? `in ${selectedState}` : "(all states)"}
                        </p>
                        {!byZip || byZip.length === 0 ? (
                          <div className="flex items-center justify-center rounded-lg border bg-gray-50 py-10">
                            <p className="text-xs text-gray-400">No ZIP data available</p>
                          </div>
                        ) : (
                          <div className="overflow-hidden rounded-lg border">
                            <table className="w-full text-xs">
                              <thead>
                                <tr className="border-b bg-gray-50 text-left">
                                  <th className="px-3 py-2 font-semibold text-gray-600">ZIP</th>
                                  <th className="px-3 py-2 font-semibold text-gray-600">State</th>
                                  <th className="px-3 py-2 text-right font-semibold text-gray-600">Lines</th>
                                  <th className="px-3 py-2 text-right font-semibold text-gray-600">Billed</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y">
                                {byZip.slice(0, 10).map((row: SpendByZip) => (
                                  <tr key={row.zip} className="hover:bg-gray-50">
                                    <td className="px-3 py-2 font-mono font-semibold text-gray-900">{row.zip}</td>
                                    <td className="px-3 py-2 text-gray-500">{row.state ?? "—"}</td>
                                    <td className="px-3 py-2 text-right tabular-nums text-gray-600">{row.line_count}</td>
                                    <td className="px-3 py-2 text-right tabular-nums font-medium text-gray-900">{formatCurrency(row.total_billed)}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
