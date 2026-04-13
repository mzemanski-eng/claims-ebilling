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
  getSupplierProfile,
  listSupplierDocuments,
  uploadSupplierDocument,
  importSupplierTaxonomy,
  submitSupplierForReview,
  approveSupplier,
  rejectSupplier,
  suspendSupplier,
  reinstateSupplier,
} from "@/lib/api";
import type {
  AdminSupplier,
  SupplierAuditResult,
  SupplierDocument,
  TaxonomyImportResult,
  OnboardingStatusType,
} from "@/lib/types";
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

// ── Onboarding status badge ───────────────────────────────────────────────────

const ONBOARDING_STATUS_STYLES: Record<string, string> = {
  DRAFT:          "bg-gray-100 text-gray-600",
  PENDING_REVIEW: "bg-amber-100 text-amber-700",
  ACTIVE:         "bg-green-100 text-green-700",
  SUSPENDED:      "bg-red-100 text-red-700",
};

function OnboardingStatusBadge({ status }: { status: string }) {
  const style = ONBOARDING_STATUS_STYLES[status] ?? ONBOARDING_STATUS_STYLES.DRAFT;
  const label = status.replace(/_/g, " ");
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${style}`}>
      {label}
    </span>
  );
}

// ── Supplier Detail Panel (Profile / Documents / Taxonomy Import tabs) ─────────

function SupplierDetailPanel({
  supplier,
}: {
  supplier: AdminSupplier;
}) {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"profile" | "documents" | "import">("profile");
  const [importResult, setImportResult] = useState<TaxonomyImportResult | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [importLoading, setImportLoading] = useState(false);

  // Profile query
  const { data: profile, isLoading: profileLoading } = useQuery({
    queryKey: ["supplier-profile", supplier.id],
    queryFn: () => getSupplierProfile(supplier.id),
  });

  // Documents query — only fire when tab is active
  const { data: documents, isLoading: docsLoading } = useQuery({
    queryKey: ["supplier-documents", supplier.id],
    queryFn: () => listSupplierDocuments(supplier.id),
    enabled: activeTab === "documents",
  });

  // State machine mutations
  const submitMutation = useMutation({
    mutationFn: () => submitSupplierForReview(supplier.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-suppliers"] }),
  });
  const approveMutation = useMutation({
    mutationFn: () => approveSupplier(supplier.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-suppliers"] }),
  });
  const rejectMutation = useMutation({
    mutationFn: () => rejectSupplier(supplier.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-suppliers"] }),
  });
  const suspendMutation = useMutation({
    mutationFn: () => suspendSupplier(supplier.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-suppliers"] }),
  });
  const reinstateMutation = useMutation({
    mutationFn: () => reinstateSupplier(supplier.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-suppliers"] }),
  });

  // Document upload mutation
  const uploadMutation = useMutation({
    mutationFn: ({ docType, file }: { docType: "W9" | "COI" | "MSA" | "OTHER"; file: File }) =>
      uploadSupplierDocument(supplier.id, docType, file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["supplier-documents", supplier.id] }),
  });

  // Taxonomy import handler
  async function handleImport(file: File) {
    setImportError(null);
    setImportResult(null);
    setImportLoading(true);
    try {
      const result = await importSupplierTaxonomy(supplier.id, file);
      setImportResult(result);
    } catch (err: unknown) {
      setImportError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setImportLoading(false);
    }
  }

  const status = supplier.onboarding_status;

  return (
    <tr>
      <td colSpan={8} className="px-4 pb-4 pt-0">
        <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 space-y-4">

          {/* Tab bar + state machine actions */}
          <div className="flex flex-wrap items-center gap-2 border-b border-gray-200 pb-2">
            {(["profile", "documents", "import"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                  activeTab === tab
                    ? "bg-white text-blue-700 shadow-sm border border-gray-200"
                    : "text-gray-500 hover:text-gray-800"
                }`}
              >
                {tab === "profile" ? "Profile" : tab === "documents" ? "Documents" : "Taxonomy Import"}
              </button>
            ))}

            {/* State machine action buttons — conditional on current status */}
            <div className="ml-auto flex items-center gap-2">
              {status === "DRAFT" && (
                <Button
                  size="sm"
                  variant="secondary"
                  loading={submitMutation.isPending}
                  onClick={() => submitMutation.mutate()}
                >
                  Submit for Review
                </Button>
              )}
              {status === "PENDING_REVIEW" && (
                <>
                  <Button
                    size="sm"
                    loading={approveMutation.isPending}
                    onClick={() => approveMutation.mutate()}
                  >
                    Approve
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    loading={rejectMutation.isPending}
                    onClick={() => rejectMutation.mutate()}
                  >
                    Reject
                  </Button>
                </>
              )}
              {status === "ACTIVE" && (
                <Button
                  size="sm"
                  variant="danger"
                  loading={suspendMutation.isPending}
                  onClick={() => suspendMutation.mutate()}
                >
                  Suspend
                </Button>
              )}
              {status === "SUSPENDED" && (
                <Button
                  size="sm"
                  variant="secondary"
                  loading={reinstateMutation.isPending}
                  onClick={() => reinstateMutation.mutate()}
                >
                  Reinstate
                </Button>
              )}
            </div>
          </div>

          {/* Profile tab */}
          {activeTab === "profile" && (
            profileLoading ? (
              <p className="text-xs text-gray-400">Loading profile…</p>
            ) : profile ? (
              <div className="grid grid-cols-2 gap-x-10 gap-y-2 text-xs">
                {([
                  ["Contact Name",  profile.primary_contact_name],
                  ["Contact Email", profile.primary_contact_email],
                  ["Phone",         profile.primary_contact_phone],
                  ["Address",       [profile.address_line1, profile.address_line2, profile.city, profile.state_code, profile.zip_code].filter(Boolean).join(", ")],
                  ["Website",       profile.website],
                  ["Notes",         profile.notes],
                  ["Submitted",     profile.submitted_at ? new Date(profile.submitted_at).toLocaleDateString() : null],
                  ["Approved",      profile.approved_at  ? new Date(profile.approved_at).toLocaleDateString()  : null],
                ] as [string, string | null][]).map(([label, value]) => (
                  <div key={label} className="flex gap-2">
                    <span className="w-28 shrink-0 font-medium text-gray-500">{label}:</span>
                    <span className="text-gray-800 break-all">{value || "—"}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-gray-400">No profile data yet.</p>
            )
          )}

          {/* Documents tab */}
          {activeTab === "documents" && (
            <div className="space-y-3">
              {docsLoading ? (
                <p className="text-xs text-gray-400">Loading documents…</p>
              ) : documents && documents.length > 0 ? (
                <table className="min-w-full text-xs">
                  <thead>
                    <tr className="text-left text-gray-500 font-semibold">
                      <th className="pb-1 pr-4">Type</th>
                      <th className="pb-1 pr-4">Filename</th>
                      <th className="pb-1 pr-4">Uploaded</th>
                      <th className="pb-1">Expires</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {documents.map((d: SupplierDocument) => (
                      <tr key={d.id} className="text-gray-700">
                        <td className="py-1 pr-4 font-mono font-semibold">{d.document_type}</td>
                        <td className="py-1 pr-4">{d.filename}</td>
                        <td className="py-1 pr-4">{new Date(d.uploaded_at).toLocaleDateString()}</td>
                        <td className={`py-1 ${d.expires_at ? "text-amber-700" : "text-gray-400"}`}>
                          {d.expires_at ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="text-xs text-gray-400 italic">No documents uploaded yet.</p>
              )}

              {/* Upload form */}
              <div className="flex flex-wrap items-center gap-3 pt-2 border-t border-gray-200">
                <select
                  id={`doc-type-${supplier.id}`}
                  className="rounded border border-gray-300 px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                  defaultValue="W9"
                >
                  {["W9", "COI", "MSA", "OTHER"].map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
                <label className="cursor-pointer text-xs text-blue-600 hover:text-blue-800 font-medium">
                  {uploadMutation.isPending ? "Uploading…" : "Choose file to upload"}
                  <input
                    type="file"
                    accept=".pdf,.png,.jpg,.jpeg"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      const select = document.getElementById(`doc-type-${supplier.id}`) as HTMLSelectElement;
                      const docType = select?.value as "W9" | "COI" | "MSA" | "OTHER";
                      if (file && docType) uploadMutation.mutate({ docType, file });
                      e.target.value = "";
                    }}
                  />
                </label>
                {uploadMutation.isError && (
                  <span className="text-xs text-red-600">
                    Upload failed — {(uploadMutation.error as Error)?.message ?? "unknown error"}
                  </span>
                )}
                {uploadMutation.isSuccess && (
                  <span className="text-xs text-green-600">✓ Uploaded</span>
                )}
              </div>
            </div>
          )}

          {/* Taxonomy Import tab */}
          {activeTab === "import" && (
            <div className="space-y-3">
              <p className="text-xs text-gray-500">
                Upload a CSV with columns{" "}
                <code className="bg-gray-100 px-1 rounded font-mono">supplier_code,description</code>{" "}
                (max 200 rows). Claude will match each row to a platform taxonomy code and create mapping rules.
              </p>
              <label className="cursor-pointer text-xs text-blue-600 hover:text-blue-800 font-medium">
                {importLoading ? "Processing…" : "Choose CSV file"}
                <input
                  type="file"
                  accept=".csv"
                  className="hidden"
                  disabled={importLoading}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleImport(file);
                    e.target.value = "";
                  }}
                />
              </label>

              {importError && (
                <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                  {importError}
                </div>
              )}

              {importResult && (
                <div className="space-y-2">
                  {/* Summary counts */}
                  <div className="flex flex-wrap gap-4 text-xs font-medium">
                    <span className="text-gray-600">Processed: <strong>{importResult.processed}</strong></span>
                    <span className="text-green-700">Mapped: <strong>{importResult.mapped}</strong></span>
                    <span className="text-amber-700">Skipped: <strong>{importResult.skipped}</strong></span>
                    <span className="text-red-700">Unmapped: <strong>{importResult.unmapped}</strong></span>
                  </div>

                  {/* Per-row result table */}
                  <div className="max-h-48 overflow-y-auto rounded border border-gray-200 text-xs">
                    <table className="min-w-full">
                      <thead className="bg-gray-50 sticky top-0">
                        <tr>
                          <th className="px-2 py-1 text-left text-gray-500 font-semibold">#</th>
                          <th className="px-2 py-1 text-left text-gray-500 font-semibold">Supplier Code</th>
                          <th className="px-2 py-1 text-left text-gray-500 font-semibold">Matched To</th>
                          <th className="px-2 py-1 text-left text-gray-500 font-semibold">Confidence</th>
                          <th className="px-2 py-1 text-left text-gray-500 font-semibold">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {importResult.results.map((r) => (
                          <tr key={r.row} className={r.error && !r.skipped ? "bg-red-50" : ""}>
                            <td className="px-2 py-1 text-gray-400">{r.row}</td>
                            <td className="px-2 py-1 font-mono text-gray-700">{r.supplier_code}</td>
                            <td className="px-2 py-1 font-mono text-blue-700">
                              {r.matched_taxonomy_code ?? "—"}
                            </td>
                            <td className="px-2 py-1 text-gray-600">{r.confidence ?? "—"}</td>
                            <td className="px-2 py-1">
                              {r.skipped ? (
                                <span className="text-gray-400">Skipped (duplicate)</span>
                              ) : r.error ? (
                                <span className="text-red-600">{r.error}</span>
                              ) : (
                                <span className="text-green-600 font-medium">✓ Mapped</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </td>
    </tr>
  );
}

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
      <td colSpan={8} className="px-4 pb-4 pt-0">
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
            New suppliers start in <span className="font-medium text-gray-600">DRAFT</span> status.
            Use{" "}
            <span className="font-medium text-gray-600">Create Login</span>{" "}
            to give them portal access, then set up their contract, rate cards, and submit for review.
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
  const queryClient = useQueryClient();
  const { data: suppliers, isLoading } = useQuery({
    queryKey: ["admin-suppliers"],
    queryFn: listAdminSuppliers,
  });

  const [auditResults, setAuditResults] = useState<Record<string, SupplierAuditResult>>({});
  const [expandedAudit, setExpandedAudit] = useState<string | null>(null);
  const [expandedProfile, setExpandedProfile] = useState<string | null>(null);
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

  function toggleProfile(supplierId: string) {
    setExpandedProfile((prev) => (prev === supplierId ? null : supplierId));
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
            ← All Invoices
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
                <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wide text-gray-500">Onboarding</th>
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

                    {/* Onboarding status badge */}
                    <td className="px-4 py-3 text-center">
                      <OnboardingStatusBadge status={s.onboarding_status} />
                    </td>

                    {/* Active/Inactive status pill */}
                    <td className="px-4 py-3 text-center">
                      {s.is_active ? (
                        <span className="inline-flex rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">Active</span>
                      ) : (
                        <span className="inline-flex rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">Inactive</span>
                      )}
                    </td>

                    {/* Actions */}
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-2">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => toggleProfile(s.id)}
                          className="text-xs"
                        >
                          {expandedProfile === s.id ? "Hide" : "Profile"}
                        </Button>
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
                          href={`/admin/suppliers/${s.id}`}
                          className="text-sm font-medium text-gray-600 hover:text-gray-900"
                          title="View supplier scorecard"
                        >
                          Scorecard
                        </Link>
                        <Link
                          href={`/admin/invoices?supplier=${s.id}`}
                          className="text-sm font-medium text-blue-600 hover:text-blue-800"
                        >
                          Invoices →
                        </Link>
                      </div>
                    </td>
                  </tr>

                  {/* Profile detail panel */}
                  {expandedProfile === s.id && (
                    <SupplierDetailPanel
                      key={`${s.id}-profile`}
                      supplier={s}
                    />
                  )}

                  {/* AI Audit panel */}
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
