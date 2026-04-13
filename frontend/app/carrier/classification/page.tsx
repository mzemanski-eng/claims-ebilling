"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  approveClassificationItem,
  bulkApproveClassificationItems,
  getClassificationStats,
  listClassificationQueue,
  rejectClassificationItem,
} from "@/lib/api";
import type {
  ClassificationQueueItem,
  ClassificationStats,
} from "@/lib/types";
import { DOMAIN_LABELS, TAXONOMY_OPTIONS } from "@/lib/taxonomy";
import { StatusBadge } from "@/components/status-badge";
import { useToast } from "@/components/toast";

// ── Helpers ────────────────────────────────────────────────────────────────────

function formatMoney(val: string | null | undefined) {
  if (!val) return "—";
  return `$${parseFloat(val).toLocaleString("en-US", { minimumFractionDigits: 2 })}`;
}

function formatDate(iso: string | null | undefined) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function confidenceBar(val: string | null) {
  if (!val) return null;
  const pct = Math.round(parseFloat(val) * 100);
  const color =
    pct >= 90 ? "bg-green-500" : pct >= 60 ? "bg-amber-400" : "bg-red-400";
  return (
    <div className="flex items-center gap-1.5">
      <div className="h-1.5 w-16 rounded-full bg-gray-200">
        <div className={`h-1.5 rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-500">{pct}%</span>
    </div>
  );
}

// ── Tab type ──────────────────────────────────────────────────────────────────

type Tab = "PENDING" | "NEEDS_REVIEW" | "APPROVED" | "REJECTED";

const TAB_LABELS: Record<Tab, string> = {
  PENDING: "Pending",
  NEEDS_REVIEW: "Needs Review",
  APPROVED: "Approved",
  REJECTED: "Rejected",
};

// ── Inline classify form (shown in the expanded row) ─────────────────────────

interface InlineClassifyFormProps {
  item: ClassificationQueueItem;
  onApprove: (code: string, component: string, notes: string) => void;
  onReject: () => void;
  isApproving: boolean;
}

/** Derive billing_component from a taxonomy code (last dot-separated segment). */
function billingComponentFromCode(code: string): string {
  const parts = code.split(".");
  return parts[parts.length - 1] ?? "";
}

function InlineClassifyForm({ item, onApprove, onReject, isApproving }: InlineClassifyFormProps) {
  const [code, setCode] = useState(item.ai_proposed_code ?? "");
  const [component, setComponent] = useState(item.ai_proposed_billing_component ?? "");
  const [notes, setNotes] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const isAiMatch = code.trim() !== "" && code.trim() === item.ai_proposed_code;
  const isDirty = code.trim() !== "" && code.trim() !== item.ai_proposed_code;

  // Filter taxonomy options by partial code or label match
  const suggestions = useMemo(() => {
    const q = code.trim().toLowerCase();
    if (!q) return TAXONOMY_OPTIONS.slice(0, 12);
    return TAXONOMY_OPTIONS.filter(
      (t) =>
        t.code.toLowerCase().includes(q) ||
        t.label.toLowerCase().includes(q) ||
        t.domain.toLowerCase().includes(q),
    ).slice(0, 12);
  }, [code]);

  function selectOption(opt: { code: string; billing_component?: string | null }) {
    const bc = opt.billing_component ?? billingComponentFromCode(opt.code);
    setCode(opt.code);
    setComponent(bc);
    setShowDropdown(false);
    inputRef.current?.blur();
  }

  // All AI suggestions (primary + alternatives) as a flat array for quick-pick chips
  const aiChips = [
    ...(item.ai_proposed_code
      ? [{ code: item.ai_proposed_code, billing_component: item.ai_proposed_billing_component, confidence: item.ai_confidence, isPrimary: true }]
      : []),
    ...(item.ai_alternatives ?? []).map((a) => ({ ...a, isPrimary: false })),
  ];

  return (
    <div className="mt-4 rounded-lg border border-gray-200 bg-white p-4">
      <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-500">
        Classify This Line
      </p>

      {/* AI suggestion chips — shown when AI gave proposals */}
      {aiChips.length > 0 ? (
        <div className="mb-3">
          <p className="mb-1.5 text-xs text-gray-400">AI suggestions — click to select:</p>
          <div className="flex flex-wrap gap-1.5">
            {aiChips.map((chip) => (
              <button
                type="button"
                key={chip.code}
                onClick={() => selectOption(chip)}
                className={`rounded-full border px-2.5 py-0.5 text-xs transition-colors ${
                  code === chip.code
                    ? "border-blue-500 bg-blue-100 text-blue-700 font-semibold"
                    : chip.isPrimary
                    ? "border-blue-200 bg-blue-50 text-blue-600 hover:bg-blue-100"
                    : "border-gray-200 text-gray-600 hover:border-blue-300 hover:bg-blue-50"
                }`}
              >
                {chip.isPrimary && <span className="mr-1">✦</span>}
                {chip.code}
                {chip.confidence && (
                  <span className="ml-1 font-normal opacity-60">
                    ({typeof chip.confidence === "string" && chip.confidence.includes(".")
                      ? `${Math.round(parseFloat(chip.confidence) * 100)}%`
                      : chip.confidence})
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="mb-3 rounded-md border border-amber-100 bg-amber-50 px-3 py-2 text-xs text-amber-700">
          No AI suggestion for this item — search the taxonomy below or push back to the supplier.
        </div>
      )}

      {/* Taxonomy code — searchable combobox */}
      <div className="grid grid-cols-2 gap-3">
        <div className="relative">
          <label className="mb-1 block text-xs font-medium text-gray-600">
            Taxonomy Code *
          </label>
          <input
            ref={inputRef}
            type="text"
            value={code}
            onChange={(e) => { setCode(e.target.value); setShowDropdown(true); if (!component || component === billingComponentFromCode(code)) setComponent(billingComponentFromCode(e.target.value)); }}
            onFocus={() => setShowDropdown(true)}
            onBlur={() => setTimeout(() => setShowDropdown(false), 150)}
            placeholder="Search or type a code…"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            autoComplete="off"
          />
          {/* Dropdown */}
          {showDropdown && suggestions.length > 0 && (
            <div className="absolute z-20 mt-1 max-h-52 w-80 overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-lg">
              {suggestions.map((opt) => (
                <button
                  key={opt.code}
                  type="button"
                  onMouseDown={() => selectOption({ code: opt.code, billing_component: billingComponentFromCode(opt.code) })}
                  className="flex w-full flex-col px-3 py-2 text-left hover:bg-blue-50"
                >
                  <span className="font-mono text-xs font-semibold text-blue-700">{opt.code}</span>
                  <span className="text-xs text-gray-500">{opt.label} · <span className="text-gray-400">{DOMAIN_LABELS[opt.domain] ?? opt.domain}</span></span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Billing component — auto-filled from taxonomy, editable for overrides */}
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-600">
            Billing Component *
          </label>
          <input
            type="text"
            value={component}
            onChange={(e) => setComponent(e.target.value)}
            placeholder="e.g. PROF_FEE"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
        </div>
      </div>

      {/* Provenance hint */}
      {isAiMatch && (
        <p className="mt-1.5 text-xs text-green-600">✓ Confirming AI suggestion — CARRIER_CONFIRMED mapping rule will be created.</p>
      )}
      {isDirty && (
        <p className="mt-1.5 text-xs text-amber-600">⚠ Overriding AI proposal — CARRIER_OVERRIDE mapping rule will be created.</p>
      )}

      {/* Notes */}
      <div className="mt-3">
        <label className="mb-1 block text-xs font-medium text-gray-600">
          Notes (optional)
        </label>
        <textarea
          rows={2}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Optional rationale for this classification decision…"
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
        />
      </div>

      {/* Actions */}
      <div className="mt-3 flex items-center gap-2">
        <button
          type="button"
          onClick={() => onApprove(code.trim(), component.trim(), notes)}
          disabled={isApproving || !code.trim() || !component.trim()}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {isApproving ? "Approving…" : "✓ Approve & Classify"}
        </button>
        <button
          type="button"
          onClick={onReject}
          disabled={isApproving}
          className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm font-semibold text-red-600 hover:bg-red-100 disabled:opacity-50 transition-colors"
        >
          Reject & Deny
        </button>
      </div>
    </div>
  );
}

// ── Reject modal ──────────────────────────────────────────────────────────────

interface RejectModalProps {
  item: ClassificationQueueItem;
  onConfirm: (notes: string) => void;
  onCancel: () => void;
  isPending: boolean;
}

function RejectModal({ item, onConfirm, onCancel, isPending }: RejectModalProps) {
  const [notes, setNotes] = useState("");
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
        <h2 className="text-lg font-bold text-gray-900">Reject Line Item</h2>
        <p className="mt-1 text-sm text-gray-500">
          The line will be marked <strong>DENIED</strong> and will not be paid.
          No mapping rule will be created.
        </p>
        <div className="mt-4 rounded-lg border border-gray-100 bg-gray-50 p-3 text-sm">
          <p className="font-medium text-gray-800 leading-snug">{item.raw_description}</p>
          <p className="mt-0.5 text-gray-500">{formatMoney(item.raw_amount)} · {item.supplier_name ?? "—"}</p>
        </div>
        <div className="mt-4">
          <label className="mb-1 block text-xs font-medium text-gray-600">
            Reason (optional)
          </label>
          <textarea
            rows={3}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Why is this line being denied?…"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-red-400 focus:outline-none"
          />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onCancel}
            disabled={isPending}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => onConfirm(notes)}
            disabled={isPending}
            className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
          >
            {isPending ? "Rejecting…" : "Reject & Deny"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Stats header card ─────────────────────────────────────────────────────────

function StatsHeader({ stats }: { stats: ClassificationStats }) {
  return (
    <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
      <div className="rounded-xl border bg-white p-4 shadow-sm">
        <p className="text-xs font-medium uppercase tracking-wide text-gray-400">
          Pending
        </p>
        <p className="mt-1 text-2xl font-bold text-amber-600">{stats.pending}</p>
        <p className="mt-0.5 text-xs text-gray-400">
          {formatMoney(stats.total_pending_amount)} total
        </p>
      </div>
      <div className="rounded-xl border bg-white p-4 shadow-sm">
        <p className="text-xs font-medium uppercase tracking-wide text-gray-400">
          Needs Review
        </p>
        <p className="mt-1 text-2xl font-bold text-red-600">{stats.needs_review}</p>
        <p className="mt-0.5 text-xs text-gray-400">No AI proposal</p>
      </div>
      <div className="rounded-xl border bg-white p-4 shadow-sm">
        <p className="text-xs font-medium uppercase tracking-wide text-gray-400">
          Approved Today
        </p>
        <p className="mt-1 text-2xl font-bold text-green-600">
          {stats.approved_today}
        </p>
      </div>
      <div className="rounded-xl border bg-white p-4 shadow-sm">
        <p className="text-xs font-medium uppercase tracking-wide text-gray-400">
          Rejected Today
        </p>
        <p className="mt-1 text-2xl font-bold text-gray-500">
          {stats.rejected_today}
        </p>
      </div>
    </div>
  );
}

// ── Row (expandable) ──────────────────────────────────────────────────────────

interface RowProps {
  item: ClassificationQueueItem;
  onApprove: (item: ClassificationQueueItem, code: string, component: string, notes: string) => void;
  onReject: (item: ClassificationQueueItem) => void;
  isWriteRole: boolean;
  isApproving: boolean;
}

function ClassificationRow({ item, onApprove, onReject, isWriteRole, isApproving }: RowProps) {
  const [expanded, setExpanded] = useState(false);
  const isActionable =
    isWriteRole &&
    (item.status === "PENDING" || item.status === "NEEDS_REVIEW");

  return (
    <>
      <tr
        className={`cursor-pointer transition-colors hover:bg-gray-50 ${
          item.status === "NEEDS_REVIEW" ? "bg-red-50/30" : ""
        }`}
        onClick={() => setExpanded((v) => !v)}
      >
        {/* Status */}
        <td className="px-4 py-3">
          <StatusBadge status={item.status === "NEEDS_REVIEW" ? "EXCEPTION" : item.status === "APPROVED" ? "VALIDATED" : item.status === "REJECTED" ? "DENIED" : "CLASSIFICATION_PENDING"} label={
            item.status === "NEEDS_REVIEW" ? "Needs Review"
              : item.status === "APPROVED" ? "Approved"
              : item.status === "REJECTED" ? "Rejected"
              : "Pending"
          } />
        </td>

        {/* Description */}
        <td className="px-4 py-3">
          <p className="max-w-xs truncate text-sm font-medium text-gray-900">
            {item.raw_description}
          </p>
          {item.invoice_number && (
            <p className="text-xs text-gray-400">
              {item.invoice_number}
              {item.line_number ? ` · line ${item.line_number}` : ""}
            </p>
          )}
        </td>

        {/* Supplier */}
        <td className="px-4 py-3 text-sm text-gray-600">
          {item.supplier_name ?? "—"}
        </td>

        {/* Amount */}
        <td className="px-4 py-3 text-right font-mono text-sm text-gray-700">
          {formatMoney(item.raw_amount)}
        </td>

        {/* AI proposal */}
        <td className="px-4 py-3">
          {item.ai_proposed_code ? (
            <div>
              <span className="font-mono text-xs font-semibold text-blue-700">
                {item.ai_proposed_code}
              </span>
              {item.ai_confidence && confidenceBar(item.ai_confidence)}
            </div>
          ) : (
            <span className="text-xs text-red-500 font-medium">No proposal</span>
          )}
        </td>

        {/* Approved code (for resolved items) */}
        <td className="px-4 py-3">
          {item.approved_code ? (
            <span className="font-mono text-xs font-semibold text-green-700">
              {item.approved_code}
            </span>
          ) : (
            <span className="text-gray-300 text-xs">—</span>
          )}
        </td>

        {/* Queued date */}
        <td className="px-4 py-3 text-xs text-gray-400">
          {formatDate(item.created_at)}
        </td>

        {/* Actions */}
        <td className="px-4 py-3 text-right" onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center justify-end gap-2">
            {isActionable && (
              <button
                onClick={(e) => { e.stopPropagation(); setExpanded((v) => !v); }}
                className={`rounded-md px-2.5 py-1 text-xs font-semibold transition-colors ${
                  expanded
                    ? "border border-gray-300 bg-white text-gray-500 hover:bg-gray-50"
                    : "bg-blue-600 text-white hover:bg-blue-700"
                }`}
              >
                {expanded ? "Close" : "Classify"}
              </button>
            )}
            {item.invoice_id && (
              <Link
                href={`/carrier/invoices/${item.invoice_id}`}
                title="View invoice"
                className="rounded-md border border-gray-200 px-2 py-1 text-xs text-gray-400 hover:bg-gray-50 hover:text-gray-600 transition-colors"
                onClick={(e) => e.stopPropagation()}
              >
                Invoice ↗
              </Link>
            )}
          </div>
        </td>
      </tr>

      {/* Expanded detail row */}
      {expanded && (
        <tr className="bg-gray-50">
          <td colSpan={8} className="px-6 py-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">

              {/* Always-visible: full description + line context */}
              <div className="sm:col-span-2 lg:col-span-1">
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-400">
                  Full Description
                </p>
                <p className="text-sm text-gray-800 leading-relaxed">
                  {item.raw_description}
                </p>
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
                  {item.invoice_number && (
                    <span>Invoice: <span className="font-medium text-gray-700">{item.invoice_number}</span></span>
                  )}
                  {item.line_number != null && (
                    <span>Line: <span className="font-medium text-gray-700">{item.line_number}</span></span>
                  )}
                  {item.supplier_name && (
                    <span>Supplier: <span className="font-medium text-gray-700">{item.supplier_name}</span></span>
                  )}
                  <span>Amount: <span className="font-medium text-gray-700">{formatMoney(String(item.raw_amount))}</span></span>
                </div>
              </div>

              {/* AI reasoning (when available) */}
              {item.ai_reasoning ? (
                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-400">
                    AI Reasoning
                  </p>
                  <p className="text-sm text-gray-700 leading-relaxed">
                    {item.ai_reasoning}
                  </p>
                </div>
              ) : (
                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-400">
                    AI Proposal
                  </p>
                  <p className="text-sm text-red-500 font-medium">No AI proposal available</p>
                  <p className="mt-1 text-xs text-gray-400">
                    This line fell below the AI confidence threshold. Enter a taxonomy
                    code manually using the Approve button.
                  </p>
                </div>
              )}

              {/* AI alternatives (when available) */}
              {item.ai_alternatives && item.ai_alternatives.length > 0 && (
                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-400">
                    AI Alternatives
                  </p>
                  <ul className="space-y-1">
                    {item.ai_alternatives.map((alt) => (
                      <li key={alt.code} className="flex items-center gap-2 text-sm">
                        <span className="font-mono font-semibold text-blue-700">
                          {alt.code}
                        </span>
                        {alt.billing_component && (
                          <span className="text-gray-400">
                            · {alt.billing_component}
                          </span>
                        )}
                        {alt.confidence && (
                          <span className={`text-xs font-medium ${
                            alt.confidence === "HIGH" ? "text-green-600"
                              : alt.confidence === "MEDIUM" ? "text-amber-500"
                              : "text-red-400"
                          }`}>
                            {alt.confidence}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Review notes (for resolved items) */}
              {item.review_notes && (
                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-400">
                    Review Notes
                  </p>
                  <p className="text-sm text-gray-700">{item.review_notes}</p>
                </div>
              )}

              {/* Resolved timestamp */}
              {item.reviewed_at && (
                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-400">
                    Resolved
                  </p>
                  <p className="text-sm text-gray-600">{formatDate(item.reviewed_at)}</p>
                </div>
              )}
            </div>

            {/* Inline classify form — only for actionable items */}
            {isActionable && (
              <InlineClassifyForm
                item={item}
                isApproving={isApproving}
                onApprove={(code, component, notes) => onApprove(item, code, component, notes)}
                onReject={() => onReject(item)}
              />
            )}
          </td>
        </tr>
      )}
    </>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

function ClassificationQueueContent() {
  const qc = useQueryClient();
  const toast = useToast();
  const searchParams = useSearchParams();

  // Optional invoice-level filter from ?invoice_id=<uuid>
  const invoiceIdFilter = searchParams.get("invoice_id") ?? undefined;
  const invoiceNumberFilter = searchParams.get("invoice_number") ?? undefined;

  const [activeTab, setActiveTab] = useState<Tab>("PENDING");
  const [tabInitialized, setTabInitialized] = useState(false);
  const [approvingItemId, setApprovingItemId] = useState<string | null>(null);
  const [rejectingItem, setRejectingItem] =
    useState<ClassificationQueueItem | null>(null);

  // Stats (always fresh — auto-refetch every 30s)
  const { data: stats } = useQuery<ClassificationStats>({
    queryKey: ["classification-stats"],
    queryFn: getClassificationStats,
    refetchInterval: 30_000,
  });

  // Re-run tab auto-selection whenever the invoice filter changes.
  useEffect(() => {
    setTabInitialized(false);
    setActiveTab("PENDING");
  }, [invoiceIdFilter]);

  // Auto-select the most urgent non-empty tab on first load (or after filter change).
  // Priority: NEEDS_REVIEW (no AI proposal — highest urgency) → PENDING → PENDING default.
  // Only runs once per filter context; subsequent tab clicks are user-controlled.
  useEffect(() => {
    if (!stats || tabInitialized) return;
    setTabInitialized(true);
    if (stats.needs_review > 0) {
      setActiveTab("NEEDS_REVIEW");
    } else if (stats.pending > 0) {
      setActiveTab("PENDING");
    }
  }, [stats, tabInitialized]);

  // Queue items for the active tab (optionally filtered to one invoice)
  const { data: items, isLoading } = useQuery<ClassificationQueueItem[]>({
    queryKey: ["classification-queue", activeTab, invoiceIdFilter],
    queryFn: () => listClassificationQueue(activeTab, invoiceIdFilter),
    refetchInterval: 30_000,
  });

  // Approve mutation — called directly from the inline form; no modal needed
  const approveMut = useMutation({
    mutationFn: ({
      itemId,
      code,
      component,
      notes,
    }: {
      itemId: string;
      code: string;
      component: string;
      notes: string;
    }) =>
      approveClassificationItem(itemId, {
        approved_code: code,
        approved_billing_component: component,
        review_notes: notes || null,
      }),
    onSuccess: (result) => {
      setApprovingItemId(null);
      qc.invalidateQueries({ queryKey: ["classification-queue"] });
      qc.invalidateQueries({ queryKey: ["classification-stats"] });
      const auditNote =
        result.bill_audit_result === "EXCEPTION"
          ? " Bill audit found exceptions — invoice may move to review."
          : "";
      toast.success(`Classified as '${result.approved_code}'.${auditNote}`);
    },
    onError: (err: Error) => {
      setApprovingItemId(null);
      toast.error("Could not approve item", err.message);
    },
  });

  // Reject mutation
  const rejectMut = useMutation({
    mutationFn: ({ itemId, notes }: { itemId: string; notes: string }) =>
      rejectClassificationItem(itemId, { review_notes: notes || null }),
    onSuccess: () => {
      setRejectingItem(null);
      qc.invalidateQueries({ queryKey: ["classification-queue"] });
      qc.invalidateQueries({ queryKey: ["classification-stats"] });
      toast.success("Line rejected and marked DENIED.");
    },
    onError: (err: Error) => {
      setRejectingItem(null);
      toast.error("Could not reject item", err.message);
    },
  });

  // Bulk approve mutation — accepts all items with ai_proposed_code in the current view
  const [showBulkConfirm, setShowBulkConfirm] = useState(false);
  const bulkApproveMut = useMutation({
    mutationFn: (ids: string[]) => bulkApproveClassificationItems(ids),
    onSuccess: (result) => {
      setShowBulkConfirm(false);
      qc.invalidateQueries({ queryKey: ["classification-queue"] });
      qc.invalidateQueries({ queryKey: ["classification-stats"] });
      const exceptionNote =
        result.bill_audit_exceptions > 0
          ? ` ${result.bill_audit_exceptions} triggered billing exceptions.`
          : "";
      const skippedNote =
        result.skipped > 0
          ? ` ${result.skipped} item${result.skipped !== 1 ? "s" : ""} skipped (no AI proposal).`
          : "";
      toast.success(
        `${result.approved} item${result.approved !== 1 ? "s" : ""} classified.${exceptionNote}${skippedNote}`,
      );
    },
    onError: (err: Error) => {
      setShowBulkConfirm(false);
      toast.error("Bulk approve failed", err.message);
    },
  });

  const isWriteRole = true; // CARRIER_ADMIN; router guards enforce this

  // Items that can be bulk-approved (have an AI proposal and are actionable)
  const bulkApprovableItems =
    items?.filter(
      (i) =>
        i.ai_proposed_code &&
        (i.status === "PENDING" || i.status === "NEEDS_REVIEW"),
    ) ?? [];

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Classification Queue</h1>
        <p className="mt-1 text-sm text-gray-500">
          Line items whose AI classification confidence was below the auto-proceed
          threshold. Review the AI proposal and confirm or override the taxonomy code.
          Approving creates a mapping rule so future similar lines auto-classify.
        </p>
      </div>

      {/* Invoice filter banner */}
      {invoiceIdFilter && (
        <div className="mb-4 flex items-center gap-3 rounded-lg border border-blue-100 bg-blue-50 px-4 py-2.5 text-sm">
          <span className="text-blue-500">🔍</span>
          <span className="text-blue-800">
            Filtered to invoice{" "}
            <strong className="font-semibold">
              {invoiceNumberFilter ?? invoiceIdFilter}
            </strong>
          </span>
          <Link
            href="/carrier/classification"
            className="ml-auto text-xs text-blue-600 hover:underline whitespace-nowrap"
          >
            Clear filter ×
          </Link>
        </div>
      )}

      {/* Stats header */}
      {stats && <StatsHeader stats={stats} />}

      {/* Tabs */}
      <div className="mb-4 flex gap-1 border-b border-gray-200">
        {(["PENDING", "NEEDS_REVIEW", "APPROVED", "REJECTED"] as Tab[]).map(
          (tab) => {
            const count =
              tab === "PENDING"
                ? stats?.pending
                : tab === "NEEDS_REVIEW"
                ? stats?.needs_review
                : undefined;
            return (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`flex items-center gap-1.5 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
                  activeTab === tab
                    ? "border-blue-600 text-blue-700"
                    : "border-transparent text-gray-500 hover:text-gray-700"
                }`}
              >
                {TAB_LABELS[tab]}
                {count !== undefined && count > 0 && (
                  <span
                    className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold ${
                      tab === "NEEDS_REVIEW"
                        ? "bg-red-100 text-red-700"
                        : "bg-amber-100 text-amber-700"
                    }`}
                  >
                    {count}
                  </span>
                )}
              </button>
            );
          },
        )}
      </div>

      {/* Approve All AI Proposals — shown when there are bulk-approvable items */}
      {isWriteRole && bulkApprovableItems.length > 0 && (
        <div className="mb-4 flex items-center justify-between rounded-lg border border-green-100 bg-green-50 px-4 py-2.5">
          <div className="text-sm text-green-800">
            <span className="font-semibold">{bulkApprovableItems.length}</span>{" "}
            item{bulkApprovableItems.length !== 1 ? "s" : ""} have AI proposals
            ready to accept
          </div>
          <button
            onClick={() => setShowBulkConfirm(true)}
            className="rounded-lg bg-green-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-green-700 transition-colors"
          >
            ✓ Approve All AI Proposals
          </button>
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
        </div>
      )}

      {/* Empty state */}
      {!isLoading && (!items || items.length === 0) && (
        <div className="rounded-xl border-2 border-dashed border-gray-200 py-20 text-center">
          <p className="text-4xl">
            {activeTab === "PENDING" || activeTab === "NEEDS_REVIEW" ? "🎉" : "📋"}
          </p>
          <p className="mt-3 font-medium text-gray-700">
            {activeTab === "PENDING"
              ? "No pending items"
              : activeTab === "NEEDS_REVIEW"
              ? "No items needing review"
              : activeTab === "APPROVED"
              ? "No approved items yet"
              : "No rejected items"}
          </p>
          <p className="mt-1 text-sm text-gray-400">
            {activeTab === "PENDING" || activeTab === "NEEDS_REVIEW"
              ? "All classification items have been resolved."
              : "Items will appear here once reviewed."}
          </p>
        </div>
      )}

      {/* Table */}
      {!isLoading && items && items.length > 0 && (
        <div className="overflow-hidden rounded-xl border bg-white shadow-sm">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Description
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Supplier
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Amount
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  AI Proposal
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Approved Code
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Queued
                </th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {items.map((item) => (
                <ClassificationRow
                  key={item.id}
                  item={item}
                  onApprove={(it, code, component, notes) => {
                    setApprovingItemId(it.id);
                    approveMut.mutate({ itemId: it.id, code, component, notes });
                  }}
                  onReject={setRejectingItem}
                  isWriteRole={isWriteRole}
                  isApproving={approvingItemId === item.id}
                />
              ))}
            </tbody>
          </table>
          <div className="border-t border-gray-100 bg-gray-50 px-4 py-2.5 text-xs text-gray-400">
            {items.length} item{items.length !== 1 ? "s" : ""} · Click a row to
            expand and classify
          </div>
        </div>
      )}

      {/* Reject modal */}
      {rejectingItem && (
        <RejectModal
          item={rejectingItem}
          isPending={rejectMut.isPending}
          onCancel={() => setRejectingItem(null)}
          onConfirm={(notes) =>
            rejectMut.mutate({ itemId: rejectingItem.id, notes })
          }
        />
      )}

      {/* Bulk approve confirmation modal */}
      {showBulkConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
            <h2 className="text-lg font-bold text-gray-900">
              Approve {bulkApprovableItems.length} AI Proposals?
            </h2>
            <p className="mt-2 text-sm text-gray-500">
              Each item will be classified using its AI-proposed taxonomy code, a{" "}
              <strong>CARRIER_CONFIRMED</strong> mapping rule will be created, and
              bill audit will run on each line. This cannot be undone.
            </p>
            {bulkApprovableItems.length < (items?.length ?? 0) && (
              <div className="mt-3 rounded-md border border-amber-100 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                ⚠ {(items?.length ?? 0) - bulkApprovableItems.length} item
                {(items?.length ?? 0) - bulkApprovableItems.length !== 1 ? "s" : ""} without
                an AI proposal will be skipped and must be classified manually.
              </div>
            )}
            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => setShowBulkConfirm(false)}
                disabled={bulkApproveMut.isPending}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() =>
                  bulkApproveMut.mutate(bulkApprovableItems.map((i) => i.id))
                }
                disabled={bulkApproveMut.isPending}
                className="rounded-lg bg-green-600 px-4 py-2 text-sm font-semibold text-white hover:bg-green-700 disabled:opacity-50 transition-colors"
              >
                {bulkApproveMut.isPending
                  ? "Approving…"
                  : `✓ Approve ${bulkApprovableItems.length}`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Page export — Suspense required for useSearchParams in Next.js 14 ─────────

export default function ClassificationQueuePage() {
  return (
    <Suspense fallback={
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
      </div>
    }>
      <ClassificationQueueContent />
    </Suspense>
  );
}
