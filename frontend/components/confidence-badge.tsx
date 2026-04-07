const CONFIDENCE_STYLES: Record<string, string> = {
  HIGH:   "bg-green-100 text-green-700",
  MEDIUM: "bg-yellow-100 text-yellow-700",
  LOW:    "bg-red-100 text-red-700",
};

const CONFIDENCE_LABELS: Record<string, string> = {
  HIGH:   "High — AI is confident in this classification",
  MEDIUM: "Medium — AI has moderate confidence; verify if unsure",
  LOW:    "Low — AI is uncertain; manual review recommended",
};

interface ConfidenceBadgeProps {
  confidence: string | null | undefined;
}

export function ConfidenceBadge({ confidence }: ConfidenceBadgeProps) {
  if (!confidence) return <span className="text-gray-400 text-xs">—</span>;
  const style = CONFIDENCE_STYLES[confidence] ?? "bg-gray-100 text-gray-600";
  return (
    <span
      title={CONFIDENCE_LABELS[confidence] ?? `AI match confidence: ${confidence}`}
      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium cursor-help ${style}`}
    >
      {confidence}
    </span>
  );
}
