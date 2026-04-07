"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useState, useEffect, useMemo, useRef } from "react";
import {
  getAnalyticsSummary,
  listAdminInvoices,
  getMappingReviewQueue,
  runSeedDemo,
  getSeedDemoStatus,
} from "@/lib/api";
import { TrendingUp } from "lucide-react";
import { MetricCard } from "@/components/metric-card";
import { StatusBadge } from "@/components/status-badge";
import { getUserInfo, isCarrierAdmin } from "@/lib/auth";
import type { InvoiceListItem, SeedDemoJobStatus } from "@/lib/types";

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

// ── Seed Demo button + modal ──────────────────────────────────────────────────

type SeedPhase = "idle" | "confirming" | "running" | "done" | "error";

function SeedDemoButton() {
  const [phase, setPhase] = useState<SeedPhase>("idle");
  const [clean, setClean] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [result, setResult] = useState<SeedDemoJobStatus | null>(null);
  const [errMsg, setErrMsg] = useState<string>("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Poll job status every 3 s while running
  useEffect(() => {
    if (phase === "running" && jobId) {
      pollRef.current = setInterval(async () => {
        try {
          const data = await getSeedDemoStatus(jobId);
          if (data.status === "finished") {
            clearInterval(pollRef.current!);
            setResult(data);
            setPhase("done");
          } else if (data.status === "failed") {
            clearInterval(pollRef.current!);
            setErrMsg(data.error ?? "Seed job failed");
            setPhase("error");
          }
        } catch {
          // network blip — keep polling
        }
      }, 3000);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [phase, jobId]);

  async function handleGenerate() {
    setPhase("running");
    try {
      const { job_id } = await runSeedDemo(clean);
      setJobId(job_id);
    } catch (e: unknown) {
      setErrMsg(e instanceof Error ? e.message : "Failed to start seed job");
      setPhase("error");
    }
  }

  function reset() {
    setPhase("idle");
    setJobId(null);
    setResult(null);
    setErrMsg("");
    setClean(false);
  }

  // Trigger button (always visible in Quick Actions)
  const triggerButton = (
    <button
      onClick={() => setPhase("confirming")}
      className="flex flex-col gap-1 rounded-xl border bg-white p-4 shadow-sm hover:border-purple-200 hover:shadow-md transition-all group text-left w-full"
    >
      <span className="text-xl">🌱</span>
      <span className="text-sm font-semibold text-gray-900 group-hover:text-purple-700 transition-colors">
        Seed Demo Data
      </span>
      <span className="text-xs text-gray-400">Generate synthetic invoices &amp; contracts</span>
    </button>
  );

  if (phase === "idle") return triggerButton;

  // Modal overlay for all non-idle phases
  return (
    <>
      {triggerButton}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
        <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">

          {/* confirming */}
          {phase === "confirming" && (
            <>
              <h2 className="text-base font-semibold text-gray-900 mb-1">Generate Demo Data</h2>
              <p className="text-sm text-gray-500 mb-4">
                Creates 6 suppliers, 12 contracts, 120 invoices, and ~640 line items
                across all 11 P&amp;C ALAE taxonomy domains using Claude AI.
                Runs as a background job (~2–4 minutes).
              </p>
              <label className="flex items-center gap-2 mb-5 text-sm text-gray-700 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={clean}
                  onChange={e => setClean(e.target.checked)}
                  className="h-4 w-4 rounded border-gray-300 text-purple-600 focus:ring-purple-500"
                />
                <span>
                  <span className="font-medium">Regenerate</span>
                  {" "}— delete existing SEED-* data first
                </span>
              </label>
              <div className="flex gap-3">
                <button
                  onClick={handleGenerate}
                  className="flex-1 rounded-lg bg-purple-600 px-4 py-2 text-sm font-semibold text-white hover:bg-purple-700 transition-colors"
                >
                  Generate
                </button>
                <button
                  onClick={reset}
                  className="flex-1 rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </>
          )}

          {/* running */}
          {phase === "running" && (
            <div className="flex flex-col items-center gap-4 py-4">
              <div className="h-10 w-10 rounded-full border-4 border-purple-200 border-t-purple-600 animate-spin" />
              <p className="text-sm font-medium text-gray-700">Generating demo data…</p>
              <p className="text-xs text-gray-400 text-center">
                Agents are building suppliers, contracts, and invoices.
                This takes 2–4 minutes.
              </p>
            </div>
          )}

          {/* done */}
          {phase === "done" && result?.result && (
            <>
              <div className="flex items-center gap-2 mb-3">
                <span className="text-xl">✅</span>
                <h2 className="text-base font-semibold text-gray-900">Seed Complete</h2>
              </div>
              <div className="grid grid-cols-2 gap-2 mb-5">
                {[
                  ["Suppliers",  result.result.suppliers],
                  ["Contracts",  result.result.contracts],
                  ["Invoices",   result.result.invoices],
                  ["Line Items", result.result.line_items],
                ].map(([label, val]) => (
                  <div key={label as string} className="rounded-lg bg-purple-50 p-3 text-center">
                    <div className="text-xl font-bold text-purple-700">{val}</div>
                    <div className="text-xs text-gray-500">{label}</div>
                  </div>
                ))}
              </div>
              <button
                onClick={() => { reset(); window.location.reload(); }}
                className="w-full rounded-lg bg-purple-600 px-4 py-2 text-sm font-semibold text-white hover:bg-purple-700 transition-colors"
              >
                Refresh Dashboard
              </button>
            </>
          )}

          {/* error */}
          {phase === "error" && (
            <>
              <div className="flex items-center gap-2 mb-3">
                <span className="text-xl">❌</span>
                <h2 className="text-base font-semibold text-gray-900">Seed Failed</h2>
              </div>
              <p className="text-sm text-red-600 bg-red-50 rounded-lg p-3 mb-4 font-mono break-all">
                {errMsg}
              </p>
              <button
                onClick={reset}
                className="w-full rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors"
              >
                Close
              </button>
            </>
          )}

        </div>
      </div>
    </>
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

  // Mapping count: number of *distinct invoices* that have lines needing review,
  // not raw line count — avoids inflating the alert for large invoices.
  const mappingCount = useMemo(() => {
    if (!mappingQueue || mappingQueue.length === 0) return 0;
    return new Set(mappingQueue.map((item) => item.invoice_id)).size;
  }, [mappingQueue]);

  const mappingLineCount = mappingQueue?.length ?? 0;

  // Aging alert: PENDING_CARRIER_REVIEW invoices sitting for 7+ days
  const sevenDaysAgo = Date.now() - 7 * 86_400_000;
  const agedCount = useMemo(() => {
    if (!pendingInvoices) return 0;
    return pendingInvoices.filter(
      (inv) => inv.submitted_at && new Date(inv.submitted_at).getTime() < sevenDaysAgo,
    ).length;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingInvoices]);

  const hasAlerts = flaggedCount > 0 || mappingCount > 0 || agedCount > 0;

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
        <div className="flex flex-col gap-2">
          {agedCount > 0 && (
            <Link
              href="/admin/invoices?status=PENDING_CARRIER_REVIEW"
              className="flex items-center gap-3 rounded-xl border border-red-300 bg-red-50 px-4 py-3 hover:bg-red-100 transition-colors"
            >
              <span className="text-lg">⏰</span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-red-800">
                  {agedCount} invoice{agedCount !== 1 ? "s" : ""} waiting 7+ days for approval
                </p>
                <p className="text-xs text-red-500">
                  Stale items in the pending queue · review to avoid supplier delays
                </p>
              </div>
              <span className="shrink-0 text-xs font-semibold text-red-600">Review →</span>
            </Link>
          )}
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
                    {mappingCount} invoice{mappingCount !== 1 ? "s" : ""} need classification
                    {mappingLineCount > mappingCount && (
                      <span className="ml-1 font-normal text-amber-700">
                        ({mappingLineCount} lines)
                      </span>
                    )}
                  </p>
                  <p className="text-xs text-amber-500">Service lines without an assigned spend bucket · click to review</p>
                </div>
                <span className="shrink-0 text-xs font-semibold text-amber-600">Review →</span>
              </Link>
            )}
          </div>
        </div>
      )}

      {/* KPI strip */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MetricCard
          label="Submitted Amount"
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

      {/* Value snapshot strip */}
      {summary && (Number(summary.total_savings) > 0 || (summary.recovery_rate ?? 0) > 0) && (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 rounded-xl border border-indigo-100 bg-indigo-50 px-4 py-2.5">
          <span className="flex items-center gap-1.5 text-xs font-semibold text-indigo-700">
            <TrendingUp className="h-3.5 w-3.5" />
            Platform value
          </span>
          <span className="text-sm text-gray-700">
            <span className="font-semibold text-gray-900">{fmt(summary.total_savings)}</span>
            {" "}identified
          </span>
          {(summary.recovery_rate ?? 0) > 0 && (
            <span className="text-sm text-gray-700">
              <span className="font-semibold text-gray-900">
                {Math.round((summary.recovery_rate ?? 0) * 100)}%
              </span>
              {" "}recovered
            </span>
          )}
          {(summary.auto_classification_rate ?? 0) > 0 && (
            <span className="text-sm text-gray-700">
              <span className="font-semibold text-gray-900">
                {Math.round((summary.auto_classification_rate ?? 0) * 100)}%
              </span>
              {" "}AI auto-classified
            </span>
          )}
          <Link
            href="/admin/analytics"
            className="ml-auto text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition-colors"
          >
            Full Report →
          </Link>
        </div>
      )}

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
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
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
          <SeedDemoButton />
        </div>
      </div>
    </div>
  );
}
