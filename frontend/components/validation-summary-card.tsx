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
      <Stat label="Payable" value={<Money value={summary.total_payable} />} green />
      {summary.lines_denied > 0 && (
        <Stat
          label="Denied"
          value={<Money value={summary.total_denied} />}
          highlight
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
}: {
  label: string;
  value: React.ReactNode;
  highlight?: boolean;
  green?: boolean;
}) {
  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
        {label}
      </p>
      <p
        className={`mt-1 text-2xl font-semibold ${
          highlight
            ? "text-red-600"
            : green
              ? "text-green-600"
              : "text-gray-900"
        }`}
      >
        {value}
      </p>
    </div>
  );
}
