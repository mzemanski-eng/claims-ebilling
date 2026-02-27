"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { getSupplierInvoice, resubmitInvoice } from "@/lib/api";
import { Button } from "@/components/ui/button";

export default function ResubmitInvoicePage({
  params,
}: {
  params: { id: string };
}) {
  const { id } = params;
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const { data: invoice, isLoading } = useQuery({
    queryKey: ["supplier-invoice", id],
    queryFn: () => getSupplierInvoice(id),
  });

  const mutation = useMutation({
    mutationFn: () => resubmitInvoice(id, file!),
    onSuccess: () => {
      router.push(`/supplier/invoices/${id}`);
    },
    onError: (err: Error) => setSubmitError(err.message),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
      </div>
    );
  }

  if (!invoice) {
    return <p className="text-red-600">Invoice not found.</p>;
  }

  // Guard: only allow resubmission when invoice is in REVIEW_REQUIRED
  if (invoice.status !== "REVIEW_REQUIRED") {
    return (
      <div className="mx-auto max-w-xl space-y-4">
        <div className="text-sm text-gray-500">
          <Link href="/supplier/invoices" className="hover:text-blue-600">
            My Invoices
          </Link>
          <span className="mx-2">›</span>
          <Link
            href={`/supplier/invoices/${id}`}
            className="hover:text-blue-600"
          >
            {invoice.invoice_number}
          </Link>
          <span className="mx-2">›</span>
          <span className="text-gray-900 font-medium">Resubmit</span>
        </div>
        <div className="rounded-lg border border-gray-200 bg-white px-6 py-10 shadow-sm text-center">
          <p className="text-gray-600">
            This invoice is not currently awaiting resubmission.
          </p>
          <p className="mt-1 text-sm text-gray-400">
            Current status:{" "}
            <span className="font-medium">
              {invoice.status.replace(/_/g, " ")}
            </span>
          </p>
          <Link href={`/supplier/invoices/${id}`}>
            <Button variant="secondary" className="mt-5">
              ← Back to invoice
            </Button>
          </Link>
        </div>
      </div>
    );
  }

  const exceptionCount =
    invoice.validation_summary?.lines_with_exceptions ?? 0;

  return (
    <div className="mx-auto max-w-xl space-y-6">
      {/* Breadcrumb */}
      <div className="text-sm text-gray-500">
        <Link href="/supplier/invoices" className="hover:text-blue-600">
          My Invoices
        </Link>
        <span className="mx-2">›</span>
        <Link
          href={`/supplier/invoices/${id}`}
          className="hover:text-blue-600"
        >
          {invoice.invoice_number}
        </Link>
        <span className="mx-2">›</span>
        <span className="text-gray-900 font-medium">Resubmit</span>
      </div>

      {/* Context card */}
      <div className="rounded-lg border border-orange-200 bg-orange-50 px-5 py-4">
        <h1 className="text-base font-semibold text-orange-900">
          Resubmit invoice {invoice.invoice_number}
        </h1>
        <p className="mt-1 text-sm text-orange-700">
          Version {invoice.current_version} was flagged with{" "}
          <strong>
            {exceptionCount} {exceptionCount === 1 ? "exception" : "exceptions"}
          </strong>
          . Upload a corrected CSV file to address them. The version number will
          increment automatically.
        </p>
        <Link
          href={`/supplier/invoices/${id}`}
          className="mt-2 inline-block text-xs font-medium text-orange-700 underline underline-offset-2 hover:text-orange-900"
        >
          ← Review exceptions before resubmitting
        </Link>
      </div>

      {/* Upload card */}
      <div className="rounded-xl border bg-white px-8 py-8 shadow-sm space-y-5">
        <h2 className="text-lg font-semibold text-gray-900">
          Upload corrected invoice file
        </h2>
        <p className="text-sm text-gray-500">
          Accepted format: CSV. Make sure you have addressed all flagged
          exceptions before uploading.
        </p>

        {submitError && (
          <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3">
            <p className="text-sm text-red-700">{submitError}</p>
          </div>
        )}

        {/* Drop zone */}
        <label
          htmlFor="resubmit-file"
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
            id="resubmit-file"
            type="file"
            accept=".csv"
            className="sr-only"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setSubmitError(null);
            }}
          />
        </label>

        <div className="flex justify-end gap-3 pt-2">
          <Link href={`/supplier/invoices/${id}`}>
            <Button type="button" variant="ghost">
              Cancel
            </Button>
          </Link>
          <Button
            onClick={() => mutation.mutate()}
            loading={mutation.isPending}
            disabled={!file || mutation.isPending}
          >
            Resubmit Invoice
          </Button>
        </div>
      </div>
    </div>
  );
}
