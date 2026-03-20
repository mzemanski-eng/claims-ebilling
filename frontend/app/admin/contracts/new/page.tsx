"use client";

import { Suspense, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  createAdminContract,
  createGuideline,
  createRateCard,
  listAdminSuppliers,
  parseContractPdf,
} from "@/lib/api";
import type { GuidelineCreate, RateCardCreate } from "@/lib/types";
import { DOMAIN_LABELS, TAXONOMY_DOMAINS, TAXONOMY_OPTIONS } from "@/lib/taxonomy";

// ── Types ──────────────────────────────────────────────────────────────────────

interface RateCardRow extends RateCardCreate {
  _key: number;
}

interface GuidelineRow extends GuidelineCreate {
  _key: number;
}

// ── Page (inner — uses useSearchParams) ───────────────────────────────────────

function NewContractContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const fileInputRef = useRef<HTMLInputElement>(null);
  let _nextKey = 0;
  const nextKey = () => ++_nextKey;

  // ── Form state ──────────────────────────────────────────────────────────────
  // Pre-select supplier if navigated from Suppliers page via ?supplier_id=
  const [supplierId, setSupplierId] = useState(searchParams.get("supplier_id") ?? "");
  const [name, setName] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [effectiveTo, setEffectiveTo] = useState("");
  const [geographyScope, setGeographyScope] = useState("national");
  const [notes, setNotes] = useState("");

  // ── AI extraction state ─────────────────────────────────────────────────────
  const [isParsing, setIsParsing] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const [uploadedFilename, setUploadedFilename] = useState<string | null>(null);
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

  // ── PDF Upload handlers ──────────────────────────────────────────────────────
  async function processPdfFile(file: File) {
    if (!supplierId) {
      setError("Please select a supplier before uploading a PDF.");
      return;
    }
    setError(null);
    setIsParsing(true);
    setUploadedFilename(file.name);
    try {
      const result = await parseContractPdf(supplierId, file);
      // Pre-fill form fields
      if (result.contract.name) setName(result.contract.name);
      if (result.contract.effective_from) setEffectiveFrom(result.contract.effective_from);
      if (result.contract.effective_to) setEffectiveTo(result.contract.effective_to ?? "");
      if (result.contract.geography_scope) setGeographyScope(result.contract.geography_scope);
      if (result.contract.notes) setNotes(result.contract.notes ?? "");
      // Load extracted rate cards and guidelines
      setRateCards(result.rate_cards.map((rc) => ({ ...rc, _key: nextKey() })));
      setGuidelines(result.guidelines.map((g) => ({ ...g, _key: nextKey() })));
      setExtractionNotes(result.extraction_notes);
    } catch (err) {
      setError(err instanceof Error ? err.message : "PDF parsing failed");
      setUploadedFilename(null);
    } finally {
      setIsParsing(false);
      // Reset file input so same file can be re-uploaded
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handlePdfUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    await processPdfFile(file);
  }

  function handleDragOver(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  }

  function handleDragLeave(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }

  async function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    if (file.type !== "application/pdf") {
      setError("Please drop a PDF file.");
      return;
    }
    await processPdfFile(file);
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
          <h2 className="text-base font-semibold text-gray-900">Contract Details</h2>

          {/* Drop zone */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            className="hidden"
            onChange={handlePdfUpload}
          />
          <div
            onClick={() => !isParsing && fileInputRef.current?.click()}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={`flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors ${
              isParsing
                ? "border-blue-300 bg-blue-50 cursor-default"
                : uploadedFilename
                ? "border-green-300 bg-green-50 cursor-pointer"
                : isDragOver
                ? "border-blue-400 bg-blue-50 cursor-copy"
                : "border-gray-200 bg-gray-50 cursor-pointer hover:border-blue-300 hover:bg-blue-50"
            }`}
          >
            {isParsing ? (
              <>
                <span className="h-6 w-6 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
                <p className="text-sm font-medium text-blue-700">Reading contract with AI…</p>
                <p className="text-xs text-blue-400">This may take a moment</p>
              </>
            ) : uploadedFilename ? (
              <>
                <span className="text-2xl">✅</span>
                <p className="text-sm font-medium text-green-700">{uploadedFilename}</p>
                <p className="text-xs text-green-600">Contract extracted — review the fields below</p>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
                  className="mt-1 text-xs text-gray-400 hover:text-gray-600 underline"
                >
                  Upload a different file
                </button>
              </>
            ) : isDragOver ? (
              <>
                <span className="text-3xl">📄</span>
                <p className="text-sm font-medium text-blue-700">Drop to upload</p>
              </>
            ) : (
              <>
                <span className="text-3xl">📄</span>
                <p className="text-sm font-medium text-gray-700">Drop your PDF contract here</p>
                <p className="text-xs text-gray-400">
                  or <span className="text-blue-600 underline">click to browse</span> · PDF files only
                </p>
              </>
            )}
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

// ── Suspense shell (required for useSearchParams in Next.js 14) ───────────────

export default function NewContractPage() {
  return (
    <Suspense fallback={
      <div className="flex items-center justify-center py-16">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
      </div>
    }>
      <NewContractContent />
    </Suspense>
  );
}
