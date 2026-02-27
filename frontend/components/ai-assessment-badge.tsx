/**
 * AiAssessmentBadge
 *
 * Displays the AI description alignment score for a line item.
 * Shows a colored pill (ALIGNED=green, PARTIAL=amber, MISALIGNED=red)
 * with a tooltip containing the one-sentence rationale.
 *
 * Renders nothing when assessment is null (API key not set / call failed).
 */

import type { AiDescriptionAssessment } from "@/lib/types";

interface AiAssessmentBadgeProps {
  assessment: AiDescriptionAssessment | null | undefined;
  /** If true, also show the rationale text below the badge */
  showRationale?: boolean;
}

const SCORE_CONFIG = {
  ALIGNED: {
    dot: "bg-green-500",
    pill: "border-green-200 bg-green-50 text-green-800",
    label: "Aligned",
    icon: "✓",
  },
  PARTIAL: {
    dot: "bg-amber-400",
    pill: "border-amber-200 bg-amber-50 text-amber-800",
    label: "Partial",
    icon: "~",
  },
  MISALIGNED: {
    dot: "bg-red-500",
    pill: "border-red-200 bg-red-50 text-red-800",
    label: "Misaligned",
    icon: "!",
  },
} as const;

export function AiAssessmentBadge({
  assessment,
  showRationale = false,
}: AiAssessmentBadgeProps) {
  if (!assessment) return null;

  const config = SCORE_CONFIG[assessment.score] ?? SCORE_CONFIG.PARTIAL;

  return (
    <div className="flex flex-col gap-1">
      <span
        className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${config.pill}`}
        title={assessment.rationale}
      >
        <span
          className={`inline-block h-1.5 w-1.5 rounded-full ${config.dot}`}
        />
        {config.label}
      </span>
      {showRationale && assessment.rationale && (
        <p className="text-xs text-gray-500 leading-snug max-w-xs">
          {assessment.rationale}
        </p>
      )}
    </div>
  );
}

/**
 * Inline version for table cells — just the dot + label, no rationale text.
 * Rationale is visible on hover via the title attribute.
 */
export function AiAssessmentInline({
  assessment,
}: {
  assessment: AiDescriptionAssessment | null | undefined;
}) {
  if (!assessment) {
    return <span className="text-gray-300 text-xs">—</span>;
  }
  return <AiAssessmentBadge assessment={assessment} showRationale={false} />;
}
