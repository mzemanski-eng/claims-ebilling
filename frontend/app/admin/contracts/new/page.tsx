"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  createAdminContract,
  createGuideline,
  createRateCard,
  listAdminSuppliers,
  parseContractPdf,
} from "@/lib/api";
import type { GuidelineCreate, RateCardCreate } from "@/lib/types";

// ── Taxonomy options ───────────────────────────────────────────────────────────

const TAXONOMY_OPTIONS = [
  // IME
  { code: "IME.PHY_EXAM.PROF_FEE", label: "Physician Examination Professional Fee", domain: "IME" },
  { code: "IME.PHY_EXAM.TRAVEL_TRANSPORT", label: "Transportation", domain: "IME" },
  { code: "IME.PHY_EXAM.TRAVEL_LODGING", label: "Lodging", domain: "IME" },
  { code: "IME.PHY_EXAM.TRAVEL_MEALS", label: "Meals & Per Diem", domain: "IME" },
  { code: "IME.PHY_EXAM.MILEAGE", label: "Mileage", domain: "IME" },
  { code: "IME.MULTI_SPECIALTY.PROF_FEE", label: "Multi-Specialty Panel", domain: "IME" },
  { code: "IME.RECORDS_REVIEW.PROF_FEE", label: "Records Review No Exam", domain: "IME" },
  { code: "IME.ADDENDUM.PROF_FEE", label: "Addendum Report", domain: "IME" },
  { code: "IME.PEER_REVIEW.PROF_FEE", label: "Peer Review", domain: "IME" },
  { code: "IME.CANCELLATION.CANCEL_FEE", label: "Cancellation Fee", domain: "IME" },
  { code: "IME.NO_SHOW.NO_SHOW_FEE", label: "No-Show Fee", domain: "IME" },
  { code: "IME.ADMIN.SCHEDULING_FEE", label: "Administrative/Scheduling Fee", domain: "IME" },
  // ENG
  { code: "ENG.PROPERTY_INSPECT.PROF_FEE", label: "Property Inspection Professional Fee", domain: "ENG" },
  { code: "ENG.PROPERTY_INSPECT.TRAVEL_TRANSPORT", label: "Transportation", domain: "ENG" },
  { code: "ENG.PROPERTY_INSPECT.MILEAGE", label: "Mileage", domain: "ENG" },
  { code: "ENG.CAUSE_ORIGIN.PROF_FEE", label: "Cause & Origin Investigation", domain: "ENG" },
  { code: "ENG.STRUCTURAL_ASSESS.PROF_FEE", label: "Structural Assessment", domain: "ENG" },
  { code: "ENG.EXPERT_REPORT.PROF_FEE", label: "Expert Report", domain: "ENG" },
  { code: "ENG.FILE_REVIEW.PROF_FEE", label: "File Review", domain: "ENG" },
  { code: "ENG.SUPPLEMENTAL_INSPECT.PROF_FEE", label: "Supplemental Inspection", domain: "ENG" },
  { code: "ENG.TESTIMONY_DEPO.PROF_FEE", label: "Expert Testimony/Deposition", domain: "ENG" },
  // IA
  { code: "IA.FIELD_ASSIGN.PROF_FEE", label: "Field Assignment Professional Fee", domain: "IA" },
  { code: "IA.FIELD_ASSIGN.TRAVEL_TRANSPORT", label: "Transportation", domain: "IA" },
  { code: "IA.FIELD_ASSIGN.MILEAGE", label: "Mileage", domain: "IA" },
  { code: "IA.FIELD_ASSIGN.TRAVEL_LODGING", label: "Lodging", domain: "IA" },
  { code: "IA.FIELD_ASSIGN.TRAVEL_MEALS", label: "Meals & Per Diem", domain: "IA" },
  { code: "IA.DESK_ASSIGN.PROF_FEE", label: "Desk Assignment Professional Fee", domain: "IA" },
  { code: "IA.CAT_ASSIGN.PROF_FEE", label: "Catastrophe Assignment Professional Fee", domain: "IA" },
  { code: "IA.PHOTO_DOC.PROF_FEE", label: "Photo & Documentation Services", domain: "IA" },
  { code: "IA.SUPPLEMENT_HANDLING.PROF_FEE", label: "Supplement Handling", domain: "IA" },
  { code: "IA.ADMIN.FILE_OPEN_FEE", label: "Administrative/File Open Fee", domain: "IA" },
  // INV
  { code: "INV.SURVEILLANCE.PROF_FEE", label: "Surveillance Professional Fee", domain: "INV" },
  { code: "INV.SURVEILLANCE.TRAVEL_TRANSPORT", label: "Transportation", domain: "INV" },
  { code: "INV.SURVEILLANCE.MILEAGE", label: "Mileage", domain: "INV" },
  { code: "INV.STATEMENT.PROF_FEE", label: "Recorded Statement", domain: "INV" },
  { code: "INV.BACKGROUND_ASSET.PROF_FEE", label: "Background/Asset Search", domain: "INV" },
  { code: "INV.AOE_COE.PROF_FEE", label: "AOE/COE Investigation", domain: "INV" },
  { code: "INV.SKIP_TRACE.PROF_FEE", label: "Skip Trace", domain: "INV" },
  // REC
  { code: "REC.MED_RECORDS.RETRIEVAL_FEE", label: "Medical Records Retrieval Fee", domain: "REC" },
  { code: "REC.MED_RECORDS.COPY_REPRO", label: "Copy/Reproduction Fee", domain: "REC" },
  { code: "REC.MED_RECORDS.POSTAGE_COURIER", label: "Postage/Courier", domain: "REC" },
  { code: "REC.MED_RECORDS.RUSH_PREMIUM", label: "Rush/Expedite Premium", domain: "REC" },
  { code: "REC.MED_RECORDS.CERT_COPY_FEE", label: "Certified Copy Fee", domain: "REC" },
  { code: "REC.EMPLOYMENT_RECORDS.RETRIEVAL_FEE", label: "Employment Records Retrieval", domain: "REC" },
  { code: "REC.LEGAL_RECORDS.RETRIEVAL_FEE", label: "Legal/Court Records Retrieval", domain: "REC" },
  { code: "REC.ADMIN.PROCESSING_FEE", label: "Administrative/Processing Fee", domain: "REC" },
  // XDOMAIN
  { code: "XDOMAIN.PASS_THROUGH.THIRD_PARTY_COST", label: "Pass-Through Third-Party Cost", domain: "XDOMAIN" },
  { code: "XDOMAIN.ADMIN_MISC.ADMIN_FEE", label: "Miscellaneous Administrative Fee", domain: "XDOMAIN" },
];

const DOMAINS = [...new Set(TAXONOMY_OPTIONS.map((t) => t.domain))];

// ── Types ──────────────────────────────────────────────────────────────────────

interface RateCardRow extends RateCardCreate {
  _key: number;
}

interface GuidelineRow extends GuidelineCreate {
  _key: number;
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function NewContractPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  let _nextKey = 0;
  const nextKey = () => ++_nextKey;

  // ── Form state ──────────────────────────────────────────────────────────────
  const [supplierId, setSupplierId] = useState("");
  const [name, setName] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [effectiveTo, setEffectiveTo] = useState("");
  const [geographyScope, setGeographyScope] = useState("national");
  const [notes, setNotes] = useState("");

  // ── AI extraction state ─────────────────────────────────────────────────────
  const [isParsing, setIsParsing] = useState(false);
  const [extractionNotes, setExtractionNotes] = useState("");
  const [rateCards, setRateCards] = useState<RateCardRow[]>([]);
  const [guidelines, setGuidelines] = useState<GuidelineRow[]>([]);

  // ── Submit state ────────────────────────────────────────────────────────────
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: suppliers } = useQuery({
    queryKey: ["admin-suppliers"],
    queryFn: listAdminSuppliers,
    staleTime: 5 * 60 * 1000,
  });

  // ── PDF Upload handler ───────────────────────────────────────────────────────
  async function handlePdfUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!supplierId) {
      setError("Please select a supplier before uploading a PDF.");
      return;
    }
    setError(null);
    setIsParsing(true);
    try {
      const result = await parseContractPdf(supplierId, file);
      // Pre-fill form fields
      if (result.contract.name) setName(result.contract.name);
      if (result.contract.effective_from) setEffectiveFrom(result.contract.effective_from);
      if (result.contract.effective_to) setEffectiveTo(result.contract.effective_to);
      if (result.contract.geography_scope) setGeographyScope(result.contract.geography_scope);
      if (result.contract.notes) setNotes(result.contract.notes);
      // Load extracted rate cards and guidelines
      setRateCards(result.rate_cards.map((rc) => ({ ...rc, _key: nextKey() })));
      setGuidelines(result.guidelines.map((g) => ({ ...g, _key: nextKey() })));
      setExtractionNotes(result.extraction_notes);
    } catch (err) {
      setError(err instanceof Error ? err.message : "PDF parsing failed");
    } finally {
      setIsParsing(false);
      // Reset file input so same file can be re-uploaded
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  // ── Submit handler ───────────────────────────────────────────────────────────
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!supplierId || !name || !effectiveFrom) {
      setError("Supplier, contract name, and effective from date are required.");
      return;
    }
    setError(null);
    setIsSubmitting(true);
    try {
      // 1. Create the contract
      const contract = await createAdminContract({
        supplier_id: supplierId,
        name,
        effective_from: effectiveFrom,
        effective_to: effectiveTo || null,
        geography_scope: geographyScope,
        state_codes: null,
        notes: notes || null,
      });

      // 2. Add rate cards sequentially
      for (const rc of rateCards) {
        await createRateCard(contract.id, {
          taxonomy_code: rc.taxonomy_code,
          contracted_rate: rc.contracted_rate,
          max_units: rc.max_units,
          is_all_inclusive: rc.is_all_inclusive,
          effective_from: rc.effective_from || effectiveFrom,
          effective_to: rc.effective_to,
        });
      }

      // 3. Add guidelines sequentially
      for (const g of guidelines) {
        await createGuideline(contract.id, {
          taxonomy_code: g.taxonomy_code,
          domain: g.domain,
          rule_type: g.rule_type,
          rule_params: g.rule_params,
          severity: g.severity,
          narrative_source: g.narrative_source,
        });
      }

      router.push(`/admin/contracts/${contract.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create contract");
      setIsSubmitting(false);
    }
  }

  const hasExtracted = rateCards.length > 0 || guidelines.length > 0 || extractionNotes;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">New Contract</h1>
        <p className="mt-1 text-sm text-gray-500">
          Fill in the details manually or upload a PDF to let AI extract the rates and rules.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Contract details card */}
        <div className="rounded-xl border bg-white p-6 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-gray-900">Contract Details</h2>
            {/* PDF Upload */}
            <div className="flex items-center gap-3">
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf"
                className="hidden"
                onChange={handlePdfUpload}
                id="pdf-upload"
              />
              <label
                htmlFor="pdf-upload"
                className={`cursor-pointer rounded-md border px-3 py-1.5 text-sm font-medium transition-colors ${
                  isParsing
                    ? "border-blue-300 bg-blue-50 text-blue-500"
                    : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
                }`}
              >
                {isParsing ? (
                  <span className="flex items-center gap-2">
                    <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
                    Reading contract with AI…
                  </span>
                ) : (
                  "📄 Upload PDF Contract"
                )}
              </label>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {/* Supplier */}
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500">
                Supplier <span className="text-red-500">*</span>
              </label>
              <select
                value={supplierId}
                onChange={(e) => setSupplierId(e.target.value)}
                required
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              >
                <option value="">Select supplier…</option>
                {suppliers?.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Contract name */}
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500">
                Contract Name <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. IME Services Agreement 2025"
                required
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>

            {/* Effective from */}
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500">
                Effective From <span className="text-red-500">*</span>
              </label>
              <input
                type="date"
                value={effectiveFrom}
                onChange={(e) => setEffectiveFrom(e.target.value)}
                required
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>

            {/* Effective to */}
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500">
                Effective To
              </label>
              <input
                type="date"
                value={effectiveTo}
                onChange={(e) => setEffectiveTo(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>

            {/* Geography scope */}
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500">
                Geography Scope
              </label>
              <select
                value={geographyScope}
                onChange={(e) => setGeographyScope(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              >
                <option value="national">National</option>
                <option value="regional">Regional</option>
                <option value="state">State</option>
              </select>
            </div>

            {/* Notes */}
            <div className="sm:col-span-2">
              <label className="mb-1 block text-xs font-medium text-gray-500">
                Notes
              </label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={2}
                placeholder="Optional notes about this contract…"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
          </div>
        </div>

        {/* AI extraction notes */}
        {extractionNotes && (
          <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3">
            <p className="text-xs font-medium text-blue-800">AI Extraction Notes</p>
            <p className="mt-0.5 text-sm text-blue-700">{extractionNotes}</p>
          </div>
        )}

        {/* Extracted rate cards */}
        {hasExtracted && (
          <div className="rounded-xl border bg-white p-6 shadow-sm space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-semibold text-gray-900">Rate Cards to Add</h2>
                <p className="text-xs text-gray-500 mt-0.5">
                  {rateCards.length} extracted · Remove any that look incorrect before saving
                </p>
              </div>
              <button
                type="button"
                onClick={() =>
                  setRateCards((prev) => [
                    ...prev,
                    {
                      _key: nextKey(),
                      taxonomy_code: "",
                      contracted_rate: "",
                      max_units: null,
                      is_all_inclusive: false,
                      effective_from: effectiveFrom,
                      effective_to: null,
                    },
                  ])
                }
                className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50"
              >
                + Add row
              </button>
            </div>

            {rateCards.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-4">
                No rate cards extracted. Add one manually with the button above.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100">
                      <th className="pb-2 text-left text-xs font-medium text-gray-500">Taxonomy Code</th>
                      <th className="pb-2 text-left text-xs font-medium text-gray-500">Rate ($)</th>
                      <th className="pb-2 text-left text-xs font-medium text-gray-500">Max Units</th>
                      <th className="pb-2 text-left text-xs font-medium text-gray-500">All-Inclusive</th>
                      <th className="pb-2 text-left text-xs font-medium text-gray-500">Eff. From</th>
                      <th className="w-8" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {rateCards.map((rc, i) => (
                      <tr key={rc._key}>
                        <td className="py-1.5 pr-2">
                          <select
                            value={rc.taxonomy_code}
                            onChange={(e) => {
                              const v = e.target.value;
                              setRateCards((prev) =>
                                prev.map((r, j) => (j === i ? { ...r, taxonomy_code: v } : r))
                              );
                            }}
                            className="w-full rounded border border-gray-200 px-2 py-1 text-xs focus:border-blue-500 focus:outline-none"
                          >
                            <option value="">Select…</option>
                            {DOMAINS.map((domain) => (
                              <optgroup key={domain} label={domain}>
                                {TAXONOMY_OPTIONS.filter((t) => t.domain === domain).map((t) => (
                                  <option key={t.code} value={t.code}>
                                    {t.code} — {t.label}
                                  </option>
                                ))}
                              </optgroup>
                            ))}
                          </select>
                        </td>
                        <td className="py-1.5 pr-2">
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            value={rc.contracted_rate}
                            onChange={(e) =>
                              setRateCards((prev) =>
                                prev.map((r, j) =>
                                  j === i ? { ...r, contracted_rate: e.target.value } : r
                                )
                              )
                            }
                            className="w-24 rounded border border-gray-200 px-2 py-1 text-xs focus:border-blue-500 focus:outline-none"
                          />
                        </td>
                        <td className="py-1.5 pr-2">
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            value={rc.max_units ?? ""}
                            placeholder="—"
                            onChange={(e) =>
                              setRateCards((prev) =>
                                prev.map((r, j) =>
                                  j === i
                                    ? { ...r, max_units: e.target.value || null }
                                    : r
                                )
                              )
                            }
                            className="w-20 rounded border border-gray-200 px-2 py-1 text-xs focus:border-blue-500 focus:outline-none"
                          />
                        </td>
                        <td className="py-1.5 pr-2">
                          <input
                            type="checkbox"
                            checked={rc.is_all_inclusive}
                            onChange={(e) =>
                              setRateCards((prev) =>
                                prev.map((r, j) =>
                                  j === i ? { ...r, is_all_inclusive: e.target.checked } : r
                                )
                              )
                            }
                            className="rounded border-gray-300"
                          />
                        </td>
                        <td className="py-1.5 pr-2">
                          <input
                            type="date"
                            value={rc.effective_from}
                            onChange={(e) =>
                              setRateCards((prev) =>
                                prev.map((r, j) =>
                                  j === i ? { ...r, effective_from: e.target.value } : r
                                )
                              )
                            }
                            className="rounded border border-gray-200 px-2 py-1 text-xs focus:border-blue-500 focus:outline-none"
                          />
                        </td>
                        <td className="py-1.5">
                          <button
                            type="button"
                            onClick={() =>
                              setRateCards((prev) => prev.filter((_, j) => j !== i))
                            }
                            className="text-gray-400 hover:text-red-500 transition-colors text-sm"
                            title="Remove"
                          >
                            ✕
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Extracted guidelines */}
        {hasExtracted && (
          <div className="rounded-xl border bg-white p-6 shadow-sm space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-semibold text-gray-900">Guidelines to Add</h2>
                <p className="text-xs text-gray-500 mt-0.5">
                  {guidelines.length} extracted · Review billing rules before saving
                </p>
              </div>
            </div>

            {guidelines.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-4">
                No guidelines extracted.
              </p>
            ) : (
              <div className="space-y-2">
                {guidelines.map((g, i) => (
                  <div
                    key={g._key}
                    className="flex items-start gap-3 rounded-lg border border-gray-100 bg-gray-50 p-3"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="rounded bg-purple-100 px-1.5 py-0.5 text-xs font-medium text-purple-700">
                          {g.rule_type}
                        </span>
                        {g.taxonomy_code && (
                          <span className="font-mono text-xs text-gray-600">
                            {g.taxonomy_code}
                          </span>
                        )}
                        {g.domain && !g.taxonomy_code && (
                          <span className="text-xs text-gray-500">Domain: {g.domain}</span>
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
                      </div>
                      {g.narrative_source && (
                        <p className="mt-1 text-xs text-gray-500 line-clamp-2">
                          {g.narrative_source}
                        </p>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        setGuidelines((prev) => prev.filter((_, j) => j !== i))
                      }
                      className="text-gray-400 hover:text-red-500 transition-colors text-sm flex-shrink-0"
                      title="Remove"
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3">
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={() => router.back()}
            className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={isSubmitting}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 disabled:opacity-50"
          >
            {isSubmitting ? "Creating…" : "Create Contract"}
          </button>
        </div>
      </form>
    </div>
  );
}
