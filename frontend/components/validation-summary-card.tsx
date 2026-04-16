import type { ValidationSummary } from "@/lib/types";

interface ValidationSummaryCardProps {
  summary: ValidationSummary;
  invoiceStatus?: string;
}

function Money({ value }: { value: string }) {
  return (
    <span>
      ${parseFloat(value).toLocaleString("en-US", { minimumFractionDigits: 2 })}
    </span>
  );
}

const ACTION_OWNER: Record<string, string> = {
  REVIEW_REQUIRED: "Awaiting supplier",
  SUPPLIER_RESPONDED: "Awaiting carrier",
  PENDING_CARRIER_REVIEW: "Awaiting carrier",
  CARRIER_REVIEWING: "Awaiting carrier",
};

export function ValidationSummaryCard({ summary, invoiceStatus }: ValidationSummaryCardProps) {
  const hasInDispute = parseFloat(summary.total_in_dispute) > 0;
  const hasPayable = parseFloat(summary.total_payable) > 0;
  const actionOwner = invoiceStatus ? ACTION_OWNER[invoiceStatus] : null;

  // Hide zero-value stats that add no information
  const showValidated = summary.lines_validated > 0;
  const showPendingReview = summary.lines_pending_review > 0;
  // Hide "Approved to Pay: $0.00" when In Dispute is already showing — it's redundant
  const showApprovedToPay = hasPayable || !hasInDispute;

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
      <Stat label="Total Lines" value={String(summary.total_lines)} />
      {showValidated && (
        <Stat label="Validated" value={String(summary.lines_validated)} />
      )}
      <Stat
        label="Exceptions"
        value={
          summary.lines_with_exceptions > 0 && actionOwner ? (
            <span>
              {summary.lines_with_exceptions}
              <span className="block text-xs font-normal text-gray-400 mt-0.5">
                {actionOwner}
              </span>
            </span>
          ) : (
            String(summary.lines_with_exceptions)
          )
        }
        highlight={summary.lines_with_exceptions > 0}
      />
      {showPendingReview && (
        <Stat label="Pending Review" value={String(summary.lines_pending_review)} />
      )}
      <Stat label="Total Billed" value={<Money value={summary.total_billed} />} />
      {hasInDispute && (
        <Stat
          label="In Dispute"
          value={<Money value={summary.total_in_dispute} />}
          highlight
        />
      )}
      {showApprovedToPay && (
        <Stat
          label="Approved to Pay"
          value={
            hasPayable ? (
              <Money value={summary.total_payable} />
            ) : (
              <span className="text-base font-medium text-gray-400">
                Pending
              </span>
            )
          }
          green={hasPayable}
        />
      )}
      {summary.lines_denied > 0 && (
        <Stat
          label="Denied"
          value={<Money value={summary.total_denied} />}
          highlight
        />
      )}
      {(summary.lines_pending_classification ?? 0) > 0 && (
        <Stat
          label="Pending Classification"
          value={
            <span>
              {summary.lines_pending_classification}
              <span className="block text-xs font-normal text-amber-600 mt-0.5">
                <Money value={summary.total_pending_classification} />
              </span>
            </span>
          }
          amber
        />
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  highlight,
  green,
  amber,
}: {
  label: string;
  value: React.ReactNode;
  highlight?: boolean;
  green?: boolean;
  amber?: boolean;
}) {
  return (
    <div
      className={`rounded-lg border p-4 shadow-sm ${
        amber ? "border-amber-200 bg-amber-50" : "bg-white"
      }`}
    >
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
        {label}
      </p>
      <p
        className={`mt-1 text-2xl font-semibold ${
          highlight
            ? "text-red-600"
            : green
              ? "text-green-600"
              : amber
                ? "text-amber-700"
                : "text-gray-900"
        }`}
      >
        {value}
      </p>
    </div>
  );
}
