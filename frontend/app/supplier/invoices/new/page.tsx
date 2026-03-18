"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { createInvoice, listSupplierContracts, uploadInvoiceFile } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function NewInvoicePage() {
  const router = useRouter();

  // Step 1: form fields
  const [invoiceNumber, setInvoiceNumber] = useState("");
  const [invoiceDate, setInvoiceDate] = useState(
    new Date().toISOString().split("T")[0],
  );
  const [contractId, setContractId] = useState("");
  const [notes, setNotes] = useState("");

  // Step 2: file upload
  const [createdInvoiceId, setCreatedInvoiceId] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [stepError, setStepError] = useState<string | null>(null);

  // Load supplier's active contracts
  const { data: contracts, isLoading: contractsLoading } = useQuery({
    queryKey: ["supplier-contracts"],
    queryFn: listSupplierContracts,
  });

  // Auto-select when only one active contract exists
  useEffect(() => {
    if (contracts?.length === 1 && !contractId) {
      setContractId(contracts[0].id);
    }
  }, [contracts, contractId]);

  const selectedContract = contracts?.find((c) => c.id === contractId);
  const singleContract = contracts?.length === 1;

  const createMutation = useMutation({
    mutationFn: () =>
      createInvoice({
        contract_id: contractId,
        invoice_number: invoiceNumber,
        invoice_date: invoiceDate,
        submission_notes: notes || undefined,
      }),
    onSuccess: (invoice) => {
      setCreatedInvoiceId(invoice.id);
      setStepError(null);
    },
    onError: (err: Error) => setStepError(err.message),
  });

  const uploadMutation = useMutation({
    mutationFn: () => uploadInvoiceFile(createdInvoiceId!, file!),
    onSuccess: () => {
      router.push(`/supplier/invoices/${createdInvoiceId}`);
    },
    onError: (err: Error) => setStepError(err.message),
  });

  const step = createdInvoiceId ? 2 : 1;

  return (
    <div className="mx-auto max-w-xl">
      {/* Stepper */}
      <div className="mb-8 flex items-center gap-4">
        <Step num={1} label="Invoice details" active={step === 1} done={step > 1} />
        <div className="h-px flex-1 bg-gray-200" />
        <Step num={2} label="Upload file" active={step === 2} done={false} />
      </div>

      <div className="rounded-xl border bg-white px-8 py-8 shadow-sm">
        {/* ── Step 1: Details ─────────────────────────────────────────────── */}
        {step === 1 && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              createMutation.mutate();
            }}
            className="space-y-5"
          >
            <h2 className="text-lg font-semibold text-gray-900">Invoice details</h2>

            {stepError && (
              <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3">
                <p className="text-sm text-red-700">{stepError}</p>
              </div>
            )}

            {/* Contract — auto-selected pill (single) or dropdown (multiple) */}
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">
                Contract
              </label>

              {contractsLoading ? (
                <div className="h-9 animate-pulse rounded-md bg-gray-100" />
              ) : contracts?.length === 0 ? (
                <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                  No active contracts found. Contact your carrier to set up a contract before submitting invoices.
                </div>
              ) : singleContract ? (
                /* Single contract — show as a read-only info card, no selection needed */
                <div className="flex items-center gap-3 rounded-lg border border-gray-200 bg-gray-50 px-4 py-2.5">
                  <div className="h-2 w-2 rounded-full bg-green-500 shrink-0" />
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-gray-900">
                      {selectedContract?.name}
                    </p>
                    <p className="text-xs text-gray-500">
                      Effective {selectedContract?.effective_from}
                      {selectedContract?.effective_to
                        ? ` → ${selectedContract.effective_to}`
                        : " · No expiry"}
                    </p>
                  </div>
                  <span className="ml-auto shrink-0 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                    Active
                  </span>
                </div>
              ) : (
                /* Multiple contracts — dropdown */
                <select
                  id="contract"
                  required
                  value={contractId}
                  onChange={(e) => setContractId(e.target.value)}
                  className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                >
                  <option value="">Select a contract…</option>
                  {contracts?.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                      {c.effective_to
                        ? ` (${c.effective_from} – ${c.effective_to})`
                        : ` (eff. ${c.effective_from})`}
                    </option>
                  ))}
                </select>
              )}
            </div>

            <Input
              id="invoice-number"
              label="Invoice number"
              placeholder="INV-2025-001"
              required
              value={invoiceNumber}
              onChange={(e) => setInvoiceNumber(e.target.value)}
            />

            <Input
              id="invoice-date"
              label="Invoice date"
              type="date"
              required
              value={invoiceDate}
              onChange={(e) => setInvoiceDate(e.target.value)}
            />

            <Input
              id="notes"
              label="Notes (optional)"
              placeholder="Any submission notes…"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />

            <div className="flex justify-end gap-3 pt-2">
              <Button type="button" variant="ghost" onClick={() => router.back()}>
                Cancel
              </Button>
              <Button
                type="submit"
                loading={createMutation.isPending}
                disabled={
                  !invoiceNumber ||
                  !invoiceDate ||
                  !contractId ||
                  contracts?.length === 0 ||
                  createMutation.isPending
                }
              >
                Continue →
              </Button>
            </div>
          </form>
        )}

        {/* ── Step 2: Upload ───────────────────────────────────────────────── */}
        {step === 2 && (
          <div className="space-y-5">
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Upload invoice file</h2>
              <p className="mt-1 text-sm text-gray-500">
                Upload your CSV. The system will classify each line, validate
                rates against your contract, and flag any exceptions for review.
              </p>
            </div>

            {stepError && (
              <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3">
                <p className="text-sm text-red-700">{stepError}</p>
              </div>
            )}

            {/* Drop zone */}
            <label
              htmlFor="file-upload"
              className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-12 transition-colors ${
                file
                  ? "border-blue-400 bg-blue-50"
                  : "border-gray-300 bg-gray-50 hover:border-blue-400 hover:bg-blue-50"
              }`}
            >
              <svg
                className={`mb-3 h-10 w-10 ${file ? "text-blue-500" : "text-gray-400"}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                />
              </svg>
              {file ? (
                <div className="text-center">
                  <p className="text-sm font-medium text-blue-700">{file.name}</p>
                  <p className="mt-0.5 text-xs text-blue-500">
                    {(file.size / 1024).toFixed(1)} KB · Click to change
                  </p>
                </div>
              ) : (
                <div className="text-center">
                  <p className="text-sm font-medium text-gray-700">
                    Choose a file or drag &amp; drop
                  </p>
                  <p className="mt-0.5 text-xs text-gray-400">.csv up to 10 MB</p>
                </div>
              )}
              <input
                id="file-upload"
                type="file"
                accept=".csv"
                className="sr-only"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>

            <div className="flex justify-end gap-3 pt-2">
              <Button
                variant="ghost"
                onClick={() => {
                  setCreatedInvoiceId(null);
                  setFile(null);
                  setStepError(null);
                }}
              >
                ← Back
              </Button>
              <Button
                loading={uploadMutation.isPending}
                disabled={!file || uploadMutation.isPending}
                onClick={() => uploadMutation.mutate()}
              >
                Upload &amp; Process
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Step({
  num,
  label,
  active,
  done,
}: {
  num: number;
  label: string;
  active: boolean;
  done: boolean;
}) {
  return (
    <div className="flex items-center gap-2">
      <div
        className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-bold ${
          done
            ? "bg-green-500 text-white"
            : active
              ? "bg-blue-600 text-white"
              : "bg-gray-200 text-gray-500"
        }`}
      >
        {done ? "✓" : num}
      </div>
      <span className={`text-sm font-medium ${active ? "text-gray-900" : "text-gray-400"}`}>
        {label}
      </span>
    </div>
  );
}
