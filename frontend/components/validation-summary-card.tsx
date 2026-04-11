import type { ValidationSummary } from "@/lib/types";

interface ValidationSummaryCardProps {
  summary: ValidationSummary;
}

function Money({ value }: { value: string }) {
  return (
    <span>
      ${parseFloat(value).toLocaleString("en-US", { minimumFractionDigits: 2 })}
    </span>
  );
}

export function ValidationSummaryCard({ summary }: ValidationSummaryCardProps) {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
      <Stat label="Total Lines" value={String(summary.total_lines)} />
      <Stat label="Validated" value={String(summary.lines_validated)} />
      <Stat
        label="Exceptions"
        value={String(summary.lines_with_exceptions)}
        highlight={summary.lines_with_exceptions > 0}
      />
      <Stat label="Pending Review" value={String(summary.lines_pending_review)} />
      <Stat label="Total Billed" value={<Money value={summary.total_billed} />} />
      <Stat
        label="Approved to Pay"
        value={
          summary.lines_with_spend_exceptions > 0 &&
          parseFloat(summary.total_payable) === 0 ? (
            <span className="text-base font-medium text-gray-400">Pending</span>
          ) : (
            <Money value={summary.total_payable} />
          )
        }
        green={parseFloat(summary.total_payable) > 0}
      />
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
          value={<Money value={summary.total_pending_classification} />}
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
