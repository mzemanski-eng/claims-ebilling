"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listCarrierUsers,
  createCarrierUser,
  updateUserScope,
  listAdminSuppliers,
} from "@/lib/api";
import type { CarrierUser, CarrierUserCreate, UserScopeUpdate, AdminSupplier } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

// ── Constants ──────────────────────────────────────────────────────────────────

const TAXONOMY_DOMAINS = [
  { code: "IA",   label: "Independent Adjusting" },
  { code: "ENG",  label: "Engineering & Forensic" },
  { code: "REC",  label: "Record Retrieval" },
  { code: "LA",   label: "Ladder Assist" },
  { code: "INSP", label: "Property Inspections" },
  { code: "VIRT", label: "Virtual Assist Inspections" },
  { code: "CR",   label: "Court Reporting" },
  { code: "INV",  label: "Investigation & Surveillance" },
  { code: "DRNE", label: "Drone & Aerial Inspection" },
  { code: "APPR", label: "Property Appraisal & Umpire" },
];

// ── Helpers ────────────────────────────────────────────────────────────────────

function roleBadge(role: string) {
  const isAdmin = role === "CARRIER_ADMIN";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
        isAdmin
          ? "bg-violet-100 text-violet-800"
          : "bg-blue-100 text-blue-800"
      }`}
    >
      {isAdmin ? "Admin" : "Auditor"}
    </span>
  );
}

function ScopePills({
  scope,
  allLabel,
  lookup,
}: {
  scope: string[] | null;
  allLabel: string;
  lookup?: Record<string, string>;
}) {
  if (!scope || scope.length === 0) {
    return <span className="text-xs text-gray-400 italic">{allLabel}</span>;
  }
  return (
    <div className="flex flex-wrap gap-1">
      {scope.map((v) => (
        <span
          key={v}
          className="inline-flex items-center rounded-md bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-700"
        >
          {lookup ? (lookup[v] ?? v) : v}
        </span>
      ))}
    </div>
  );
}

// ── Invite Modal ──────────────────────────────────────────────────────────────

function InviteModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"CARRIER_REVIEWER" | "CARRIER_ADMIN">("CARRIER_REVIEWER");
  const [error, setError] = useState<string | null>(null);

  const mut = useMutation({
    mutationFn: (payload: CarrierUserCreate) => createCarrierUser(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["carrier-users"] });
      onClose();
    },
    onError: (err: Error) => setError(err.message),
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    mut.mutate({ email: email.trim(), password, role });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-gray-900">Invite Team Member</h2>
        <p className="mt-1 text-sm text-gray-500">
          Create a login for a new auditor or admin. You can assign their scope after creation.
        </p>

        <form onSubmit={submit} className="mt-5 space-y-4">
          <Input
            label="Email address"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            placeholder="auditor@company.com"
          />
          <Input
            label="Temporary password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            placeholder="Min. 8 characters"
          />
          <div>
            <label className="mb-1.5 block text-sm font-medium text-gray-700">
              Role
            </label>
            <div className="grid grid-cols-2 gap-3">
              {[
                { value: "CARRIER_REVIEWER", title: "Auditor", desc: "Reviews & approves invoices within assigned scope" },
                { value: "CARRIER_ADMIN", title: "Admin", desc: "Full access — configure contracts, mappings, team" },
              ].map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setRole(opt.value as typeof role)}
                  className={`rounded-xl border-2 p-3 text-left transition-colors ${
                    role === opt.value
                      ? "border-indigo-600 bg-indigo-50"
                      : "border-gray-200 hover:border-gray-300"
                  }`}
                >
                  <p className="text-sm font-semibold text-gray-900">{opt.title}</p>
                  <p className="mt-0.5 text-xs text-gray-500">{opt.desc}</p>
                </button>
              ))}
            </div>
          </div>

          {error && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={mut.isPending}>
              Create account
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Edit Scope Modal ──────────────────────────────────────────────────────────

function EditScopeModal({
  user,
  suppliers,
  onClose,
}: {
  user: CarrierUser;
  suppliers: AdminSupplier[];
  onClose: () => void;
}) {
  const qc = useQueryClient();

  // Initialize from current scope; null / empty = "all"
  const [selectedDomains, setSelectedDomains] = useState<Set<string>>(
    new Set(user.category_scope ?? []),
  );
  const [selectedSuppliers, setSelectedSuppliers] = useState<Set<string>>(
    new Set(user.supplier_scope ?? []),
  );
  const [error, setError] = useState<string | null>(null);

  function toggleDomain(code: string) {
    setSelectedDomains((prev) => {
      const next = new Set(prev);
      next.has(code) ? next.delete(code) : next.add(code);
      return next;
    });
  }

  function toggleSupplier(id: string) {
    setSelectedSuppliers((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  const mut = useMutation({
    mutationFn: (payload: UserScopeUpdate) => updateUserScope(user.id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["carrier-users"] });
      onClose();
    },
    onError: (err: Error) => setError(err.message),
  });

  function save() {
    setError(null);
    mut.mutate({
      category_scope: selectedDomains.size > 0 ? [...selectedDomains] : null,
      supplier_scope: selectedSuppliers.size > 0 ? [...selectedSuppliers] : null,
    });
  }

  const allDomains = selectedDomains.size === 0;
  const allSuppliers = selectedSuppliers.size === 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl">
        <div className="mb-5">
          <h2 className="text-lg font-semibold text-gray-900">Edit Scope</h2>
          <p className="mt-0.5 text-sm text-gray-500">
            <span className="font-medium text-gray-700">{user.email}</span> ·{" "}
            {user.role === "CARRIER_ADMIN" ? "Admin" : "Auditor"}
          </p>
        </div>

        {user.role === "CARRIER_ADMIN" ? (
          <div className="rounded-xl bg-violet-50 px-4 py-3 text-sm text-violet-800">
            Admins always have full access and cannot be scoped to specific domains or suppliers.
          </div>
        ) : (
          <div className="space-y-6">
            {/* Domain Responsibility */}
            <div>
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-gray-800">
                  Domain Responsibility
                </h3>
                {!allDomains && (
                  <button
                    onClick={() => setSelectedDomains(new Set())}
                    className="text-xs text-gray-400 underline hover:text-gray-600"
                  >
                    Clear (assign all)
                  </button>
                )}
              </div>
              <p className="mb-3 text-xs text-gray-500">
                {allDomains
                  ? "This auditor sees exceptions across all service domains."
                  : "This auditor only sees exceptions in the selected domains."}
              </p>
              <div className="grid grid-cols-2 gap-2">
                {TAXONOMY_DOMAINS.map((d) => {
                  const checked = selectedDomains.has(d.code);
                  return (
                    <label
                      key={d.code}
                      className={`flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2.5 transition-colors ${
                        checked
                          ? "border-indigo-300 bg-indigo-50"
                          : "border-gray-200 hover:border-gray-300"
                      }`}
                    >
                      <input
                        type="checkbox"
                        className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                        checked={checked}
                        onChange={() => toggleDomain(d.code)}
                      />
                      <div>
                        <p className="text-sm font-medium text-gray-900">{d.code}</p>
                        <p className="text-xs text-gray-500">{d.label}</p>
                      </div>
                    </label>
                  );
                })}
              </div>
            </div>

            {/* Supplier Assignment */}
            <div>
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-gray-800">
                  Supplier Assignment
                </h3>
                {!allSuppliers && (
                  <button
                    onClick={() => setSelectedSuppliers(new Set())}
                    className="text-xs text-gray-400 underline hover:text-gray-600"
                  >
                    Clear (assign all)
                  </button>
                )}
              </div>
              <p className="mb-3 text-xs text-gray-500">
                {allSuppliers
                  ? "This auditor sees billing from all suppliers."
                  : "This auditor only sees billing from the selected suppliers."}
              </p>
              {suppliers.length === 0 ? (
                <p className="text-xs text-gray-400 italic">No suppliers configured yet.</p>
              ) : (
                <div className="max-h-48 space-y-1.5 overflow-y-auto">
                  {suppliers.map((s) => {
                    const checked = selectedSuppliers.has(s.id);
                    return (
                      <label
                        key={s.id}
                        className={`flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 transition-colors ${
                          checked
                            ? "border-indigo-300 bg-indigo-50"
                            : "border-gray-200 hover:border-gray-300"
                        }`}
                      >
                        <input
                          type="checkbox"
                          className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                          checked={checked}
                          onChange={() => toggleSupplier(s.id)}
                        />
                        <span className="text-sm font-medium text-gray-900">{s.name}</span>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}

        {error && (
          <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
        )}

        <div className="mt-6 flex justify-end gap-3">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          {user.role !== "CARRIER_ADMIN" && (
            <Button onClick={save} loading={mut.isPending}>
              Save scope
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AdminTeamPage() {
  const [showInvite, setShowInvite] = useState(false);
  const [scopeTarget, setScopeTarget] = useState<CarrierUser | null>(null);

  const { data: users, isLoading } = useQuery({
    queryKey: ["carrier-users"],
    queryFn: listCarrierUsers,
  });

  const { data: suppliers } = useQuery({
    queryKey: ["admin-suppliers"],
    queryFn: listAdminSuppliers,
    staleTime: 5 * 60 * 1000,
  });

  // Build a lookup map: supplier_id → name for display in scope pills
  const supplierNames: Record<string, string> = Object.fromEntries(
    (suppliers ?? []).map((s) => [s.id, s.name]),
  );

  return (
    <div className="space-y-6">
      {showInvite && <InviteModal onClose={() => setShowInvite(false)} />}
      {scopeTarget && (
        <EditScopeModal
          user={scopeTarget}
          suppliers={suppliers ?? []}
          onClose={() => setScopeTarget(null)}
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Team</h1>
          <p className="mt-1 text-sm text-gray-500">
            Manage carrier admin and auditor accounts. Assign each auditor a domain
            and/or supplier scope to focus their review queue.
          </p>
        </div>
        <Button onClick={() => setShowInvite(true)}>+ Invite</Button>
      </div>

      {/* How scope works — info banner */}
      <div className="rounded-xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-800">
        <strong>How scope works:</strong> Auditors with no scope assigned see all
        exceptions across all domains and suppliers. Narrowing their scope pre-filters the
        Mappings queue so each auditor only sees what they own. The AI handles
        high-confidence items automatically — scope only affects the manual review queue.
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
          </div>
        ) : !users || users.length === 0 ? (
          <div className="py-16 text-center">
            <p className="text-sm text-gray-400">No team members yet.</p>
            <button
              onClick={() => setShowInvite(true)}
              className="mt-2 text-sm font-medium text-indigo-600 hover:text-indigo-800"
            >
              Invite the first auditor →
            </button>
          </div>
        ) : (
          <table className="min-w-full divide-y divide-gray-100">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Email
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Role
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Domain Scope
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Supplier Scope
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Status
                </th>
                <th className="w-28 px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {users.map((u) => (
                <tr key={u.id} className="transition-colors hover:bg-gray-50">
                  <td className="px-4 py-3 text-sm font-medium text-gray-900">
                    {u.email}
                  </td>
                  <td className="px-4 py-3">{roleBadge(u.role)}</td>
                  <td className="px-4 py-3">
                    {u.role === "CARRIER_ADMIN" ? (
                      <span className="text-xs text-gray-400 italic">Full access</span>
                    ) : (
                      <ScopePills
                        scope={u.category_scope}
                        allLabel="All domains"
                      />
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {u.role === "CARRIER_ADMIN" ? (
                      <span className="text-xs text-gray-400 italic">Full access</span>
                    ) : (
                      <ScopePills
                        scope={u.supplier_scope}
                        allLabel="All suppliers"
                        lookup={supplierNames}
                      />
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                        u.is_active
                          ? "bg-green-100 text-green-700"
                          : "bg-gray-100 text-gray-500"
                      }`}
                    >
                      {u.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setScopeTarget(u)}
                    >
                      Edit scope
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
