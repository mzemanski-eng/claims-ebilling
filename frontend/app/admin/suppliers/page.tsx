"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  createAdminSupplier,
  createSupplierUser,
  listAdminSuppliers,
  listSupplierUsers,
  runSupplierAudit,
} from "@/lib/api";
import type { AdminSupplier, SupplierAuditResult } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

// ── Risk rating colours ───────────────────────────────────────────────────────
const RISK_COLORS: Record<string, { border: string; bg: string; badge: string }> = {
  LOW:      { border: "border-green-200", bg: "bg-green-50",  badge: "bg-green-100 text-green-800"  },
  MEDIUM:   { border: "border-amber-200", bg: "bg-amber-50",  badge: "bg-amber-100 text-amber-800"  },
  HIGH:     { border: "border-red-200",   bg: "bg-red-50",    badge: "bg-red-100 text-red-800"      },
  CRITICAL: { border: "border-red-300",   bg: "bg-red-50",    badge: "bg-red-600 text-white"        },
};

const FINDING_SEVERITY_COLORS: Record<string, string> = {
  ERROR:   "text-red-700 bg-red-50 border-red-100",
  WARNING: "text-amber-700 bg-amber-50 border-amber-100",
  INFO:    "text-blue-700 bg-blue-50 border-blue-100",
};

// ── AI Audit panel ────────────────────────────────────────────────────────────

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
      <td colSpan={7} className="px-4 pb-4 pt-0">
        <div className={`rounded-xl border ${c.border} ${c.bg} p-4 space-y-4`}>
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
          {result.findings.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">Findings</p>
              <div className="space-y-2">
                {result.findings.map((f, i) => (
                  <div key={i} className={`rounded-lg border px-3 py-2.5 text-xs ${FINDING_SEVERITY_COLORS[f.severity] ?? FINDING_SEVERITY_COLORS.INFO}`}>
                    <p className="font-semibold">{f.title}</p>
                    <p className="mt-0.5 leading-relaxed opacity-90">{f.detail}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
          {result.recommendations.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">Recommendations</p>
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

// ── New Supplier modal ────────────────────────────────────────────────────────

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
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-full max-w-md rounded-xl border bg-white shadow-xl">
        <div className="flex items-center justify-between border-b px-6 py-4">
          <h2 className="text-base font-semibold text-gray-900">New Supplier</h2>
          <button onClick={onClose} className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600">✕</button>
        </div>
        <form
          onSubmit={(e) => { e.preventDefault(); setError(null); mutation.mutate(); }}
          className="space-y-4 px-6 py-5"
        >
          {error && (
            <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
          )}
          <Input id="supplier-name" label="Supplier Name" placeholder="Acme Engineering Inc." required value={name} onChange={(e) => setName(e.target.value)} />
          <Input id="supplier-tax-id" label="Tax ID (optional)" placeholder="XX-0000000" value={taxId} onChange={(e) => setTaxId(e.target.value)} />
          <p className="text-xs text-gray-400">
            After creating the supplier, use{" "}
            <span className="font-medium text-gray-600">Create Login</span>{" "}
            to give them portal access, then set up their contract and rate cards.
          </p>
          <div className="flex justify-end gap-3 pt-1">
            <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={mutation.isPending} disabled={!name.trim() || mutation.isPending}>
              Create Supplier
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Create Login modal ────────────────────────────────────────────────────────

function CreateLoginModal({
  supplier,
  onClose,
}: {
  supplier: AdminSupplier;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Fetch existing logins for this supplier
  const { data: existingUsers, isLoading: loadingUsers } = useQuery({
    queryKey: ["supplier-users", supplier.id],
    queryFn: () => listSupplierUsers(supplier.id),
  });

  const mutation = useMutation({
    mutationFn: () => createSupplierUser(supplier.id, { email: email.trim().toLowerCase(), password }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["supplier-users", supplier.id] });
      queryClient.invalidateQueries({ queryKey: ["admin-suppliers"] });
      setSuccess(`Login created for ${data.email}`);
      setEmail("");
      setPassword("");
      setConfirm("");
      setError(null);
    },
    onError: (err: Error) => setError(err.message),
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    mutation.mutate();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-full max-w-md rounded-xl border bg-white shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b px-6 py-4">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Supplier Login</h2>
            <p className="text-xs text-gray-500 mt-0.5">{supplier.name}</p>
          </div>
          <button onClick={onClose} className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600">✕</button>
        </div>

        <div className="px-6 py-5 space-y-5">
          {/* Existing logins */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
              Current Logins
            </p>
            {loadingUsers ? (
              <p className="text-xs text-gray-400">Loading…</p>
            ) : existingUsers && existingUsers.length > 0 ? (
              <ul className="space-y-1.5">
                {existingUsers.map((u) => (
                  <li key={u.id} className="flex items-center gap-2 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2">
                    <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${u.is_active ? "bg-green-500" : "bg-gray-300"}`} />
                    <span className="text-sm text-gray-700 font-mono">{u.email}</span>
                    {!u.is_active && (
                      <span className="ml-auto text-xs text-gray-400">Inactive</span>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-gray-400 italic">No logins yet — create one below.</p>
            )}
          </div>

          <div className="border-t" />

          {/* Create new login form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
              Create New Login
            </p>

            {error && (
              <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
            )}
            {success && (
              <div className="rounded-md border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
                ✓ {success}
              </div>
            )}

            <Input
              id="login-email"
              label="Email address"
              type="email"
              placeholder="billing@supplier.com"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <Input
              id="login-password"
              label="Password"
              type="password"
              placeholder="Min. 8 characters"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <Input
              id="login-confirm"
              label="Confirm password"
              type="password"
              placeholder="Re-enter password"
              required
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />

            <div className="flex justify-end gap-3 pt-1">
              <Button type="button" variant="ghost" onClick={onClose}>Done</Button>
              <Button
                type="submit"
                loading={mutation.isPending}
                disabled={!email.trim() || !password || !confirm || mutation.isPending}
              >
                Create Login
              </Button>
            </div>
          </form>
        </div>
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

  const [auditResults, setAuditResults] = useState<Record<string, SupplierAuditResult>>({});
  const [expandedAudit, setExpandedAudit] = useState<string | null>(null);
  const [loadingAuditId, setLoadingAuditId] = useState<string | null>(null);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [showNewSupplier, setShowNewSupplier] = useState(false);
  const [loginTarget, setLoginTarget] = useState<AdminSupplier | null>(null);

  const auditMutation = useMutation({
    mutationFn: (supplierId: string) => runSupplierAudit(supplierId),
    onMutate: (supplierId) => { setLoadingAuditId(supplierId); setAuditError(null); },
    onSuccess: (data, supplierId) => {
      setAuditResults((prev) => ({ ...prev, [supplierId]: data }));
      setExpandedAudit(supplierId);
      setLoadingAuditId(null);
    },
    onError: (err: Error) => {
      setAuditError(`Audit failed: ${err.message}`);
      setLoadingAuditId(null);
    },
  });

  function handleRunAudit(supplierId: string) {
    if (auditResults[supplierId]) {
      setExpandedAudit((prev) => (prev === supplierId ? null : supplierId));
    } else {
      auditMutation.mutate(supplierId);
    }
  }

  return (
    <div className="space-y-6">
      {showNewSupplier && <NewSupplierModal onClose={() => setShowNewSupplier(false)} />}
      {loginTarget && <CreateLoginModal supplier={loginTarget} onClose={() => setLoginTarget(null)} />}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Suppliers</h1>
          <p className="mt-1 text-sm text-gray-500">
            {suppliers?.length ?? 0} supplier{suppliers?.length !== 1 ? "s" : ""} on record
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button onClick={() => setShowNewSupplier(true)}>+ New Supplier</Button>
          <Link href="/admin/invoices" className="text-sm font-medium text-blue-600 hover:text-blue-800">
            ← Invoice Queue
          </Link>
        </div>
      </div>

      {auditError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{auditError}</div>
      )}

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
          </div>
        ) : suppliers?.length === 0 ? (
          <div className="py-16 text-center">
            <p className="text-sm text-gray-400">No suppliers found.</p>
            <Button variant="secondary" className="mt-4" onClick={() => setShowNewSupplier(true)}>
              + Add your first supplier
            </Button>
          </div>
        ) : (
          <table className="min-w-full divide-y divide-gray-100">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">Supplier</th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">Tax ID</th>
                <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wide text-gray-500">Logins</th>
                <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wide text-gray-500">Contracts</th>
                <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wide text-gray-500">Invoices</th>
                <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wide text-gray-500">Status</th>
                <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-gray-500">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {suppliers?.map((s) => (
                <>
                  <tr key={s.id} className="hover:bg-gray-50 transition-colors">
                    {/* Supplier name + audit badge */}
                    <td className="px-4 py-3 font-medium text-gray-900">
                      <div className="flex items-center gap-2">
                        {s.name}
                        {auditResults[s.id] && (
                          <span
                            className={`rounded-full px-1.5 py-0.5 text-xs font-bold ${(RISK_COLORS[auditResults[s.id].risk_rating] ?? RISK_COLORS.MEDIUM).badge}`}
                            title={`AI audit: ${auditResults[s.id].risk_rating} risk`}
                          >
                            {auditResults[s.id].risk_rating}
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Tax ID */}
                    <td className="px-4 py-3 font-mono text-sm text-gray-500">{s.tax_id ?? "—"}</td>

                    {/* Logins column */}
                    <td className="px-4 py-3 text-center">
                      {s.user_count > 0 ? (
                        <button
                          onClick={() => setLoginTarget(s)}
                          className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-700 hover:bg-green-200 transition-colors"
                          title="Manage logins"
                        >
                          <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
                          {s.user_count} login{s.user_count !== 1 ? "s" : ""}
                        </button>
                      ) : (
                        <button
                          onClick={() => setLoginTarget(s)}
                          className="inline-flex items-center gap-1 rounded-full bg-amber-50 border border-amber-200 px-2.5 py-0.5 text-xs font-medium text-amber-700 hover:bg-amber-100 transition-colors"
                          title="No logins — click to create one"
                        >
                          No login
                        </button>
                      )}
                    </td>

                    {/* Contracts */}
                    <td className="px-4 py-3 text-center text-sm">
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

                    {/* Invoices */}
                    <td className="px-4 py-3 text-center text-sm text-gray-700">{s.invoice_count}</td>

                    {/* Status */}
                    <td className="px-4 py-3 text-center">
                      {s.is_active ? (
                        <span className="inline-flex rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">Active</span>
                      ) : (
                        <span className="inline-flex rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">Inactive</span>
                      )}
                    </td>

                    {/* Actions */}
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
                            ? expandedAudit === s.id ? "Hide audit" : "Show audit"
                            : "Run Audit"}
                        </Button>
                        <Link
                          href={`/admin/invoices?supplier=${s.id}`}
                          className="text-sm font-medium text-blue-600 hover:text-blue-800"
                        >
                          Invoices →
                        </Link>
                      </div>
                    </td>
                  </tr>

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
