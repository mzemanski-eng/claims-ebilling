import type { ValidationSummary } from "@/lib/types";

interface ValidationSummaryCardProps {
  summary: ValidationSummary;
  invoiceStatus?: string;
}

function formatMoney(value: string): string {
  return `$${parseFloat(value).toLocaleString("en-US", { minimumFractionDigits: 2 })}`;
}

const SUPPLIER_OWNED_STATUSES = new Set([
  "REVIEW_REQUIRED",
]);

export function ValidationSummaryCard({ summary, invoiceStatus }: ValidationSummaryCardProps) {
  const inDispute = parseFloat(summary.total_in_dispute);
  const payable = parseFloat(summary.total_payable);
  const denied = parseFloat(summary.total_denied);
  const pendingClassDollars = parseFloat(summary.total_pending_classification ?? "0");
  const pendingClassLines = summary.lines_pending_classification ?? 0;

  // ── LINES card breakdown
  const lineParts: string[] = [];
  if (summary.lines_validated > 0) {
    lineParts.push(`${summary.lines_validated} validated`);
  }
  if (summary.lines_with_exceptions > 0) {
    lineParts.push(
      `${summary.lines_with_exceptions} with exception${summary.lines_with_exceptions !== 1 ? "s" : ""}`,
    );
  }
  if (summary.lines_denied > 0) {
    lineParts.push(`${summary.lines_denied} denied`);
  }
  if (pendingClassLines > 0) {
    lineParts.push(`${pendingClassLines} pending classification`);
  }
  if (summary.lines_pending_review > 0) {
    lineParts.push(`${summary.lines_pending_review} pending review`);
  }
  const lineBreakdown = lineParts.length > 0 ? lineParts.join(" · ") : "—";

  // ── PAYMENT STATUS — answers "why hasn't this been paid?"
  // Build a list of all holds blocking payment with $ and owner
  const supplierAction = invoiceStatus
    ? SUPPLIER_OWNED_STATUSES.has(invoiceStatus)
    : false;

  const holds: { label: string; amount: string; owner: string; tone: "red" | "amber" }[] = [];
  if (inDispute > 0) {
    holds.push({
      label: "Disputed",
      amount: summary.total_in_dispute,
      owner: supplierAction ? "Awaiting supplier" : "Awaiting carrier",
      tone: "red",
    });
  }
  if (pendingClassDollars > 0) {
    holds.push({
      label: "Pending classification",
      amount: summary.total_pending_classification,
      owner: "On carrier",
      tone: "amber",
    });
  }
  if (denied > 0) {
    holds.push({
      label: "Denied",
      amount: summary.total_denied,
      owner: "Will not pay",
      tone: "red",
    });
  }

  const isClean = holds.length === 0;
  const paymentTone = isClean && payable > 0 ? "green" : "muted";

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      {/* LINES */}
      <Stat
        label="Lines"
        value={String(summary.total_lines)}
        sub={lineBreakdown}
      />

      {/* BILLED */}
      <Stat
        label="Billed"
        value={formatMoney(summary.total_billed)}
      />

      {/* PAYMENT STATUS — the answer to "why hasn't this been paid?" */}
      <div
        className={`rounded-lg border p-4 shadow-sm ${
          isClean && payable > 0
            ? "border-green-200 bg-green-50"
            : "border-gray-200 bg-white"
        }`}
      >
        <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
          Payment Status
        </p>
        <p
          className={`mt-1 text-2xl font-semibold ${
            paymentTone === "green" ? "text-green-700" : "text-gray-900"
          }`}
        >
          {formatMoney(summary.total_payable)}
          <span className="ml-1 text-xs font-normal text-gray-400">
            approved
          </span>
        </p>
        {isClean && payable > 0 && (
          <p className="mt-1 text-xs font-normal text-green-600">
            Ready for export
          </p>
        )}
        {holds.length > 0 && (
          <ul className="mt-2 space-y-1">
            {holds.map((h) => (
              <li
                key={h.label}
                className="flex items-baseline justify-between gap-2 text-xs"
              >
                <span
                  className={`font-medium ${
                    h.tone === "red" ? "text-red-700" : "text-amber-700"
                  }`}
                >
                  {formatMoney(h.amount)} {h.label.toLowerCase()}
                </span>
                <span className="text-gray-400 whitespace-nowrap">
                  {h.owner}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
        {label}
      </p>
      <p className="mt-1 text-2xl font-semibold text-gray-900">{value}</p>
      {sub && <p className="mt-1 text-xs font-normal text-gray-500">{sub}</p>}
    </div>
  );
}
