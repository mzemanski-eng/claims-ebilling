"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getAdminInvoice,
  getAdminInvoiceLines,
  approveAdminInvoice,
  exportAdminInvoice,
  resolveAdminException,
  overrideMapping,
  downloadBlob,
} from "@/lib/api";
import { StatusBadge } from "@/components/status-badge";
import { ConfidenceBadge } from "@/components/confidence-badge";
import { AiClassificationSuggestion } from "@/components/ai-classification-suggestion";
import { Button } from "@/components/ui/button";
import type { LineItemCarrierView } from "@/lib/types";
import { ResolutionActions } from "@/lib/types";
import { useToast } from "@/components/toast";

// ── AI Processing Timeline ────────────────────────────────────────────────────

function fmt(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

/** Normalise a billing unit to its singular form for use in rate labels (e.g. "hrs" → "hr"). */
function toUnitSingular(unit: string): string {
  const map: Record<string, string> = {
    hrs: "hr", hours: "hr", hour: "hr",
    days: "day",
    claims: "claim",
    units: "unit",
    pages: "page",
    items: "item",
    reports: "report",
    assessments: "assessment",
    inspections: "inspection",
    reviews: "review",
    visits: "visit",
    services: "service",
  };
  return map[unit.toLowerCase().trim()] ?? unit.toLowerCase().trim();
}

type StepVariant = "neutral" | "pass" | "warn" | "pending";

function TimelineStep({
  label, detail, variant,
}: {
  label: string; detail: React.ReactNode; variant: StepVariant;
}) {
  const dotColors: Record<StepVariant, string> = {
    neutral: "bg-gray-400",
    pass:    "bg-green-400",
    warn:    "bg-amber-400",
    pending: "bg-gray-200",
  };
  const labelColors: Record<StepVariant, string> = {
    neutral: "text-gray-700",
    pass:    "text-green-800",
    warn:    "text-amber-800",
    pending: "text-gray-400",
  };
  const detailColors: Record<StepVariant, string> = {
    neutral: "text-gray-500",
    pass:    "text-green-600",
    warn:    "text-amber-600",
    pending: "text-gray-300",
  };
  return (
    <div className="flex flex-col items-center flex-1 px-1">
      {/* Dot sits on the connector line; ring punches through it cleanly */}
      <div className={`h-3 w-3 rounded-full ring-[3px] ring-white shrink-0 ${dotColors[variant]}`} />
      <span className={`text-xs font-semibold mt-2 text-center ${labelColors[variant]}`}>{label}</span>
      <div className={`mt-0.5 text-[11px] text-center leading-relaxed ${detailColors[variant]}`}>{detail}</div>
    </div>
  );
}

function StatCard({
  label, value, highlight, green,
}: {
  label: string; value: string; highlight?: boolean; green?: boolean;
}) {
  return (
    <div className="flex-1 min-w-0 rounded-lg border border-gray-100 bg-gray-50 px-4 py-3 text-center">
      <p className={`text-xl font-bold tabular-nums ${
        highlight ? "text-red-600" : green ? "text-green-700" : "text-gray-900"
      }`}>
        {value}
      </p>
      <p className="mt-0.5 text-[10px] uppercase tracking-wider text-gray-400">{label}</p>
    </div>
  );
}

function AIProcessingTimeline({
  invoice,
  summary,
}: {
  invoice: { submitted_at: string | null; processed_at?: string | null; status: string; triage_risk_level?: string | null };
  summary: import("@/lib/types").ValidationSummary | null;
}) {
  const isProcessed = !!summary;
  const total = summary?.total_lines ?? 0;
  // Use line-level counts (not exception record counts) for consistent units across steps
  const linesWithSpendExcs = summary?.lines_with_spend_exceptions ?? 0;
  const linesWithIssues = summary?.lines_with_exceptions ?? 0;
  const validated = summary?.lines_validated ?? 0;
  const denied = summary?.lines_denied ?? 0;
  const spendVariant: StepVariant = !isProcessed ? "pending" : linesWithSpendExcs === 0 ? "pass" : "warn";
  const resultVariant: StepVariant = !isProcessed ? "pending" : invoice.status === "APPROVED" ? "pass" : "warn";

  const fmtMoney = (v: string | null | undefined) => {
    const n = parseFloat(v ?? "0");
    if (isNaN(n)) return "—";
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
  };

  return (
    <div className="mb-6 rounded-xl border border-gray-200 bg-white shadow-sm px-6 py-5">
      <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-5">
        ✦ AI Processing
      </p>

      {/* Timeline steps — dots sit on the connector line */}
      <div className="relative flex items-start">
        <div className="absolute top-[6px] left-0 right-0 h-px bg-gray-200 mx-8" />
        <TimelineStep
          label="Received"
          detail={
            isProcessed ? (
              <>
                <span>{fmt(invoice.submitted_at)}</span>
                <span className="block text-gray-400 mt-0.5">
                  {total} line{total !== 1 ? "s" : ""} · {fmtMoney(summary?.total_billed)}
                </span>
              </>
            ) : fmt(invoice.submitted_at)
          }
          variant={invoice.submitted_at ? "neutral" : "pending"}
        />
        <TimelineStep
          label="Classified"
          detail={isProcessed ? `${total} line${total !== 1 ? "s" : ""} mapped` : "Pending"}
          variant={isProcessed ? "neutral" : "pending"}
        />
        <TimelineStep
          label="Spend Audit"
          detail={isProcessed
            ? (linesWithSpendExcs === 0
              ? "All passed"
              : `${linesWithSpendExcs} line${linesWithSpendExcs !== 1 ? "s" : ""} flagged`)
            : "Pending"}
          variant={spendVariant}
        />
        <TimelineStep
          label={invoice.status === "APPROVED" ? "Auto-Approved" : isProcessed ? "Flagged for Review" : "Pending"}
          detail={
            invoice.status === "APPROVED"
              ? "No action needed"
              : isProcessed
              ? (linesWithSpendExcs === 0
                  ? "Classification only"
                  : `${linesWithSpendExcs} line${linesWithSpendExcs !== 1 ? "s" : ""} need attention`)
              : "—"
          }
          variant={resultVariant}
        />
      </div>

      {/* Outcome stats — spend audit perspective only; classification handled in mapping queue */}
      {isProcessed && (
        <div className="mt-6 pt-5 border-t border-gray-100 flex gap-3">
          <StatCard label="Clean Lines" value={String(total - linesWithSpendExcs)} />
          <StatCard label="Spend Exceptions" value={String(linesWithSpendExcs)} highlight={linesWithSpendExcs > 0} />
          <StatCard label="Submitted" value={fmtMoney(summary?.total_billed)} />
          <StatCard label="Payable" value={fmtMoney(summary?.total_payable)} green />
          {denied > 0 && (
            <StatCard label="Denied" value={String(denied)} highlight />
          )}
        </div>
      )}
    </div>
  );
}

// ── Triage panel ──────────────────────────────────────────────────────────────

const TRIAGE_COLORS: Record<string, { border: string; bg: string; badge: string; text: string }> = {
  LOW:      { border: "border-green-200", bg: "bg-green-50", badge: "bg-green-100 text-green-800", text: "text-green-700" },
  MEDIUM:   { border: "border-amber-200", bg: "bg-amber-50", badge: "bg-amber-100 text-amber-800", text: "text-amber-700" },
  HIGH:     { border: "border-red-200",   bg: "bg-red-50",   badge: "bg-red-100 text-red-800",     text: "text-red-700"  },
  CRITICAL: { border: "border-red-300",   bg: "bg-red-50",   badge: "bg-red-600 text-white",       text: "text-red-800"  },
};

function TriagePanel({
  level,
  notes,
  expanded,
  onToggle,
}: {
  level: string;
  notes: string | null;
  expanded: boolean;
  onToggle: () => void;
}) {
  const c = TRIAGE_COLORS[level] ?? TRIAGE_COLORS.MEDIUM;
  const isElevated = level === "HIGH" || level === "CRITICAL";
  const factors = notes ? notes.split("\n").filter(Boolean) : [];

  return (
    <div
      className={`mb-6 rounded-xl border shadow-sm overflow-hidden ${
        isElevated ? `${c.border} ${c.bg}` : "border-gray-200 bg-white"
      }`}
    >
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between px-6 py-3 text-left hover:bg-black/[0.02] transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold text-gray-700">✦ AI Triage</span>
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${c.badge}`}>
            {level}
          </span>
          {factors.length > 0 && !expanded && (
            <span className={`text-xs ${c.text}`}>
              {factors.length} risk factor{factors.length !== 1 ? "s" : ""} — click to expand
            </span>
          )}
        </div>
        <span className="text-gray-400 text-xs">{expanded ? "▲" : "▼"}</span>
      </button>
      {expanded && factors.length > 0 && (
        <div className="border-t border-gray-100 px-6 py-4">
          <ul className={`space-y-1.5 text-sm ${c.text}`}>
            {factors.map((f, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="mt-0.5 shrink-0">•</span>
                <span>{f}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ── Inline Dialog ─────────────────────────────────────────────────────────────
function Dialog({
  open,
  title,
  children,
  onClose,
}: {
  open: boolean;
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b px-6 py-4">
          <h2 className="text-base font-semibold text-gray-900">{title}</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
          >
            ✕
          </button>
        </div>
        <div className="px-6 py-5">{children}</div>
      </div>
    </div>
  );
}

// ── Resolution action config ──────────────────────────────────────────────────
const RESOLUTION_OPTIONS: {
  value: string;
  label: string;
  hint: string;
  accepting: boolean;
}[] = [
  {
    value: "WAIVED",
    label: "Waive — accept as billed",
    hint: "Rule waived for this instance; line paid as submitted",
    accepting: true,
  },
  {
    value: "ACCEPTED_REDUCTION",
    label: "Accept reduction",
    hint: "Supplier agrees to the contracted / expected amount",
    accepting: true,
  },
  {
    value: "HELD_CONTRACT_RATE",
    label: "Hold contract rate",
    hint: "Contract rate enforced; payment capped at expected amount",
    accepting: true,
  },
  {
    value: "RECLASSIFIED",
    label: "Reclassified",
    hint: "Line reclassified to a different taxonomy code; billing accepted",
    accepting: true,
  },
  {
    value: "DENIED",
    label: "Deny — reject line",
    hint: "Line rejected; supplier must correct and resubmit",
    accepting: false,
  },
];

/** Pick the best default resolution action based on the exception's required_action. */
function defaultResolutionAction(requiredAction: string): string {
  switch (requiredAction) {
    case "ACCEPT_REDUCTION":        return "ACCEPTED_REDUCTION";
    case "ESTABLISH_CONTRACT_RATE": return "HELD_CONTRACT_RATE";
    case "REQUEST_RECLASSIFICATION":return "RECLASSIFIED";
    case "REUPLOAD":                return "DENIED";
    // Supplier billing outside contracted scope or with no active contract —
    // these are not resolvable by the carrier adding a rate; denial is the
    // appropriate action. Carrier can override to WAIVED if exceptional circumstances.
    case "OUT_OF_SCOPE":            return "DENIED";
    case "NO_ACTIVE_CONTRACT":      return "DENIED";
    case "ATTACH_DOC":
    case "NONE":
    default:                        return "WAIVED";
  }
}

// ── Exception resolve row ─────────────────────────────────────────────────────
function ExceptionRow({
  exc,
  invoiceId,
  lineClassificationSuggestion,
}: {
  exc: LineItemCarrierView["exceptions"][number];
  invoiceId: string;
  lineClassificationSuggestion: LineItemCarrierView["ai_classification_suggestion"];
}) {
  const qc = useQueryClient();
  const toast = useToast();
  // Pre-select in priority order:
  //   1. AI exception recommendation (from exception_resolver)
  //   2. RECLASSIFIED — when the parent line has a HIGH/MEDIUM confidence classification
  //      suggestion, that's exactly what the carrier should do: reclassify
  //   3. Rule-based default from required_action
  const [action, setAction] = useState<string>(() => {
    if (exc.ai_recommendation) return exc.ai_recommendation;
    if (
      lineClassificationSuggestion?.verdict === "SUGGESTED" &&
      (lineClassificationSuggestion.confidence === "HIGH" ||
        lineClassificationSuggestion.confidence === "MEDIUM")
    ) {
      return "RECLASSIFIED";
    }
    return defaultResolutionAction(exc.required_action);
  });
  const [notes, setNotes] = useState<string>(() => exc.ai_reasoning ?? "");

  const resolveMut = useMutation({
    mutationFn: () => resolveAdminException(exc.exception_id, action, notes),
    onSuccess: (data: { invoice_status?: string; line_status?: string }) => {
      qc.invalidateQueries({ queryKey: ["admin-invoice", invoiceId] });
      qc.invalidateQueries({ queryKey: ["admin-invoice-lines", invoiceId] });

      const opt = RESOLUTION_OPTIONS.find((o) => o.value === action);
      if (data?.invoice_status === "APPROVED") {
        toast.success("Invoice auto-approved", "All exceptions resolved — invoice is ready for export.");
      } else if (data?.invoice_status === "PENDING_CARRIER_REVIEW") {
        toast.success("All exceptions resolved", "Invoice is ready to approve.");
      } else if (action === "DENIED" && exc.required_action === "OUT_OF_SCOPE") {
        toast.warning("Line denied — out of scope", "Supplier billed outside their contracted service domain.");
      } else if (action === "DENIED" && exc.required_action === "NO_ACTIVE_CONTRACT") {
        toast.warning("Line denied — no active contract", "No executed contract was in effect at time of service.");
      } else if (action === "DENIED") {
        toast.warning("Line denied", "Exception recorded — invoice can still be approved for remaining lines.");
      } else {
        toast.info(`Exception resolved: ${opt?.label ?? action}`);
      }
    },
    onError: (err: Error) => {
      toast.error("Could not resolve exception", err.message);
    },
  });

  const isDenying = action === "DENIED";
  const isAiAction = !!exc.ai_recommendation && action === exc.ai_recommendation;
  const selectedOption = RESOLUTION_OPTIONS.find((o) => o.value === action);
  const aiOption = exc.ai_recommendation
    ? RESOLUTION_OPTIONS.find((o) => o.value === exc.ai_recommendation)
    : null;
  const ctaLabel = isAiAction ? "Accept & Send" : isDenying ? "Deny & Send" : "Resolve";

  if (exc.status !== "OPEN" && exc.status !== "SUPPLIER_RESPONDED" && exc.status !== "CARRIER_REVIEWING") {
    const isResolved = exc.status === "RESOLVED" || exc.status === "WAIVED";
    return (
      <div className={`rounded px-3 py-2 text-xs ${isResolved ? "bg-green-50 text-green-700" : "bg-gray-50 text-gray-500"}`}>
        <div className="flex items-start gap-2">
          <StatusBadge status={exc.status} />
          <span className="flex-1">{exc.message}</span>
          {exc.resolution_action && (
            <span className="font-medium shrink-0">
              {RESOLUTION_OPTIONS.find((o) => o.value === exc.resolution_action)?.label
                ?? exc.resolution_action}
            </span>
          )}
        </div>
        {/* AI accuracy indicator — only shown when an AI recommendation was made */}
        {exc.ai_recommendation !== null && exc.ai_recommendation_accepted !== null && (
          <div className="mt-1.5 text-[10px]">
            {exc.ai_recommendation_accepted ? (
              <span className="text-green-600">✓ AI prediction followed</span>
            ) : (
              <span className="text-gray-400">
                ↺ AI predicted{" "}
                {RESOLUTION_OPTIONS.find((o) => o.value === exc.ai_recommendation)?.label
                  ?? exc.ai_recommendation}{" "}
                — carrier overrode
              </span>
            )}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="rounded border border-orange-200 bg-orange-50 p-3 text-xs space-y-2">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <StatusBadge status={exc.status} />
          <span className="font-mono text-gray-500">{exc.required_action}</span>
        </div>
        <p className="text-gray-800">{exc.message}</p>
        {exc.supplier_response && (
          <p className="mt-1 italic text-gray-500">
            Supplier note: {exc.supplier_response}
          </p>
        )}
      </div>

      {/* AI response assessment card — shown after supplier responds */}
      {exc.supplier_response && exc.ai_response_assessment && (
        <div className={`rounded border-l-4 bg-white pl-3 pr-2 py-2 ${
          exc.ai_response_assessment === "SUFFICIENT"
            ? "border-green-400"
            : exc.ai_response_assessment === "PARTIAL"
            ? "border-amber-400"
            : "border-red-400"
        }`}>
          <p className={`text-xs font-semibold ${
            exc.ai_response_assessment === "SUFFICIENT"
              ? "text-green-700"
              : exc.ai_response_assessment === "PARTIAL"
              ? "text-amber-700"
              : "text-red-700"
          }`}>
            ✦ AI response review:{" "}
            {exc.ai_response_assessment === "SUFFICIENT"
              ? "Response appears sufficient"
              : exc.ai_response_assessment === "PARTIAL"
              ? "Response partially addresses the issue"
              : "Response insufficient — consider denying"}
          </p>
          {exc.ai_response_reasoning && (
            <p className="mt-1 text-xs leading-relaxed text-gray-600">
              {exc.ai_response_reasoning}
            </p>
          )}
        </div>
      )}

      {/* AI recommendation card */}
      {exc.ai_recommendation && (
        <div className="rounded border-l-4 border-amber-400 bg-white pl-3 pr-2 py-2">
          <p className="text-xs font-semibold text-amber-700">
            ✦ AI suggests: {aiOption?.label ?? exc.ai_recommendation}
          </p>
          {exc.ai_reasoning && (
            <p className="mt-1 text-xs leading-relaxed text-gray-600">{exc.ai_reasoning}</p>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-start gap-2">
        <div className="flex flex-col gap-1">
          <select
            value={action}
            onChange={(e) => setAction(e.target.value)}
            className={`rounded border px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500 ${
              isDenying
                ? "border-red-300 bg-red-50 text-red-700"
                : "border-gray-300 bg-white text-gray-800"
            }`}
          >
            {RESOLUTION_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          {selectedOption && (
            <p className="text-gray-400 pl-0.5">{selectedOption.hint}</p>
          )}
        </div>

        <div className="flex flex-col flex-1 min-w-32 gap-0.5">
          <input
            type="text"
            placeholder={
              exc.ai_reasoning
                ? "AI reasoning (editable)"
                : isDenying
                ? "Reason for denial (required)"
                : "Notes (optional)"
            }
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className={`rounded border px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500 ${
              isDenying && !notes.trim()
                ? "border-red-300 bg-red-50"
                : "border-gray-300 bg-white"
            }`}
          />
          {exc.ai_reasoning && notes === exc.ai_reasoning && (
            <p className="text-[10px] text-amber-500 pl-0.5">
              ✦ Pre-filled from AI reasoning — edit before sending if needed
            </p>
          )}
        </div>

        <Button
          size="sm"
          variant={isDenying ? "danger" : "primary"}
          loading={resolveMut.isPending}
          disabled={isDenying && !notes.trim()}
          onClick={() => resolveMut.mutate()}
        >
          {ctaLabel}
        </Button>
      </div>

    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatInvoiceDate(iso: string) {
  // ISO date strings like "2025-01-15" — parse as local date to avoid TZ shift
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default function AdminInvoiceDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const { id } = params;
  const qc = useQueryClient();

  const [expandedLines, setExpandedLines] = useState<Set<string>>(new Set());
  const [showApproveConfirm, setShowApproveConfirm] = useState(false);
  const [approvalNotes, setApprovalNotes] = useState("");
  const [exportError, setExportError] = useState<string | null>(null);
  const [triageExpanded, setTriageExpanded] = useState(false);
  const [showBulkModal, setShowBulkModal] = useState(false);
  const toast = useToast();

  // ── Inline classification correction ──────────────────────────────────────
  const [editingLineId, setEditingLineId] = useState<string | null>(null);
  const [editTaxonomy, setEditTaxonomy]   = useState("");
  const [editComponent, setEditComponent] = useState("");
  const [editScope, setEditScope]         = useState<"this_line" | "this_supplier" | "global">("this_supplier");
  const [editNotes, setEditNotes]         = useState("");

  const overrideMut = useMutation({
    mutationFn: () =>
      overrideMapping(editingLineId!, editTaxonomy, editComponent, editScope, editNotes || undefined),
    onSuccess: () => {
      setEditingLineId(null);
      qc.invalidateQueries({ queryKey: ["admin-invoice-lines", id] });
      qc.invalidateQueries({ queryKey: ["admin-invoice", id] });
      toast.success(
        "Classification updated",
        editScope !== "this_line"
          ? "Saved as a mapping rule — future similar lines will classify automatically."
          : "Updated for this line only.",
      );
    },
    onError: (err: Error) => toast.error("Could not update classification", err.message),
  });

  const { data: invoice, isLoading: loadingInvoice } = useQuery({
    queryKey: ["admin-invoice", id],
    queryFn: () => getAdminInvoice(id),
  });

  const { data: lines, isLoading: loadingLines } = useQuery({
    queryKey: ["admin-invoice-lines", id],
    queryFn: () => getAdminInvoiceLines(id),
    enabled: !!invoice,
  });

  const approveMut = useMutation({
    mutationFn: () => approveAdminInvoice(id, undefined, approvalNotes || undefined),
    onSuccess: () => {
      setShowApproveConfirm(false);
      qc.invalidateQueries({ queryKey: ["admin-invoice", id] });
    },
  });

  // ── Bulk AI resolve ────────────────────────────────────────────────────────
  const aiResolvableExceptions = (lines ?? []).flatMap((line) =>
    line.exceptions
      .filter(
        (exc) =>
          exc.ai_recommendation &&
          ["OPEN", "SUPPLIER_RESPONDED", "CARRIER_REVIEWING"].includes(exc.status)
      )
      .map((exc) => ({
        exc,
        lineNumber: line.line_number,
        description: line.raw_description,
      }))
  );

  const bulkResolveMut = useMutation({
    mutationFn: async () => {
      for (const { exc } of aiResolvableExceptions) {
        await resolveAdminException(
          exc.exception_id,
          exc.ai_recommendation!,
          exc.ai_reasoning ?? ""
        );
      }
    },
    onSuccess: () => {
      setShowBulkModal(false);
      qc.invalidateQueries({ queryKey: ["admin-invoice", id] });
      qc.invalidateQueries({ queryKey: ["admin-invoice-lines", id] });
      toast.success(
        "AI recommendations applied",
        `${aiResolvableExceptions.length} exception${aiResolvableExceptions.length !== 1 ? "s" : ""} resolved.`
      );
    },
    onError: (err: Error) => {
      toast.error("Bulk resolve failed", err.message);
    },
  });

  async function handleExport() {
    setExportError(null);
    try {
      const blob = await exportAdminInvoice(id);
      downloadBlob(
        blob,
        `approved_${invoice?.invoice_number ?? id}_${new Date().toISOString().slice(0, 10)}.csv`,
      );
      qc.invalidateQueries({ queryKey: ["admin-invoice", id] });
    } catch (e) {
      setExportError((e as Error).message);
    }
  }

  function toggleLine(lineId: string) {
    setExpandedLines((prev) => {
      const next = new Set(prev);
      if (next.has(lineId)) next.delete(lineId);
      else next.add(lineId);
      return next;
    });
  }

  if (loadingInvoice) {
    return (
      <div className="flex min-h-64 items-center justify-center">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
      </div>
    );
  }

  if (!invoice) {
    return (
      <div className="py-16 text-center text-gray-500">Invoice not found.</div>
    );
  }

  const canApprove =
    invoice.status === "PENDING_CARRIER_REVIEW" ||
    invoice.status === "CARRIER_REVIEWING";
  const canExport = invoice.status === "APPROVED";

  return (
    <>
      {/* Bulk AI resolve confirmation dialog */}
      <Dialog
        open={showBulkModal}
        title={`Apply ${aiResolvableExceptions.length} AI Recommendation${aiResolvableExceptions.length !== 1 ? "s" : ""}`}
        onClose={() => setShowBulkModal(false)}
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-600">
            The following AI recommendations will be applied and the supplier will be notified for each exception:
          </p>
          <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
            {aiResolvableExceptions.map(({ exc, lineNumber, description }) => {
              const opt = RESOLUTION_OPTIONS.find((o) => o.value === exc.ai_recommendation);
              return (
                <div
                  key={exc.exception_id}
                  className="rounded border border-gray-200 bg-gray-50 px-3 py-2 text-xs"
                >
                  <p className="font-medium text-gray-700">
                    Line {lineNumber} —{" "}
                    <span className="font-normal text-gray-500 truncate">{description}</span>
                  </p>
                  <p
                    className={`mt-0.5 font-semibold ${
                      exc.ai_recommendation === "DENIED" ? "text-red-600" : "text-green-700"
                    }`}
                  >
                    → {opt?.label ?? exc.ai_recommendation}
                  </p>
                </div>
              );
            })}
          </div>
          {bulkResolveMut.isError && (
            <p className="text-sm text-red-600">
              {(bulkResolveMut.error as Error).message}
            </p>
          )}
          <div className="flex justify-end gap-3">
            <Button variant="ghost" onClick={() => setShowBulkModal(false)}>
              Cancel
            </Button>
            <Button
              loading={bulkResolveMut.isPending}
              onClick={() => bulkResolveMut.mutate()}
            >
              Apply {aiResolvableExceptions.length} Recommendation{aiResolvableExceptions.length !== 1 ? "s" : ""}
            </Button>
          </div>
        </div>
      </Dialog>

      {/* Approve confirmation dialog */}
      <Dialog
        open={showApproveConfirm}
        title="Approve Invoice"
        onClose={() => setShowApproveConfirm(false)}
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-600">
            Approving{" "}
            <strong className="font-mono">{invoice.invoice_number}</strong> will
            mark it ready for export. Any remaining open exceptions will be
            recorded.
          </p>
          <div>
            <label className="block text-sm font-medium text-gray-700">
              Approval notes (optional)
            </label>
            <textarea
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
              rows={3}
              value={approvalNotes}
              onChange={(e) => setApprovalNotes(e.target.value)}
              placeholder="Any notes for the record…"
            />
          </div>
          {approveMut.isError && (
            <p className="text-sm text-red-600">
              {(approveMut.error as Error).message}
            </p>
          )}
          <div className="flex justify-end gap-3">
            <Button
              variant="ghost"
              onClick={() => setShowApproveConfirm(false)}
            >
              Cancel
            </Button>
            <Button
              loading={approveMut.isPending}
              onClick={() => approveMut.mutate()}
            >
              Confirm Approval
            </Button>
          </div>
        </div>
      </Dialog>

      {/* Sticky action bar */}
      <div className="sticky top-0 z-10 -mx-4 mb-6 border-b bg-white px-4 py-3 shadow-sm sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <Link
              href="/admin/invoices"
              className="shrink-0 text-sm text-gray-500 hover:text-gray-700"
            >
              ← Queue
            </Link>
            <span className="text-gray-300">/</span>
            <h1 className="truncate text-xl font-bold font-mono text-gray-900">
              {invoice.invoice_number}
            </h1>
            <StatusBadge status={invoice.status} />
          </div>
          <div className="flex shrink-0 items-center gap-3">
            {canApprove && (
              <Button onClick={() => setShowApproveConfirm(true)}>
                ✓ Approve
              </Button>
            )}
            {canExport && (
              <Button variant="secondary" onClick={handleExport}>
                ↓ Export CSV
              </Button>
            )}
          </div>
        </div>
      </div>

      {exportError && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {exportError}
        </div>
      )}

      {/* Invoice metadata */}
      <div className="mb-6 grid grid-cols-2 gap-4 rounded-xl border bg-white p-6 shadow-sm sm:grid-cols-4">
        <div>
          <p className="text-xs font-medium uppercase text-gray-400">
            Supplier
          </p>
          <p className="mt-1 text-sm font-semibold text-gray-900">
            {invoice.supplier_name ?? "—"}
          </p>
        </div>
        <div>
          <p className="text-xs font-medium uppercase text-gray-400">
            Contract
          </p>
          <p className="mt-1 text-sm text-gray-700">
            {invoice.contract_name ?? "—"}
          </p>
        </div>
        <div>
          <p className="text-xs font-medium uppercase text-gray-400">
            Invoice date
          </p>
          <p className="mt-1 text-sm text-gray-700">{formatInvoiceDate(invoice.invoice_date)}</p>
        </div>
        <div>
          <p className="text-xs font-medium uppercase text-gray-400">
            Submitted
          </p>
          <p className="mt-1 text-sm text-gray-700">
            {formatDate(invoice.submitted_at)}
          </p>
        </div>
      </div>

      {/* AI Processing Timeline */}
      <AIProcessingTimeline
        invoice={invoice}
        summary={invoice.validation_summary}
      />

      {/* AI Triage panel */}
      {invoice.triage_risk_level && (
        <TriagePanel
          level={invoice.triage_risk_level}
          notes={invoice.triage_notes}
          expanded={triageExpanded}
          onToggle={() => setTriageExpanded((v) => !v)}
        />
      )}

      {/* Line items */}
      <div className="rounded-xl border bg-white shadow-sm overflow-hidden">
        <div className="border-b px-6 py-4 flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">Line Items</h2>
          {aiResolvableExceptions.length > 0 && (
            <button
              onClick={() => setShowBulkModal(true)}
              className="flex items-center gap-1.5 rounded-lg bg-amber-50 border border-amber-200 px-3 py-1.5 text-xs font-semibold text-amber-800 hover:bg-amber-100 transition-colors"
            >
              ✦ Apply {aiResolvableExceptions.length} AI Recommendation{aiResolvableExceptions.length !== 1 ? "s" : ""}
            </button>
          )}
        </div>
        {loadingLines ? (
          <div className="flex justify-center py-10">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
          </div>
        ) : (
          <table className="min-w-full divide-y divide-gray-100 text-sm">
            <thead className="bg-gray-50">
              {/* Group label row */}
              <tr className="border-b border-gray-200">
                <th rowSpan={2} className="px-4 py-2 text-left text-xs font-semibold uppercase text-gray-500 w-10">
                  #
                </th>
                <th rowSpan={2} className="px-4 py-2 text-left text-xs font-semibold uppercase text-gray-500">
                  Description
                </th>
                <th colSpan={2} className="px-4 py-1.5 text-center text-xs font-semibold uppercase tracking-wide text-blue-700 bg-blue-50 border-b border-blue-100">
                  Spend Classification
                </th>
                <th colSpan={3} className="px-4 py-1.5 text-center text-xs font-semibold uppercase tracking-wide text-gray-500 bg-gray-50 border-b border-gray-200">
                  Rate &amp; Guideline Audit
                </th>
                <th rowSpan={2} className="w-8" />
              </tr>
              {/* Column name row */}
              <tr>
                <th className="px-4 py-2 text-left text-xs font-semibold uppercase text-gray-500">
                  Taxonomy
                </th>
                <th className="px-4 py-2 text-left text-xs font-semibold uppercase text-gray-500">
                  Conf.
                </th>
                <th className="px-4 py-2 text-right text-xs font-semibold uppercase text-gray-500">
                  Billed
                </th>
                <th className="px-4 py-2 text-right text-xs font-semibold uppercase text-gray-500">
                  Expected
                </th>
                <th className="px-4 py-2 text-left text-xs font-semibold uppercase text-gray-500">
                  Status
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {lines?.map((line) => {
                const isExpanded = expandedLines.has(line.id);
                const hasIssues =
                  line.exceptions.length > 0 ||
                  line.needs_review ||
                  (!line.taxonomy_code && !!line.ai_classification_suggestion);
                return (
                  <>
                    <tr
                      key={line.id}
                      className={`transition-colors ${hasIssues ? "cursor-pointer hover:bg-amber-50" : "hover:bg-gray-50"}`}
                      onClick={() => hasIssues && toggleLine(line.id)}
                    >
                      <td className="px-4 py-3 text-gray-400">
                        {line.line_number}
                      </td>
                      <td className="px-4 py-3">
                        <p className="font-medium text-gray-900 leading-snug">
                          {line.raw_description}
                        </p>
                        {(line.claim_number || line.service_date) && (
                          <p className="text-xs text-gray-400 mt-0.5 flex items-center gap-1.5">
                            {line.claim_number && (
                              <span>Claim {line.claim_number}</span>
                            )}
                            {line.claim_number && line.service_date && (
                              <span className="text-gray-300">·</span>
                            )}
                            {line.service_date && (
                              <span>
                                {(() => {
                                  const [y, m, d] = line.service_date!.split("-").map(Number);
                                  return new Date(y, m - 1, d).toLocaleDateString("en-US", {
                                    month: "short", day: "numeric", year: "numeric",
                                  });
                                })()}
                              </span>
                            )}
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {/* Taxonomy display + inline correction */}
                        <div className="flex items-start justify-between gap-1 group/tax">
                          <div className="min-w-0">
                            {line.taxonomy_code ? (
                              <>
                                <p className="font-mono text-xs text-gray-700">
                                  {line.taxonomy_code}
                                </p>
                                {line.taxonomy_label && (
                                  <p className="text-xs text-gray-400 mt-0.5 truncate max-w-40">
                                    {line.taxonomy_label}
                                  </p>
                                )}
                              </>
                            ) : (
                              <span className="text-gray-300">—</span>
                            )}
                          </div>
                          {/* ✏ edit button — visible on row hover */}
                          <button
                            className="shrink-0 mt-0.5 opacity-0 group-hover/tax:opacity-100 transition-opacity text-gray-400 hover:text-blue-600 text-xs"
                            title="Correct classification"
                            onClick={(e) => {
                              e.stopPropagation();
                              if (editingLineId === line.id) {
                                setEditingLineId(null);
                              } else {
                                setEditTaxonomy(line.taxonomy_code ?? "");
                                setEditComponent(line.billing_component ?? "");
                                setEditScope("this_supplier");
                                setEditNotes("");
                                setEditingLineId(line.id);
                              }
                            }}
                          >
                            ✏
                          </button>
                        </div>

                        {/* Inline correction form */}
                        {editingLineId === line.id && (
                          <div
                            className="mt-2 space-y-2 rounded border border-blue-200 bg-blue-50 p-3"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <p className="text-[10px] font-semibold uppercase tracking-wide text-blue-700">
                              Correct Classification
                            </p>
                            <div className="grid grid-cols-2 gap-2">
                              <input
                                value={editTaxonomy}
                                onChange={(e) => setEditTaxonomy(e.target.value)}
                                placeholder="Taxonomy code"
                                className="rounded border border-gray-300 bg-white px-2 py-1 font-mono text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                              />
                              <input
                                value={editComponent}
                                onChange={(e) => setEditComponent(e.target.value)}
                                placeholder="Billing component"
                                className="rounded border border-gray-300 bg-white px-2 py-1 font-mono text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                              />
                            </div>
                            <select
                              value={editScope}
                              onChange={(e) =>
                                setEditScope(e.target.value as typeof editScope)
                              }
                              className="w-full rounded border border-gray-300 bg-white px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                            >
                              <option value="this_line">This line only</option>
                              <option value="this_supplier">
                                This supplier — save as mapping rule ✦
                              </option>
                              <option value="global">
                                All suppliers — save as global rule ✦
                              </option>
                            </select>
                            <input
                              value={editNotes}
                              onChange={(e) => setEditNotes(e.target.value)}
                              placeholder="Notes (optional)"
                              className="w-full rounded border border-gray-300 bg-white px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                            />
                            <div className="flex gap-2">
                              <Button
                                size="sm"
                                loading={overrideMut.isPending}
                                disabled={
                                  !editTaxonomy.trim() || !editComponent.trim()
                                }
                                onClick={() => overrideMut.mutate()}
                              >
                                Save &amp; Learn
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => setEditingLineId(null)}
                              >
                                Cancel
                              </Button>
                            </div>
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {line.mapping_confidence ? (
                          <ConfidenceBadge confidence={line.mapping_confidence} />
                        ) : (
                          <span className="text-gray-300">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {(() => {
                          const qty = Number(line.raw_quantity);
                          const total = Number(line.raw_amount);
                          const unitSingular = line.raw_unit ? toUnitSingular(line.raw_unit) : null;
                          const showFormula = qty > 1;
                          const billedRate = showFormula ? total / qty : null;
                          return (
                            <>
                              {showFormula && billedRate !== null && (
                                <p className="text-[11px] text-gray-400 mb-0.5">
                                  {qty.toLocaleString()}{line.raw_unit ? ` ${line.raw_unit}` : ""} × ${billedRate.toFixed(2)}{unitSingular ? `/${unitSingular}` : ""}
                                </p>
                              )}
                              <p className="font-mono text-gray-900">${total.toFixed(2)}</p>
                            </>
                          );
                        })()}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {(() => {
                          // "No rate" only fires when the line was successfully classified
                          // but no contracted rate card exists (ESTABLISH_CONTRACT_RATE).
                          // Classification failures (REQUEST_RECLASSIFICATION) should show "—"
                          // because there's no taxonomy mapping yet, not a missing rate.
                          const hasNoRate = line.exceptions.some(
                            (ex) => ex.required_action === "ESTABLISH_CONTRACT_RATE"
                          );
                          if (hasNoRate) {
                            return (
                              <span
                                className="text-xs font-medium text-amber-600"
                                title="No contracted rate found for this service code"
                              >
                                No rate
                              </span>
                            );
                          }
                          if (!line.expected_amount) {
                            return <span className="text-gray-300">—</span>;
                          }
                          const qty = Number(line.raw_quantity);
                          const expected = Number(line.expected_amount);
                          const contractRate = line.mapped_rate ? Number(line.mapped_rate) : null;
                          const unitSingular = line.raw_unit ? toUnitSingular(line.raw_unit) : null;
                          const showFormula = qty > 1 && contractRate !== null;
                          const isOver = Number(line.raw_amount) > expected;
                          return (
                            <>
                              {showFormula && contractRate !== null && (
                                <p className="text-[11px] text-gray-400 mb-0.5">
                                  {qty.toLocaleString()}{line.raw_unit ? ` ${line.raw_unit}` : ""} × ${contractRate.toFixed(2)}{unitSingular ? `/${unitSingular}` : ""}
                                </p>
                              )}
                              <p className={`font-mono ${isOver ? "text-red-600" : "text-gray-700"}`}>
                                ${expected.toFixed(2)}
                              </p>
                            </>
                          );
                        })()}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <StatusBadge status={line.status} />
                          {line.exceptions.length > 0 && (
                            <span className="rounded-full bg-red-100 px-1.5 py-0.5 text-xs font-semibold text-red-700">
                              {line.exceptions.length}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-gray-400 text-xs">
                        {hasIssues && (isExpanded ? "▲" : "▼")}
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr key={`${line.id}-expanded`}>
                        <td colSpan={8} className="px-6 py-4 bg-gray-50 border-t border-gray-100">
                          {(() => {
                            const classificationExcs = line.exceptions.filter(
                              (e) => e.required_action === "REQUEST_RECLASSIFICATION"
                            );
                            const auditExcs = line.exceptions.filter(
                              (e) => e.required_action !== "REQUEST_RECLASSIFICATION"
                            );
                            const needsClassification =
                              line.needs_review ||
                              !line.taxonomy_code ||
                              classificationExcs.length > 0;

                            return (
                              <div className="space-y-3">
                                {/* ── Spend Classification panel ─────────────── */}
                                {needsClassification && (
                                  <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
                                    <p className="text-xs font-semibold uppercase tracking-wide text-blue-700 mb-2">
                                      🏷 Spend Classification — Action Needed
                                    </p>
                                    <p className="text-sm text-blue-800 mb-3">
                                      This service line{" "}
                                      {!line.taxonomy_code
                                        ? "has not been assigned to a spend bucket"
                                        : "has a low-confidence spend bucket assignment"}
                                      . Review and confirm or correct the classification
                                      before finalizing audit decisions.
                                    </p>
                                    <a
                                      href="/admin/mappings"
                                      className="inline-flex items-center gap-1 rounded bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 transition-colors"
                                    >
                                      → Go to Classification Review
                                    </a>
                                    {/* AI suggestion shown informational only */}
                                    {line.ai_classification_suggestion && (
                                      <div className="mt-3">
                                        <AiClassificationSuggestion
                                          suggestion={line.ai_classification_suggestion}
                                        />
                                      </div>
                                    )}
                                  </div>
                                )}

                                {/* ── Rate & Guideline Compliance panels ────── */}
                                {auditExcs.length > 0 && (() => {
                                  const rateExcs = auditExcs.filter(e => e.validation_type === "RATE");
                                  const guidelineExcs = auditExcs.filter(e => e.validation_type === "GUIDELINE");
                                  // Extract contract reference quote from guideline message
                                  function extractContractRef(msg: string): string | null {
                                    const m = msg.match(/Contract reference:\s*"([^"]+)"/);
                                    return m ? m[1] : null;
                                  }
                                  return (
                                    <div className={`space-y-3 ${needsClassification ? "opacity-60 pointer-events-none" : ""}`}>
                                      {needsClassification && (
                                        <p className="text-xs italic text-gray-400">
                                          Resolve the spend classification above before taking audit actions.
                                        </p>
                                      )}

                                      {/* Rate Compliance */}
                                      {rateExcs.length > 0 && (
                                        <div>
                                          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-1.5">
                                            💲 Rate Compliance
                                          </p>
                                          <div className="space-y-2">
                                            {rateExcs.map((exc) => (
                                              <ExceptionRow
                                                key={exc.exception_id}
                                                exc={exc}
                                                invoiceId={id}
                                                lineClassificationSuggestion={line.ai_classification_suggestion}
                                              />
                                            ))}
                                          </div>
                                        </div>
                                      )}

                                      {/* Guideline Compliance */}
                                      {guidelineExcs.length > 0 && (
                                        <div>
                                          <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600 mb-1.5">
                                            📋 Guideline Compliance
                                          </p>
                                          <div className="space-y-2">
                                            {guidelineExcs.map((exc) => {
                                              const contractRef = extractContractRef(exc.message);
                                              return (
                                                <div key={exc.exception_id}>
                                                  {contractRef && (
                                                    <blockquote className="mb-1.5 border-l-4 border-indigo-300 bg-indigo-50 pl-3 pr-2 py-1.5 text-xs text-indigo-800 rounded-r">
                                                      <span className="font-semibold text-indigo-500 text-[10px] uppercase tracking-wide">Contract rule: </span>
                                                      &ldquo;{contractRef}&rdquo;
                                                    </blockquote>
                                                  )}
                                                  <ExceptionRow
                                                    exc={exc}
                                                    invoiceId={id}
                                                    lineClassificationSuggestion={line.ai_classification_suggestion}
                                                  />
                                                </div>
                                              );
                                            })}
                                          </div>
                                        </div>
                                      )}
                                    </div>
                                  );
                                })()}

                                {/* Lines flagged for review with no exceptions yet */}
                                {needsClassification && auditExcs.length === 0 && classificationExcs.length === 0 && line.exceptions.length === 0 && (
                                  <p className="text-xs text-blue-600 mt-1">
                                    No contract audit exceptions on this line yet.
                                  </p>
                                )}
                              </div>
                            );
                          })()}
                        </td>
                      </tr>
                    )}
                  </>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
