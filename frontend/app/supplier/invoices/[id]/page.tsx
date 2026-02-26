"use client";

import { use } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { getSupplierInvoice, getSupplierInvoiceLines } from "@/lib/api";
import { StatusBadge } from "@/components/status-badge";
import { ValidationSummaryCard } from "@/components/validation-summary-card";
import { SupplierExceptionPanel } from "@/components/exception-panel";

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default function SupplierInvoiceDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  const { data: invoice, isLoading: invLoading } = useQuery({
    queryKey: ["supplier-invoice", id],
    queryFn: () => getSupplierInvoice(id),
  });

  const { data: lines, isLoading: linesLoading } = useQuery({
    queryKey: ["supplier-lines", id],
    queryFn: () => getSupplierInvoiceLines(id),
    enabled: !!invoice,
  });

  if (invLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
      </div>
    );
  }

  if (!invoice) {
    return <p className="text-red-600">Invoice not found.</p>;
  }

  const hasExceptions = invoice.validation_summary
    ? invoice.validation_summary.lines_with_exceptions > 0
    : false;

  return (
    <div className="space-y-8">
      {/* Breadcrumb */}
      <div className="text-sm text-gray-500">
        <Link href="/supplier/invoices" className="hover:text-blue-600">
          My Invoices
        </Link>
        <span className="mx-2">›</span>
        <span className="text-gray-900 font-medium">
          {invoice.invoice_number}
        </span>
      </div>

      {/* Invoice header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {invoice.invoice_number}
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            Invoice date: {formatDate(invoice.invoice_date)} · Version{" "}
            {invoice.current_version}
          </p>
          {invoice.submission_notes && (
            <p className="mt-1 text-sm text-gray-500 italic">
              Notes: {invoice.submission_notes}
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          <StatusBadge status={invoice.status} className="text-sm px-3 py-1" />
          {invoice.status === "REVIEW_REQUIRED" && (
            <Link
              href={`/supplier/invoices/new`}
              className="rounded-md bg-orange-100 px-3 py-1.5 text-sm font-medium text-orange-700 hover:bg-orange-200"
            >
              Resubmit →
            </Link>
          )}
        </div>
      </div>

      {/* Validation summary */}
      {invoice.validation_summary && (
        <div>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Validation Summary
          </h2>
          <ValidationSummaryCard summary={invoice.validation_summary} />
        </div>
      )}

      {/* Exception notice */}
      {hasExceptions && invoice.status === "REVIEW_REQUIRED" && (
        <div className="rounded-lg border border-orange-200 bg-orange-50 px-4 py-3">
          <p className="text-sm font-medium text-orange-800">
            Action required: please respond to the exceptions below before
            resubmitting.
          </p>
        </div>
      )}

      {/* Line items */}
      {linesLoading && (
        <div className="flex items-center justify-center py-10">
          <div className="h-6 w-6 animate-spin rounded-full border-4 border-blue-400 border-t-transparent" />
        </div>
      )}

      {lines && (
        <div>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Line Items
          </h2>
          <div className="overflow-hidden rounded-xl border bg-white shadow-sm">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left font-semibold text-gray-600">
                    #
                  </th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-600">
                    Description
                  </th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-600">
                    Claim
                  </th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-600">
                    Date
                  </th>
                  <th className="px-4 py-3 text-right font-semibold text-gray-600">
                    Billed
                  </th>
                  <th className="px-4 py-3 text-right font-semibold text-gray-600">
                    Expected
                  </th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-600">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {lines.map((li) => {
                  const openExcs = li.exceptions.filter(
                    (e) => e.status === "OPEN",
                  );
                  return (
                    <>
                      <tr
                        key={li.id}
                        className={
                          openExcs.length > 0 ? "bg-red-50" : "hover:bg-gray-50"
                        }
                      >
                        <td className="px-4 py-3 text-gray-500">
                          {li.line_number}
                        </td>
                        <td className="px-4 py-3 max-w-xs text-gray-900">
                          <span
                            className="block truncate"
                            title={li.raw_description}
                          >
                            {li.raw_description}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-gray-500 text-xs">
                          {li.claim_number ?? "—"}
                        </td>
                        <td className="px-4 py-3 text-gray-500 text-xs">
                          {formatDate(li.service_date)}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-gray-900">
                          ${parseFloat(li.raw_amount).toFixed(2)}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-gray-500">
                          {li.expected_amount
                            ? `$${parseFloat(li.expected_amount).toFixed(2)}`
                            : "—"}
                        </td>
                        <td className="px-4 py-3">
                          <StatusBadge status={li.status} />
                        </td>
                      </tr>

                      {/* Exceptions inline below the row */}
                      {li.exceptions.length > 0 && (
                        <tr key={`${li.id}-exc`}>
                          <td colSpan={7} className="px-6 pb-4 pt-0">
                            <SupplierExceptionPanel
                              exceptions={li.exceptions}
                              invoiceId={id}
                            />
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
