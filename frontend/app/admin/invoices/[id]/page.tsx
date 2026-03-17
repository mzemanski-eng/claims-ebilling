"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getAdminInvoice,
  getAdminInvoiceLines,
  approveAdminInvoice,
  exportAdminInvoice,
  resolveAdminException,
  downloadBlob,
} from "@/lib/api";
import { StatusBadge } from "@/components/status-badge";
import { ConfidenceBadge } from "@/components/confidence-badge";
import { ValidationSummaryCard } from "@/components/validation-summary-card";
import { AiClassificationSuggestion } from "@/components/ai-classification-suggestion";
import { Button } from "@/components/ui/button";
import type { LineItemCarrierView } from "@/lib/types";
import { ResolutionActions } from "@/lib/types";
import { useToast } from "@/components/toast";

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
}: {
  exc: LineItemCarrierView["exceptions"][number];
  invoiceId: string;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  // Pre-select AI recommendation when present; fall back to rule-based default
  const [action, setAction] = useState<string>(
    () => exc.ai_recommendation ?? defaultResolutionAction(exc.required_action)
  );
  const [notes, setNotes] = useState("");

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
  const selectedOption = RESOLUTION_OPTIONS.find((o) => o.value === action);
  const aiOption = exc.ai_recommendation
    ? RESOLUTION_OPTIONS.find((o) => o.value === exc.ai_recommendation)
    : null;

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

        <input
          type="text"
          placeholder={isDenying ? "Reason for denial (required)" : "Notes (optional)"}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          className={`flex-1 min-w-32 rounded border px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500 ${
            isDenying && !notes.trim()
              ? "border-red-300 bg-red-50"
              : "border-gray-300 bg-white"
          }`}
        />

        <Button
          size="sm"
          variant={isDenying ? "danger" : "primary"}
          loading={resolveMut.isPending}
          disabled={isDenying && !notes.trim()}
          onClick={() => resolveMut.mutate()}
        >
          {isDenying ? "Deny" : "Resolve"}
        </Button>
      </div>

    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function AdminInvoiceDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const { id } = params;
  const router = useRouter();
  const qc = useQueryClient();

  const [expandedLines, setExpandedLines] = useState<Set<string>>(new Set());
  const [showApproveConfirm, setShowApproveConfirm] = useState(false);
  const [approvalNotes, setApprovalNotes] = useState("");
  const [exportError, setExportError] = useState<string | null>(null);
  const [triageExpanded, setTriageExpanded] = useState(false);

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
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.back()}
            className="text-sm text-gray-500 hover:text-gray-700"
          >
            ← Back
          </button>
          <h1 className="text-xl font-bold text-gray-900 font-mono">
            {invoice.invoice_number}
          </h1>
          <StatusBadge status={invoice.status} />
        </div>
        <div className="flex items-center gap-3">
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
          <p className="mt-1 text-sm text-gray-700">{invoice.invoice_date}</p>
        </div>
        <div>
          <p className="text-xs font-medium uppercase text-gray-400">
            Submitted
          </p>
          <p className="mt-1 text-sm text-gray-700">
            {invoice.submitted_at
              ? new Date(invoice.submitted_at).toLocaleDateString()
              : "—"}
          </p>
        </div>
      </div>

      {/* AI Triage panel */}
      {invoice.triage_risk_level && (
        <TriagePanel
          level={invoice.triage_risk_level}
          notes={invoice.triage_notes}
          expanded={triageExpanded}
          onToggle={() => setTriageExpanded((v) => !v)}
        />
      )}

      {/* Validation summary */}
      {invoice.validation_summary && (
        <div className="mb-6">
          <ValidationSummaryCard summary={invoice.validation_summary} />
        </div>
      )}

      {/* Line items */}
      <div className="rounded-xl border bg-white shadow-sm overflow-hidden">
        <div className="border-b px-6 py-4">
          <h2 className="font-semibold text-gray-900">Line Items</h2>
        </div>
        {loadingLines ? (
          <div className="flex justify-center py-10">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
          </div>
        ) : (
          <table className="min-w-full divide-y divide-gray-100 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500 w-10">
                  #
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">
                  Description
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">
                  Taxonomy
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">
                  Conf.
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold uppercase text-gray-500">
                  Billed
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold uppercase text-gray-500">
                  Expected
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">
                  Status
                </th>
                <th className="w-8" />
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
                        {line.claim_number && (
                          <p className="text-xs text-gray-400 mt-0.5">
                            Claim {line.claim_number}
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {line.taxonomy_code ? (
                          <div>
                            <p className="font-mono text-xs text-gray-700">
                              {line.taxonomy_code}
                            </p>
                            {line.taxonomy_label && (
                              <p className="text-xs text-gray-400 mt-0.5 truncate max-w-40">
                                {line.taxonomy_label}
                              </p>
                            )}
                          </div>
                        ) : (
                          <span className="text-gray-300">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {line.mapping_confidence ? (
                          <ConfidenceBadge confidence={line.mapping_confidence} />
                        ) : (
                          <span className="text-gray-300">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-gray-900">
                        ${Number(line.raw_amount).toFixed(2)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono">
                        {line.expected_amount ? (
                          <span
                            className={
                              Number(line.raw_amount) >
                              Number(line.expected_amount)
                                ? "text-red-600"
                                : "text-gray-700"
                            }
                          >
                            ${Number(line.expected_amount).toFixed(2)}
                          </span>
                        ) : (
                          <span className="text-gray-300">—</span>
                        )}
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
                        <td colSpan={8} className="bg-amber-50 px-8 py-4">
                          <div className="space-y-3">
                            {line.needs_review &&
                              line.exceptions.length === 0 && (
                                <div className="rounded bg-yellow-100 px-3 py-2 text-xs text-yellow-800">
                                  ⚠ Low mapping confidence — consider overriding
                                  via{" "}
                                  <a
                                    href="/admin/mappings"
                                    className="underline"
                                  >
                                    Mapping Queue
                                  </a>
                                  .
                                </div>
                              )}
                            {/* AI classification suggestion for UNRECOGNIZED lines */}
                            {!line.taxonomy_code &&
                              line.ai_classification_suggestion && (
                                <AiClassificationSuggestion
                                  suggestion={line.ai_classification_suggestion}
                                />
                              )}
                            {line.exceptions.map((exc) => (
                              <ExceptionRow
                                key={exc.exception_id}
                                exc={exc}
                                invoiceId={id}
                              />
                            ))}
                          </div>
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
