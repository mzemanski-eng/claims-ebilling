/**
 * MetricCard — reusable KPI card for the analytics dashboard.
 *
 * Renders a large bold value with a small uppercase label above it,
 * an optional sublabel below, and a coloured top-border accent.
 */

interface MetricCardProps {
  label: string;
  value: string;
  sublabel?: string;
  accent?: "blue" | "green" | "amber" | "red" | "gray";
}

const ACCENT_BORDER: Record<string, string> = {
  blue:  "border-t-blue-500",
  green: "border-t-green-500",
  amber: "border-t-amber-500",
  red:   "border-t-red-500",
  gray:  "border-t-gray-400",
};

export function MetricCard({
  label,
  value,
  sublabel,
  accent = "blue",
}: MetricCardProps) {
  return (
    <div
      className={`rounded-xl border border-t-4 bg-white p-5 shadow-sm ${ACCENT_BORDER[accent]}`}
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
        {label}
      </p>
      <p className="mt-2 text-3xl font-bold text-gray-900 tabular-nums">
        {value}
      </p>
      {sublabel && (
        <p className="mt-1 text-xs text-gray-400">{sublabel}</p>
      )}
    </div>
  );
}
