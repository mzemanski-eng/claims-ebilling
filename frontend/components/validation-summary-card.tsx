import type { ValidationSummary } from "@/lib/types";

interface ValidationSummaryCardProps {
  summary: ValidationSummary;
  invoiceStatus?: string;
}

function formatMoney(value: string): string {
  return `$${parseFloat(value).toLocaleString("en-US", { minimumFractionDigits: 2 })}`;
}

const ACTION_OWNER: Record<string, string> = {
  REVIEW_REQUIRED: "Awaiting supplier response",
  SUPPLIER_RESPONDED: "Awaiting carrier",
  PENDING_CARRIER_REVIEW: "Awaiting carrier",
  CARRIER_REVIEWING: "Awaiting carrier",
};

export function ValidationSummaryCard({ summary, invoiceStatus }: ValidationSummaryCardProps) {
  const inDispute = parseFloat(summary.total_in_dispute);
  const payable = parseFloat(summary.total_payable);
  const denied = parseFloat(summary.total_denied);
  const pendingClassDollars = parseFloat(summary.total_pending_classification ?? "0");
  const pendingClassLines = summary.lines_pending_classification ?? 0;

  // ── LINES card: build a readable breakdown like
  //    "2 validated · 8 with exceptions · 1 pending classification"
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

  // ── BILLED card sub-text
  const billedSub =
    payable > 0 ? `${formatMoney(summary.total_payable)} approved to pay` : null;

  // ── Third card: adapts to the most pressing financial state.
  //    Priority: In Dispute → Denied → Pending Classification → Approved to Pay
  const actionOwner = invoiceStatus ? ACTION_OWNER[invoiceStatus] : null;

  let thirdCard: React.ReactNode;
  if (inDispute > 0) {
    thirdCard = (
      <Stat
        label="In Dispute"
        value={formatMoney(summary.total_in_dispute)}
        sub={actionOwner ?? `${summary.lines_with_exceptions} flagged line${summary.lines_with_exceptions !== 1 ? "s" : ""}`}
        tone="red"
      />
    );
  } else if (denied > 0) {
    thirdCard = (
      <Stat
        label="Denied"
        value={formatMoney(summary.total_denied)}
        sub={`${summary.lines_denied} line${summary.lines_denied !== 1 ? "s" : ""}`}
        tone="red"
      />
    );
  } else if (pendingClassDollars > 0) {
    thirdCard = (
      <Stat
        label="Pending Classification"
        value={formatMoney(summary.total_pending_classification)}
        sub={`${pendingClassLines} line${pendingClassLines !== 1 ? "s" : ""} awaiting taxonomy`}
        tone="amber"
      />
    );
  } else if (payable > 0) {
    thirdCard = (
      <Stat
        label="Approved to Pay"
        value={formatMoney(summary.total_payable)}
        sub="Ready for export"
        tone="green"
      />
    );
  } else {
    thirdCard = <Stat label="Approved to Pay" value="Pending" sub="No lines validated yet" tone="muted" />;
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      <Stat
        label="Lines"
        value={String(summary.total_lines)}
        sub={lineBreakdown}
      />
      <Stat
        label="Billed"
        value={formatMoney(summary.total_billed)}
        sub={billedSub}
      />
      {thirdCard}
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: "red" | "green" | "amber" | "muted";
}) {
  const borderClass =
    tone === "red"
      ? "border-red-200 bg-red-50"
      : tone === "amber"
        ? "border-amber-200 bg-amber-50"
        : tone === "green"
          ? "border-green-200 bg-green-50"
          : "border-gray-200 bg-white";

  const valueClass =
    tone === "red"
      ? "text-red-700"
      : tone === "amber"
        ? "text-amber-700"
        : tone === "green"
          ? "text-green-700"
          : tone === "muted"
            ? "text-gray-400"
            : "text-gray-900";

  const subClass =
    tone === "red"
      ? "text-red-600"
      : tone === "amber"
        ? "text-amber-600"
        : tone === "green"
          ? "text-green-600"
          : "text-gray-500";

  return (
    <div className={`rounded-lg border p-4 shadow-sm ${borderClass}`}>
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
        {label}
      </p>
      <p className={`mt-1 text-2xl font-semibold ${valueClass}`}>{value}</p>
      {sub && (
        <p className={`mt-1 text-xs font-normal ${subClass}`}>{sub}</p>
      )}
    </div>
  );
}
