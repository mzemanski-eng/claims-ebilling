"use client";

import React, { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createGuideline,
  createRateCard,
  deleteGuideline,
  deleteRateCard,
  getAdminContract,
  updateGuideline,
} from "@/lib/api";
import type { GuidelineCreate, RateCardCreate, RateTier } from "@/lib/types";
import { DOMAIN_LABELS, TAXONOMY_DOMAINS, TAXONOMY_OPTIONS } from "@/lib/taxonomy";

const RULE_TYPES = [
  { value: "max_units", label: "Max Units" },
  { value: "cap_amount", label: "Cap Amount" },
  { value: "billing_increment", label: "Billing Increment" },
  { value: "bundling_prohibition", label: "Bundling Prohibition" },
  { value: "requires_auth", label: "Requires Authorization" },
  { value: "max_pct_of_invoice", label: "Max % of Invoice" },
  { value: "invoice_codes_exclusive", label: "Service Hierarchy (Exclusive Codes)" },
];

// ── Blank form state ──────────────────────────────────────────────────────────

function blankRateCard(effectiveFrom = ""): RateCardCreate {
  return {
    taxonomy_code: "",
    rate_type: "flat",
    contracted_rate: "",
    rate_tiers: [],
    max_units: null,
    is_all_inclusive: false,
    effective_from: effectiveFrom,
    effective_to: null,
  };
}

// ── Rate type display helpers ─────────────────────────────────────────────────

const RATE_TYPE_LABELS: Record<string, string> = {
  flat:     "Flat",
  tiered:   "Tiered",
  hourly:   "Hourly",
  mileage:  "Per Mile",
  per_diem: "Per Diem",
};

const RATE_TYPE_COLORS: Record<string, string> = {
  flat:     "bg-gray-100 text-gray-600",
  tiered:   "bg-purple-100 text-purple-700",
  hourly:   "bg-blue-100 text-blue-700",
  mileage:  "bg-green-100 text-green-700",
  per_diem: "bg-amber-100 text-amber-700",
};

function blankGuideline(): GuidelineCreate {
  return {
    taxonomy_code: null,
    domain: null,
    rule_type: "max_units",
    rule_params: {},
    severity: "ERROR",
    narrative_source: null,
  };
}

// ── Dynamic rule-params fields ────────────────────────────────────────────────

function RuleParamsFields({
  ruleType,
  params,
  onChange,
}: {
  ruleType: string;
  params: Record<string, unknown>;
  onChange: (p: Record<string, unknown>) => void;
}) {
  switch (ruleType) {
    case "max_units":
      return (
        <div className="flex gap-2">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-500">Max</label>
            <input
              type="number"
              min="0"
              value={(params.max as string) ?? ""}
              onChange={(e) => onChange({ ...params, max: Number(e.target.value) })}
              className="w-20 rounded border border-gray-200 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none"
              placeholder="e.g. 8"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-500">Period</label>
            <select
              value={(params.period as string) ?? "per_claim"}
              onChange={(e) => onChange({ ...params, period: e.target.value })}
              className="rounded border border-gray-200 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none"
            >
              <option value="per_claim">Per claim</option>
              <option value="per_day">Per day</option>
              <option value="per_visit">Per visit</option>
            </select>
          </div>
        </div>
      );
    case "cap_amount":
      return (
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-500">
            Max Amount ($)
          </label>
          <input
            type="number"
            min="0"
            step="0.01"
            value={(params.max_amount as string) ?? ""}
            onChange={(e) => onChange({ max_amount: Number(e.target.value) })}
            className="w-32 rounded border border-gray-200 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none"
            placeholder="e.g. 500"
          />
        </div>
      );
    case "billing_increment":
      return (
        <div className="flex gap-2">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-500">Min Increment</label>
            <input
              type="number"
              min="0"
              step="0.01"
              value={(params.min_increment as string) ?? ""}
              onChange={(e) => onChange({ ...params, min_increment: Number(e.target.value) })}
              className="w-24 rounded border border-gray-200 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none"
              placeholder="0.25"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-500">Unit</label>
            <select
              value={(params.unit as string) ?? "hour"}
              onChange={(e) => onChange({ ...params, unit: e.target.value })}
              className="rounded border border-gray-200 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none"
            >
              <option value="hour">Hour</option>
              <option value="15min">15 min</option>
            </select>
          </div>
        </div>
      );
    case "bundling_prohibition":
      return (
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-500">
            Prohibited with (comma-separated codes)
          </label>
          <input
            type="text"
            value={((params.prohibited_with as string[]) ?? []).join(", ")}
            onChange={(e) =>
              onChange({
                prohibited_with: e.target.value
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean),
              })
            }
            className="w-full rounded border border-gray-200 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none"
            placeholder="e.g. IME.PHY_EXAM.TRAVEL_TRANSPORT, IME.PHY_EXAM.MILEAGE"
          />
        </div>
      );
    case "max_pct_of_invoice": {
      const useSuffix = !!(params.applies_to_suffix || params.applies_to_domain);
      return (
        <div className="space-y-3">
          {/* Row 1 — threshold + basis + description */}
          <div className="flex flex-wrap gap-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500">
                Max % of Invoice
              </label>
              <input
                type="number"
                min="0"
                max="100"
                step="0.1"
                value={(params.max_pct as string) ?? ""}
                onChange={(e) => onChange({ ...params, max_pct: Number(e.target.value) })}
                className="w-20 rounded border border-gray-200 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none"
                placeholder="5.0"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500">Basis</label>
              <select
                value={(params.basis as string) ?? "amount"}
                onChange={(e) => onChange({ ...params, basis: e.target.value })}
                className="rounded border border-gray-200 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none"
              >
                <option value="amount">Dollars (amount)</option>
                <option value="quantity">Hours (quantity)</option>
              </select>
            </div>
            <div className="flex-1 min-w-[160px]">
              <label className="mb-1 block text-xs font-medium text-gray-500">
                Description (shown in exception)
              </label>
              <input
                type="text"
                value={(params.description as string) ?? ""}
                onChange={(e) => onChange({ ...params, description: e.target.value })}
                className="w-full rounded border border-gray-200 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none"
                placeholder="Admin and Office Support lines"
              />
            </div>
          </div>

          {/* Row 2 — numerator targeting */}
          <div>
            <div className="mb-1 flex items-center gap-3">
              <span className="text-xs font-medium text-gray-500">Numerator — applies to:</span>
              <label className="flex items-center gap-1 text-xs text-gray-600 cursor-pointer">
                <input
                  type="radio"
                  name="pct-numerator-mode"
                  checked={!useSuffix}
                  onChange={() => {
                    const next = { ...params };
                    delete next.applies_to_suffix;
                    delete next.applies_to_domain;
                    onChange(next);
                  }}
                />
                Explicit codes
              </label>
              <label className="flex items-center gap-1 text-xs text-gray-600 cursor-pointer">
                <input
                  type="radio"
                  name="pct-numerator-mode"
                  checked={useSuffix}
                  onChange={() => {
                    const next = { ...params };
                    delete next.applies_to_codes;
                    onChange(next);
                  }}
                />
                Code suffix
              </label>
            </div>
            {!useSuffix ? (
              <input
                type="text"
                value={((params.applies_to_codes as string[]) ?? []).join(", ")}
                onChange={(e) =>
                  onChange({
                    ...params,
                    applies_to_codes: e.target.value
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean),
                  })
                }
                className="w-full rounded border border-gray-200 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none"
                placeholder="e.g. ENG.AOS.L6, ENG.PM.L6"
              />
            ) : (
              <div className="flex gap-2">
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-500">
                    Domain
                  </label>
                  <input
                    type="text"
                    value={(params.applies_to_domain as string) ?? ""}
                    onChange={(e) =>
                      onChange({ ...params, applies_to_domain: e.target.value })
                    }
                    className="w-24 rounded border border-gray-200 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none"
                    placeholder="ENG"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-500">
                    Code suffix
                  </label>
                  <input
                    type="text"
                    value={(params.applies_to_suffix as string) ?? ""}
                    onChange={(e) =>
                      onChange({ ...params, applies_to_suffix: e.target.value })
                    }
                    className="w-24 rounded border border-gray-200 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none"
                    placeholder=".L1"
                  />
                </div>
              </div>
            )}
          </div>

          {/* Row 3 — denominator (optional) */}
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-500">
              Denominator domain{" "}
              <span className="font-normal text-gray-400">(leave blank = all invoice lines)</span>
            </label>
            <input
              type="text"
              value={(params.denominator_domain as string) ?? ""}
              onChange={(e) =>
                onChange({
                  ...params,
                  denominator_domain: e.target.value || undefined,
                })
              }
              className="w-24 rounded border border-gray-200 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none"
              placeholder="ENG"
            />
          </div>
        </div>
      );
    }
    case "invoice_codes_exclusive":
      return (
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-500">
              Description{" "}
              <span className="font-normal text-gray-400">(shown in exception message)</span>
            </label>
            <input
              type="text"
              value={(params.description as string) ?? ""}
              onChange={(e) => onChange({ ...params, description: e.target.value })}
              className="w-full rounded border border-gray-200 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none"
              placeholder="primary ladder/roof service"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-500">
              Mutually exclusive codes{" "}
              <span className="font-normal text-gray-400">(comma-separated — at most one may appear per invoice)</span>
            </label>
            <input
              type="text"
              value={((params.exclusive_codes as string[]) ?? []).join(", ")}
              onChange={(e) =>
                onChange({
                  ...params,
                  exclusive_codes: e.target.value
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean),
                })
              }
              className="w-full rounded border border-gray-200 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none"
              placeholder="e.g. LA.ROOF_INSPECT_HARNESS.FLAT_FEE, LA.ROOF_INSPECT.FLAT_FEE, LA.LADDER_ACCESS.FLAT_FEE"
            />
            <p className="mt-1 text-xs text-gray-400">
              Example: Ladder Assist service hierarchy — billing Roof Inspection includes Ladder Access, so both cannot appear together.
            </p>
          </div>
        </div>
      );
    case "requires_auth":
    default:
      return <p className="text-xs text-gray-400">No additional parameters needed.</p>;
  }
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ContractDetailPage() {
  const params = useParams();
  const router = useRouter();
  const contractId = params.id as string;
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState<"rate-cards" | "guidelines">("rate-cards");
  const [showAddRateCard, setShowAddRateCard] = useState(false);
  const [showAddGuideline, setShowAddGuideline] = useState(false);
  const [rcForm, setRcForm] = useState<RateCardCreate>(blankRateCard());
  const [glForm, setGlForm] = useState<GuidelineCreate>(blankGuideline());
  const [formError, setFormError] = useState<string | null>(null);
  // Which tiered rate card row is expanded (by id)
  const [expandedRcId, setExpandedRcId] = useState<string | null>(null);

  // ── Queries ──────────────────────────────────────────────────────────────────
  const {
    data: contract,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["admin-contract", contractId],
    queryFn: () => getAdminContract(contractId),
  });

  // ── Mutations ────────────────────────────────────────────────────────────────
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["admin-contract", contractId] });
    queryClient.invalidateQueries({ queryKey: ["admin-contracts"] });
  };

  const addRcMutation = useMutation({
    mutationFn: (payload: RateCardCreate) => createRateCard(contractId, payload),
    onSuccess: () => {
      invalidate();
      setShowAddRateCard(false);
      setRcForm(blankRateCard(contract?.effective_from));
      setFormError(null);
    },
    onError: (err: Error) => setFormError(err.message),
  });

  const deleteRcMutation = useMutation({
    mutationFn: (rcId: string) => deleteRateCard(contractId, rcId),
    onSuccess: invalidate,
  });

  const addGlMutation = useMutation({
    mutationFn: (payload: GuidelineCreate) => createGuideline(contractId, payload),
    onSuccess: () => {
      invalidate();
      setShowAddGuideline(false);
      setGlForm(blankGuideline());
      setFormError(null);
    },
    onError: (err: Error) => setFormError(err.message),
  });

  const toggleGlMutation = useMutation({
    mutationFn: ({ gId, isActive }: { gId: string; isActive: boolean }) =>
      updateGuideline(contractId, gId, isActive),
    onSuccess: invalidate,
  });

  const deleteGlMutation = useMutation({
    mutationFn: (gId: string) => deleteGuideline(contractId, gId),
    onSuccess: invalidate,
  });

  // ── Loading / error states ───────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
      </div>
    );
  }

  if (error || !contract) {
    return (
      <div className="py-16 text-center">
        <p className="text-sm text-red-600">Failed to load contract.</p>
        <button
          onClick={() => router.push("/admin/contracts")}
          className="mt-2 text-sm text-blue-600 hover:text-blue-800"
        >
          ← Back to contracts
        </button>
      </div>
    );
  }

  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-6">
      {/* Header + back */}
      <div className="flex items-start justify-between">
        <div>
          <button
            onClick={() => router.push("/admin/contracts")}
            className="mb-2 text-xs text-gray-400 hover:text-gray-600"
          >
            ← Contracts
          </button>
          <h1 className="text-2xl font-bold text-gray-900">{contract.name}</h1>
        </div>
        <span
          className={`mt-1 inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${
            contract.is_active ? "bg-green-50 text-green-700" : "bg-gray-100 text-gray-500"
          }`}
        >
          {contract.is_active ? "Active" : "Inactive"}
        </span>
      </div>

      {/* Contract metadata card */}
      <div className="rounded-xl border bg-white p-5 shadow-sm">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-xs font-medium text-gray-400">Supplier</dt>
            <dd className="mt-0.5 font-medium text-gray-900">
              {contract.supplier_name ?? "—"}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium text-gray-400">Effective</dt>
            <dd className="mt-0.5 text-gray-700">
              {contract.effective_from}
              {contract.effective_to ? ` → ${contract.effective_to}` : " → ongoing"}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium text-gray-400">Geography</dt>
            <dd className="mt-0.5 capitalize text-gray-700">{contract.geography_scope}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium text-gray-400">Rates / Rules</dt>
            <dd className="mt-0.5 text-gray-700">
              {contract.rate_cards.length} rate cards · {contract.guidelines.length} guidelines
            </dd>
          </div>
          {contract.notes && (
            <div className="col-span-2 sm:col-span-4">
              <dt className="text-xs font-medium text-gray-400">Notes</dt>
              <dd className="mt-0.5 text-gray-600">{contract.notes}</dd>
            </div>
          )}
        </dl>
      </div>

      {/* Tabs */}
      <div>
        <div className="border-b border-gray-200">
          <nav className="-mb-px flex gap-1">
            {(["rate-cards", "guidelines"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2.5 text-sm font-medium transition-colors ${
                  activeTab === tab
                    ? "border-b-2 border-blue-600 text-blue-600"
                    : "text-gray-500 hover:border-b-2 hover:border-gray-300 hover:text-gray-700"
                }`}
              >
                {tab === "rate-cards"
                  ? `Rate Cards (${contract.rate_cards.length})`
                  : `Guidelines (${contract.guidelines.length})`}
              </button>
            ))}
          </nav>
        </div>

        {/* ── Rate Cards tab ──────────────────────────────────────────────── */}
        {activeTab === "rate-cards" && (
          <div className="mt-4 space-y-4">
            <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
              <table className="min-w-full divide-y divide-gray-100">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                      Code
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                      Service
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                      Type
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-gray-500">
                      Rate
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-gray-500">
                      Max Units
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                      All-Incl.
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                      Effective
                    </th>
                    <th className="w-12" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {contract.rate_cards.length === 0 && !showAddRateCard ? (
                    <tr>
                      <td colSpan={8} className="px-4 py-8 text-center text-sm text-gray-400">
                        No rate cards yet.
                      </td>
                    </tr>
                  ) : null}
                  {contract.rate_cards.map((rc) => {
                    const isTiered = rc.rate_type === "tiered";
                    const isExpanded = expandedRcId === rc.id;
                    return (
                      <React.Fragment key={rc.id}>
                        <tr className="hover:bg-gray-50 transition-colors">
                          <td className="px-4 py-3">
                            <span className="font-mono text-xs text-gray-700">{rc.taxonomy_code}</span>
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-600">
                            {rc.taxonomy_label ?? "—"}
                          </td>
                          {/* Type badge */}
                          <td className="px-4 py-3">
                            <span className={`inline-flex rounded px-1.5 py-0.5 text-xs font-medium ${
                              RATE_TYPE_COLORS[rc.rate_type] ?? "bg-gray-100 text-gray-600"
                            }`}>
                              {RATE_TYPE_LABELS[rc.rate_type] ?? rc.rate_type}
                            </span>
                          </td>
                          {/* Rate — for tiered show band count + expand toggle */}
                          <td className="px-4 py-3 text-right font-mono text-sm text-gray-900">
                            {isTiered ? (
                              <button
                                onClick={() => setExpandedRcId(isExpanded ? null : rc.id)}
                                className="text-purple-600 hover:text-purple-800 font-medium text-xs"
                              >
                                {rc.rate_tiers?.length ?? 0} band{(rc.rate_tiers?.length ?? 0) !== 1 ? "s" : ""}{" "}
                                {isExpanded ? "▲" : "▼"}
                              </button>
                            ) : (
                              rc.contracted_rate != null
                                ? `$${Number(rc.contracted_rate).toFixed(2)}`
                                : "—"
                            )}
                          </td>
                          <td className="px-4 py-3 text-right text-sm text-gray-600">
                            {rc.max_units ? Number(rc.max_units).toString() : "—"}
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-600">
                            {rc.is_all_inclusive ? (
                              <span className="text-green-600">✓ Yes</span>
                            ) : (
                              <span className="text-gray-400">No</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-600">
                            {rc.effective_from}
                            {rc.effective_to && (
                              <span className="text-gray-400"> → {rc.effective_to}</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-right">
                            <button
                              onClick={() => {
                                if (confirm("Delete this rate card?")) {
                                  deleteRcMutation.mutate(rc.id);
                                }
                              }}
                              className="text-xs text-gray-400 hover:text-red-500 transition-colors"
                              title="Delete rate card"
                            >
                              ✕
                            </button>
                          </td>
                        </tr>
                        {/* Expanded tier bands row */}
                        {isTiered && isExpanded && rc.rate_tiers && rc.rate_tiers.length > 0 && (
                          <tr className="bg-purple-50">
                            <td colSpan={8} className="px-6 py-3">
                              <p className="mb-2 text-xs font-semibold text-purple-700">
                                Rate Bands
                              </p>
                              <table className="text-xs">
                                <thead>
                                  <tr className="text-purple-600">
                                    <th className="pr-6 text-left font-medium pb-1">From unit</th>
                                    <th className="pr-6 text-left font-medium pb-1">To unit</th>
                                    <th className="pr-6 text-left font-medium pb-1">Rate</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-purple-100">
                                  {rc.rate_tiers.map((tier, ti) => (
                                    <tr key={ti}>
                                      <td className="pr-6 py-1 font-mono">{tier.from_unit}</td>
                                      <td className="pr-6 py-1 font-mono">
                                        {tier.to_unit != null ? tier.to_unit : <span className="text-purple-400">∞</span>}
                                      </td>
                                      <td className="pr-6 py-1 font-mono">${Number(tier.rate).toFixed(4)}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}

                  {/* Inline add form */}
                  {showAddRateCard && (
                    <React.Fragment>
                      <tr className="bg-blue-50">
                        {/* Taxonomy code */}
                        <td className="px-4 py-2">
                          <select
                            value={rcForm.taxonomy_code}
                            onChange={(e) =>
                              setRcForm({ ...rcForm, taxonomy_code: e.target.value })
                            }
                            className="w-full rounded border border-blue-200 px-2 py-1 text-xs focus:border-blue-500 focus:outline-none"
                          >
                            <option value="">Select…</option>
                            {TAXONOMY_DOMAINS.map((domain) => (
                              <optgroup key={domain} label={DOMAIN_LABELS[domain] ?? domain}>
                                {TAXONOMY_OPTIONS.filter((t) => t.domain === domain).map((t) => (
                                  <option key={t.code} value={t.code}>
                                    {t.code} — {t.label}
                                  </option>
                                ))}
                              </optgroup>
                            ))}
                          </select>
                        </td>
                        {/* Service label */}
                        <td className="px-4 py-2 text-xs text-gray-500">
                          {TAXONOMY_OPTIONS.find((t) => t.code === rcForm.taxonomy_code)?.label ?? ""}
                        </td>
                        {/* Rate type */}
                        <td className="px-4 py-2">
                          <select
                            value={rcForm.rate_type}
                            onChange={(e) =>
                              setRcForm({ ...rcForm, rate_type: e.target.value })
                            }
                            className="rounded border border-blue-200 px-2 py-1 text-xs focus:border-blue-500 focus:outline-none"
                          >
                            <option value="flat">Flat Fee</option>
                            <option value="tiered">Tiered</option>
                            <option value="hourly">Hourly</option>
                            <option value="mileage">Per Mile</option>
                            <option value="per_diem">Per Diem</option>
                          </select>
                        </td>
                        {/* Rate — conditional on rate_type */}
                        <td className="px-4 py-2">
                          {rcForm.rate_type === "tiered" ? (
                            <span className="text-xs text-purple-600 font-medium">
                              {(rcForm.rate_tiers as RateTier[] ?? []).length > 0
                                ? `${(rcForm.rate_tiers as RateTier[]).length} bands ↓`
                                : "Add bands ↓"}
                            </span>
                          ) : (
                            <input
                              type="number"
                              step="0.01"
                              min="0"
                              value={rcForm.contracted_rate ?? ""}
                              onChange={(e) =>
                                setRcForm({ ...rcForm, contracted_rate: e.target.value })
                              }
                              placeholder="0.00"
                              className="w-24 rounded border border-blue-200 px-2 py-1 text-xs text-right focus:border-blue-500 focus:outline-none"
                            />
                          )}
                        </td>
                        {/* Max units */}
                        <td className="px-4 py-2">
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            value={rcForm.max_units ?? ""}
                            onChange={(e) =>
                              setRcForm({ ...rcForm, max_units: e.target.value || null })
                            }
                            placeholder="—"
                            className="w-20 rounded border border-blue-200 px-2 py-1 text-xs text-right focus:border-blue-500 focus:outline-none"
                          />
                        </td>
                        {/* All-inclusive */}
                        <td className="px-4 py-2">
                          <input
                            type="checkbox"
                            checked={rcForm.is_all_inclusive}
                            onChange={(e) =>
                              setRcForm({ ...rcForm, is_all_inclusive: e.target.checked })
                            }
                            className="rounded border-gray-300"
                          />
                        </td>
                        {/* Effective from */}
                        <td className="px-4 py-2">
                          <input
                            type="date"
                            value={rcForm.effective_from}
                            onChange={(e) =>
                              setRcForm({ ...rcForm, effective_from: e.target.value })
                            }
                            className="rounded border border-blue-200 px-2 py-1 text-xs focus:border-blue-500 focus:outline-none"
                          />
                        </td>
                        {/* Save / Cancel */}
                        <td className="px-4 py-2">
                          <div className="flex gap-1">
                            <button
                              onClick={() => {
                                setFormError(null);
                                const tiers = rcForm.rate_tiers as RateTier[] ?? [];
                                const isValid =
                                  rcForm.taxonomy_code &&
                                  rcForm.effective_from &&
                                  (rcForm.rate_type === "tiered"
                                    ? tiers.length > 0
                                    : rcForm.contracted_rate);
                                if (!isValid) {
                                  setFormError(
                                    rcForm.rate_type === "tiered"
                                      ? "Code, effective date, and at least one tier band are required."
                                      : "Code, rate, and effective date are required."
                                  );
                                  return;
                                }
                                addRcMutation.mutate({
                                  ...rcForm,
                                  contracted_rate: rcForm.rate_type === "tiered" ? null : rcForm.contracted_rate,
                                  rate_tiers: rcForm.rate_type === "tiered" ? tiers : null,
                                });
                              }}
                              disabled={addRcMutation.isPending}
                              className="rounded bg-blue-600 px-2 py-1 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                            >
                              {addRcMutation.isPending ? "…" : "Save"}
                            </button>
                            <button
                              onClick={() => {
                                setShowAddRateCard(false);
                                setFormError(null);
                              }}
                              className="rounded border border-gray-300 px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
                            >
                              Cancel
                            </button>
                          </div>
                        </td>
                      </tr>
                      {/* Tier band editor row (only when rate_type === "tiered") */}
                      {rcForm.rate_type === "tiered" && (
                        <tr className="bg-purple-50">
                          <td colSpan={8} className="pb-3 pt-1 px-6">
                            <div className="space-y-2">
                              <p className="text-xs font-medium text-purple-700 mb-1">
                                Rate Bands
                                <span className="ml-1.5 font-normal text-purple-500">
                                  (leave "To unit" blank on the last band for unlimited)
                                </span>
                              </p>
                              {(rcForm.rate_tiers as RateTier[] ?? []).length > 0 && (
                                <div className="flex gap-4 text-xs text-purple-600 font-medium mb-0.5">
                                  <span className="w-16">From</span>
                                  <span className="w-20">To (∞=blank)</span>
                                  <span className="w-20">Rate ($)</span>
                                </div>
                              )}
                              {(rcForm.rate_tiers as RateTier[] ?? []).map((tier, ti) => (
                                <div key={ti} className="flex items-center gap-3">
                                  <input
                                    type="number" min="1" step="1"
                                    value={tier.from_unit}
                                    onChange={(e) => {
                                      const tiers = [...(rcForm.rate_tiers as RateTier[])];
                                      tiers[ti] = { ...tiers[ti], from_unit: Number(e.target.value) };
                                      setRcForm({ ...rcForm, rate_tiers: tiers });
                                    }}
                                    className="w-16 rounded border border-purple-200 bg-white px-2 py-1 text-xs focus:border-purple-400 focus:outline-none"
                                  />
                                  <input
                                    type="number" min="1" step="1"
                                    value={tier.to_unit ?? ""}
                                    onChange={(e) => {
                                      const tiers = [...(rcForm.rate_tiers as RateTier[])];
                                      tiers[ti] = { ...tiers[ti], to_unit: e.target.value ? Number(e.target.value) : null };
                                      setRcForm({ ...rcForm, rate_tiers: tiers });
                                    }}
                                    placeholder="∞"
                                    className="w-20 rounded border border-purple-200 bg-white px-2 py-1 text-xs focus:border-purple-400 focus:outline-none"
                                  />
                                  <input
                                    type="number" step="0.0001" min="0"
                                    value={tier.rate}
                                    onChange={(e) => {
                                      const tiers = [...(rcForm.rate_tiers as RateTier[])];
                                      tiers[ti] = { ...tiers[ti], rate: e.target.value };
                                      setRcForm({ ...rcForm, rate_tiers: tiers });
                                    }}
                                    placeholder="0.00"
                                    className="w-20 rounded border border-purple-200 bg-white px-2 py-1 text-xs focus:border-purple-400 focus:outline-none"
                                  />
                                  <button
                                    type="button"
                                    onClick={() => {
                                      const tiers = (rcForm.rate_tiers as RateTier[]).filter((_, k) => k !== ti);
                                      setRcForm({ ...rcForm, rate_tiers: tiers });
                                    }}
                                    className="text-purple-300 hover:text-red-500 transition-colors"
                                  >✕</button>
                                </div>
                              ))}
                              <button
                                type="button"
                                onClick={() => {
                                  const existing = rcForm.rate_tiers as RateTier[] ?? [];
                                  const lastTo = existing.length > 0 ? (existing[existing.length - 1].to_unit ?? 0) + 1 : 1;
                                  setRcForm({ ...rcForm, rate_tiers: [...existing, { from_unit: lastTo, to_unit: null, rate: "" }] });
                                }}
                                className="text-xs text-purple-600 hover:text-purple-800 font-medium"
                              >
                                + Add band
                              </button>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  )}
                </tbody>
              </table>
            </div>

            {formError && activeTab === "rate-cards" && (
              <p className="text-xs text-red-600">{formError}</p>
            )}

            {!showAddRateCard && (
              <button
                onClick={() => {
                  setRcForm(blankRateCard(contract.effective_from));
                  setFormError(null);
                  setShowAddRateCard(true);
                }}
                className="rounded-md border border-dashed border-gray-300 px-4 py-2 text-sm font-medium text-gray-500 hover:border-blue-400 hover:text-blue-600 transition-colors"
              >
                + Add Rate Card
              </button>
            )}
          </div>
        )}

        {/* ── Guidelines tab ──────────────────────────────────────────────── */}
        {activeTab === "guidelines" && (
          <div className="mt-4 space-y-4">
            {contract.guidelines.length === 0 && !showAddGuideline ? (
              <div className="rounded-xl border border-gray-200 bg-white py-12 text-center shadow-sm">
                <p className="text-sm text-gray-400">No guidelines yet.</p>
              </div>
            ) : (
              <div className="space-y-2">
                {contract.guidelines.map((g) => (
                  <div
                    key={g.id}
                    className={`rounded-xl border bg-white p-4 shadow-sm transition-opacity ${
                      !g.is_active ? "opacity-50" : ""
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0 space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="rounded bg-purple-100 px-2 py-0.5 text-xs font-medium text-purple-700">
                            {g.rule_type}
                          </span>
                          {g.taxonomy_code && (
                            <span className="font-mono text-xs text-gray-600 bg-gray-100 px-1.5 py-0.5 rounded">
                              {g.taxonomy_code}
                            </span>
                          )}
                          {g.domain && !g.taxonomy_code && (
                            <span className="text-xs text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">
                              Domain: {g.domain}
                            </span>
                          )}
                          <span
                            className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                              g.severity === "ERROR"
                                ? "bg-red-100 text-red-700"
                                : g.severity === "WARNING"
                                ? "bg-amber-100 text-amber-700"
                                : "bg-blue-100 text-blue-700"
                            }`}
                          >
                            {g.severity}
                          </span>
                          {!g.is_active && (
                            <span className="text-xs text-gray-400">(inactive)</span>
                          )}
                        </div>
                        {Object.keys(g.rule_params).length > 0 && (
                          <p className="text-xs text-gray-500 font-mono">
                            {JSON.stringify(g.rule_params)}
                          </p>
                        )}
                        {g.narrative_source && (
                          <p className="text-xs text-gray-500 line-clamp-2 italic">
                            "{g.narrative_source}"
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <button
                          onClick={() =>
                            toggleGlMutation.mutate({ gId: g.id, isActive: !g.is_active })
                          }
                          disabled={toggleGlMutation.isPending}
                          className="text-xs text-gray-400 hover:text-blue-600 transition-colors"
                          title={g.is_active ? "Deactivate" : "Activate"}
                        >
                          {g.is_active ? "⏸ Disable" : "▶ Enable"}
                        </button>
                        <button
                          onClick={() => {
                            if (confirm("Delete this guideline?")) {
                              deleteGlMutation.mutate(g.id);
                            }
                          }}
                          className="text-xs text-gray-400 hover:text-red-500 transition-colors"
                          title="Delete guideline"
                        >
                          ✕
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Inline add guideline form */}
            {showAddGuideline && (
              <div className="rounded-xl border border-blue-200 bg-blue-50 p-5 shadow-sm space-y-4">
                <h3 className="text-sm font-semibold text-gray-900">Add Guideline</h3>

                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  {/* Rule type */}
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-500">
                      Rule Type
                    </label>
                    <select
                      value={glForm.rule_type}
                      onChange={(e) =>
                        setGlForm({ ...glForm, rule_type: e.target.value, rule_params: {} })
                      }
                      className="w-full rounded border border-gray-200 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
                    >
                      {RULE_TYPES.map((rt) => (
                        <option key={rt.value} value={rt.value}>
                          {rt.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Severity */}
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-500">
                      Severity
                    </label>
                    <select
                      value={glForm.severity}
                      onChange={(e) => setGlForm({ ...glForm, severity: e.target.value })}
                      className="w-full rounded border border-gray-200 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
                    >
                      <option value="ERROR">ERROR</option>
                      <option value="WARNING">WARNING</option>
                      <option value="INFO">INFO</option>
                    </select>
                  </div>

                  {/* Applies to: taxonomy code OR domain */}
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-500">
                      Applies to Taxonomy Code
                    </label>
                    <select
                      value={glForm.taxonomy_code ?? ""}
                      onChange={(e) =>
                        setGlForm({ ...glForm, taxonomy_code: e.target.value || null, domain: null })
                      }
                      className="w-full rounded border border-gray-200 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
                    >
                      <option value="">(none — use domain below)</option>
                      {TAXONOMY_DOMAINS.map((domain) => (
                        <optgroup key={domain} label={DOMAIN_LABELS[domain] ?? domain}>
                          {TAXONOMY_OPTIONS.filter((t) => t.domain === domain).map((t) => (
                            <option key={t.code} value={t.code}>
                              {t.code} — {t.label}
                            </option>
                          ))}
                        </optgroup>
                      ))}
                    </select>
                  </div>

                  {/* Domain (only if no taxonomy code) */}
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-500">
                      Or Applies to Domain
                    </label>
                    <select
                      value={glForm.domain ?? ""}
                      disabled={!!glForm.taxonomy_code}
                      onChange={(e) =>
                        setGlForm({ ...glForm, domain: e.target.value || null, taxonomy_code: null })
                      }
                      className="w-full rounded border border-gray-200 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none disabled:bg-gray-50 disabled:text-gray-400"
                    >
                      <option value="">(domain-independent)</option>
                      {TAXONOMY_DOMAINS.map((d) => (
                        <option key={d} value={d}>
                          {d}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* Dynamic rule params */}
                <div>
                  <label className="mb-2 block text-xs font-medium text-gray-500">
                    Rule Parameters
                  </label>
                  <RuleParamsFields
                    ruleType={glForm.rule_type}
                    params={glForm.rule_params}
                    onChange={(p) => setGlForm({ ...glForm, rule_params: p })}
                  />
                </div>

                {/* Narrative source */}
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-500">
                    Source Text (original contract language)
                  </label>
                  <textarea
                    value={glForm.narrative_source ?? ""}
                    onChange={(e) =>
                      setGlForm({ ...glForm, narrative_source: e.target.value || null })
                    }
                    rows={2}
                    placeholder="Paste the relevant contract clause here…"
                    className="w-full rounded border border-gray-200 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
                  />
                </div>

                {formError && activeTab === "guidelines" && (
                  <p className="text-xs text-red-600">{formError}</p>
                )}

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setFormError(null);
                      if (!glForm.rule_type) {
                        setFormError("Rule type is required.");
                        return;
                      }
                      addGlMutation.mutate(glForm);
                    }}
                    disabled={addGlMutation.isPending}
                    className="rounded-md bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                  >
                    {addGlMutation.isPending ? "Saving…" : "Save Guideline"}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setShowAddGuideline(false);
                      setFormError(null);
                    }}
                    className="rounded-md border border-gray-300 px-4 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {!showAddGuideline && (
              <button
                onClick={() => {
                  setGlForm(blankGuideline());
                  setFormError(null);
                  setShowAddGuideline(true);
                }}
                className="rounded-md border border-dashed border-gray-300 px-4 py-2 text-sm font-medium text-gray-500 hover:border-blue-400 hover:text-blue-600 transition-colors"
              >
                + Add Guideline
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
