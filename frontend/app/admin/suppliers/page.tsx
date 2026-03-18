"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listAdminSuppliers,
  runSupplierAudit,
  createAdminSupplier,
} from "@/lib/api";
import type { SupplierAuditResult } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

// ── Risk rating colours (mirrors triage colours) ──────────────────────────────
const RISK_COLORS: Record<string, { border: string; bg: string; badge: string; text: string }> = {
  LOW:      { border: "border-green-200", bg: "bg-green-50", badge: "bg-green-100 text-green-800",   text: "text-green-700"  },
  MEDIUM:   { border: "border-amber-200", bg: "bg-amber-50", badge: "bg-amber-100 text-amber-800",   text: "text-amber-700"  },
  HIGH:     { border: "border-red-200",   bg: "bg-red-50",   badge: "bg-red-100 text-red-800",       text: "text-red-700"    },
  CRITICAL: { border: "border-red-300",   bg: "bg-red-50",   badge: "bg-red-600 text-white",         text: "text-red-800"    },
};

const FINDING_SEVERITY_COLORS: Record<string, string> = {
  ERROR:   "text-red-700 bg-red-50 border-red-100",
  WARNING: "text-amber-700 bg-amber-50 border-amber-100",
  INFO:    "text-blue-700 bg-blue-50 border-blue-100",
};

function AuditResultPanel({
  supplierId,
  supplierName,
  result,
}: {
  supplierId: string;
  supplierName: string;
  result: SupplierAuditResult;
}) {
  const c = RISK_COLORS[result.risk_rating] ?? RISK_COLORS.MEDIUM;

  return (
    <tr>
      <td colSpan={6} className="px-4 pb-4 pt-0">
        <div className={`rounded-xl border ${c.border} ${c.bg} p-4 space-y-4`}>
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="text-sm font-semibold text-gray-800">
                ✦ AI Supplier Audit — {supplierName}
              </span>
              <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${c.badge}`}>
                {result.risk_rating} RISK
              </span>
            </div>
            <Link
              href={`/admin/invoices?supplier=${supplierId}`}
              className="text-xs text-blue-600 hover:text-blue-800 font-medium"
            >
              View invoices →
            </Link>
          </div>

          {/* Findings */}
          {result.findings.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
                Findings
              </p>
              <div className="space-y-2">
                {result.findings.map((f, i) => (
                  <div
                    key={i}
                    className={`rounded-lg border px-3 py-2.5 text-xs ${FINDING_SEVERITY_COLORS[f.severity] ?? FINDING_SEVERITY_COLORS.INFO}`}
                  >
                    <p className="font-semibold">{f.title}</p>
                    <p className="mt-0.5 leading-relaxed opacity-90">{f.detail}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Recommendations */}
          {result.recommendations.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
                Recommendations
              </p>
              <ul className="space-y-1.5">
                {result.recommendations.map((rec, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-gray-700">
                    <span className="mt-0.5 shrink-0 text-gray-400">→</span>
                    <span>{rec}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </td>
    </tr>
  );
}

// ── New Supplier Modal ────────────────────────────────────────────────────────

function NewSupplierModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [taxId, setTaxId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      createAdminSupplier({ name: name.trim(), tax_id: taxId.trim() || undefined }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-suppliers"] });
      onClose();
    },
    onError: (err: Error) => setError(err.message),
  });

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-full max-w-md rounded-xl border bg-white shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b px-6 py-4">
          <h2 className="text-base font-semibold text-gray-900">New Supplier</h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            mutation.mutate();
          }}
          className="space-y-4 px-6 py-5"
        >
          {error && (
            <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <Input
            id="supplier-name"
            label="Supplier Name"
            placeholder="Acme Engineering Inc."
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
          />

          <Input
            id="supplier-tax-id"
            label="Tax ID (optional)"
            placeholder="XX-0000000"
            value={taxId}
            onChange={(e) => setTaxId(e.target.value)}
          />

          <p className="text-xs text-gray-400">
            After creating the supplier, go to{" "}
            <Link href="/admin/contracts/new" className="text-blue-600 hover:underline">
              Contracts → New Contract
            </Link>{" "}
            to add a rate card and enable invoice processing.
          </p>

          <div className="flex justify-end gap-3 pt-1">
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button
              type="submit"
              loading={mutation.isPending}
              disabled={!name.trim() || mutation.isPending}
            >
              Create Supplier
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AdminSuppliersPage() {
  const { data: suppliers, isLoading } = useQuery({
    queryKey: ["admin-suppliers"],
    queryFn: listAdminSuppliers,
  });

  // Track audit results keyed by supplier ID, and which are expanded
  const [auditResults, setAuditResults] = useState<Record<string, SupplierAuditResult>>({});
  const [expandedAudit, setExpandedAudit] = useState<string | null>(null);
  const [loadingAuditId, setLoadingAuditId] = useState<string | null>(null);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [showNewSupplier, setShowNewSupplier] = useState(false);

  const auditMutation = useMutation({
    mutationFn: (supplierId: string) => runSupplierAudit(supplierId),
    onMutate: (supplierId) => {
      setLoadingAuditId(supplierId);
      setAuditError(null);
    },
    onSuccess: (data, supplierId) => {
      setAuditResults((prev) => ({ ...prev, [supplierId]: data }));
      setExpandedAudit(supplierId);
      setLoadingAuditId(null);
    },
    onError: (err: Error) => {
      setAuditError(`Audit failed for supplier: ${err.message}`);
      setLoadingAuditId(null);
    },
  });

  function handleRunAudit(supplierId: string) {
    // If we already have results, toggle the panel instead of re-fetching
    if (auditResults[supplierId]) {
      setExpandedAudit((prev) => (prev === supplierId ? null : supplierId));
    } else {
      auditMutation.mutate(supplierId);
    }
  }

  return (
    <div className="space-y-6">
      {showNewSupplier && (
        <NewSupplierModal onClose={() => setShowNewSupplier(false)} />
      )}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Suppliers</h1>
          <p className="mt-1 text-sm text-gray-500">
            {suppliers?.length ?? 0} supplier{suppliers?.length !== 1 ? "s" : ""} on record
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button onClick={() => setShowNewSupplier(true)}>
            + New Supplier
          </Button>
          <Link
            href="/admin/invoices"
            className="text-sm font-medium text-blue-600 hover:text-blue-800"
          >
            ← Invoice Queue
          </Link>
        </div>
      </div>

      {auditError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {auditError}
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
          </div>
        ) : suppliers?.length === 0 ? (
          <div className="py-16 text-center">
            <p className="text-sm text-gray-400">No suppliers found.</p>
            <Button
              variant="secondary"
              className="mt-4"
              onClick={() => setShowNewSupplier(true)}
            >
              + Add your first supplier
            </Button>
          </div>
        ) : (
          <table className="min-w-full divide-y divide-gray-100">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Supplier Name
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Tax ID
                </th>
                <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Contracts
                </th>
                <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Invoices
                </th>
                <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Active
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {suppliers?.map((s) => (
                <>
                  <tr key={s.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3 font-medium text-gray-900">
                      <div className="flex items-center gap-2">
                        {s.name}
                        {auditResults[s.id] && (
                          <span
                            className={`rounded-full px-1.5 py-0.5 text-xs font-bold ${
                              (RISK_COLORS[auditResults[s.id].risk_rating] ?? RISK_COLORS.MEDIUM).badge
                            }`}
                            title={`Last AI audit: ${auditResults[s.id].risk_rating} risk`}
                          >
                            {auditResults[s.id].risk_rating}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 font-mono text-sm text-gray-500">
                      {s.tax_id ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-center text-sm text-gray-700">
                      {s.contract_count > 0 ? (
                        <Link
                          href={`/admin/contracts?supplier_id=${s.id}`}
                          className="font-medium text-blue-600 hover:text-blue-800"
                        >
                          {s.contract_count}
                        </Link>
                      ) : (
                        <Link
                          href={`/admin/contracts/new?supplier_id=${s.id}`}
                          className="text-amber-600 hover:text-amber-800 text-xs font-medium"
                          title="No contract — click to add one"
                        >
                          + Add
                        </Link>
                      )}
                    </td>
                    <td className="px-4 py-3 text-center text-sm text-gray-700">
                      {s.invoice_count}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {s.is_active ? (
                        <span className="inline-flex rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                          Active
                        </span>
                      ) : (
                        <span className="inline-flex rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">
                          Inactive
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-3">
                        <Button
                          size="sm"
                          variant="ghost"
                          loading={loadingAuditId === s.id}
                          onClick={() => handleRunAudit(s.id)}
                          className="text-xs"
                        >
                          {auditResults[s.id]
                            ? expandedAudit === s.id
                              ? "Hide audit"
                              : "Show audit"
                            : "Run Audit"}
                        </Button>
                        <Link
                          href={`/admin/invoices?supplier=${s.id}`}
                          className="text-sm font-medium text-blue-600 hover:text-blue-800"
                        >
                          View invoices →
                        </Link>
                      </div>
                    </td>
                  </tr>

                  {/* Expanded audit results row */}
                  {expandedAudit === s.id && auditResults[s.id] && (
                    <AuditResultPanel
                      key={`${s.id}-audit`}
                      supplierId={s.id}
                      supplierName={s.name}
                      result={auditResults[s.id]}
                    />
                  )}
                </>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
