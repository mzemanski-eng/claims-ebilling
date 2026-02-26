"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { createInvoice, uploadInvoiceFile, listSupplierContracts } from "@/lib/api";
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

  // Load supplier's contracts via the supplier-scoped endpoint
  const { data: contracts } = useQuery({
    queryKey: ["supplier-contracts"],
    queryFn: listSupplierContracts,
  });

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
        {step === 1 && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              createMutation.mutate();
            }}
            className="space-y-5"
          >
            <h2 className="text-lg font-semibold text-gray-900">
              Invoice details
            </h2>

            {stepError && (
              <div className="rounded-md bg-red-50 border border-red-200 px-4 py-3">
                <p className="text-sm text-red-700">{stepError}</p>
              </div>
            )}

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

            <div className="flex flex-col gap-1">
              <label
                htmlFor="contract"
                className="text-sm font-medium text-gray-700"
              >
                Contract
              </label>
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
                    {c.name} (eff. {c.effective_from})
                  </option>
                ))}
              </select>
            </div>

            <Input
              id="notes"
              label="Notes (optional)"
              placeholder="Any submission notes…"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />

            <div className="flex justify-end gap-3 pt-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => router.back()}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                loading={createMutation.isPending}
                disabled={!invoiceNumber || !invoiceDate || !contractId}
              >
                Continue →
              </Button>
            </div>
          </form>
        )}

        {step === 2 && (
          <div className="space-y-5">
            <h2 className="text-lg font-semibold text-gray-900">
              Upload invoice file
            </h2>
            <p className="text-sm text-gray-500">
              Accepted formats: CSV. The pipeline will process your file
              automatically.
            </p>

            {stepError && (
              <div className="rounded-md bg-red-50 border border-red-200 px-4 py-3">
                <p className="text-sm text-red-700">{stepError}</p>
              </div>
            )}

            {/* Drop zone */}
            <label
              htmlFor="file-upload"
              className="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 px-6 py-12 hover:border-blue-400 hover:bg-blue-50 transition-colors"
            >
              <svg
                className="mb-3 h-10 w-10 text-gray-400"
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
              <span className="text-sm font-medium text-gray-700">
                {file ? file.name : "Choose a file or drag & drop"}
              </span>
              <span className="mt-1 text-xs text-gray-400">.csv up to 10 MB</span>
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
                Upload & Process
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
      <span
        className={`text-sm font-medium ${active ? "text-gray-900" : "text-gray-400"}`}
      >
        {label}
      </span>
    </div>
  );
}
