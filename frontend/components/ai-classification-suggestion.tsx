/**
 * AiClassificationSuggestion
 *
 * Displays Claude's assessment of an UNRECOGNIZED invoice line item.
 * Three visual variants:
 *   SUGGESTED    — indigo card with code label, confidence chip, rationale,
 *                  and optional "Accept Suggestion" / "Accept & Save" buttons.
 *   TAXONOMY_GAP — amber banner indicating a coverage gap.
 *   OUT_OF_SCOPE — red banner indicating a non-billable charge.
 *
 * When `onAccept` is provided (admin mappings queue), SUGGESTED renders an
 * "Accept Suggestion" button that pre-fills the OverrideForm.
 * When `onAcceptAndSave` is also provided and confidence is HIGH, a primary
 * "✓ Accept & Save" button is shown instead — saving in one click without
 * opening the form (defaults scope to "this_supplier").
 * If neither prop is provided (invoice detail page) the component is
 * informational only.
 */

import { TAXONOMY_OPTIONS } from "@/lib/taxonomy";
import type { AiClassificationSuggestion as Suggestion } from "@/lib/types";

// Derived from the canonical TAXONOMY_OPTIONS list — always in sync with backend.
const TAXONOMY_LABELS: Record<string, string> = Object.fromEntries(
  TAXONOMY_OPTIONS.map((t) => [t.code, t.label]),
);

const CONFIDENCE_STYLES: Record<
  string,
  { bg: string; text: string; label: string }
> = {
  HIGH:   { bg: "bg-green-100",  text: "text-green-800",  label: "High confidence" },
  MEDIUM: { bg: "bg-yellow-100", text: "text-yellow-800", label: "Medium confidence" },
  LOW:    { bg: "bg-red-100",    text: "text-red-800",    label: "Low confidence" },
};

interface Props {
  suggestion: Suggestion | null;
  /** If provided, renders "Accept Suggestion" button on SUGGESTED cards (pre-fills form). */
  onAccept?: (code: string, billingComponent: string) => void;
  /**
   * If provided alongside onAccept, renders a primary "✓ Accept & Save" button
   * for HIGH confidence suggestions — saves immediately without opening the form.
   * The caller is responsible for calling overrideMapping with scope "this_supplier".
   */
  onAcceptAndSave?: (code: string, billingComponent: string) => void;
  /** True while an onAcceptAndSave mutation is in-flight. */
  isSaving?: boolean;
}

export function AiClassificationSuggestion({
  suggestion,
  onAccept,
  onAcceptAndSave,
  isSaving,
}: Props) {
  if (!suggestion) return null;

  const { verdict, suggested_code, suggested_billing_component, confidence, rationale } =
    suggestion;

  // ── SUGGESTED ─────────────────────────────────────────────────────────────
  if (verdict === "SUGGESTED" && suggested_code) {
    const label = TAXONOMY_LABELS[suggested_code] ?? suggested_code;
    const conf = confidence ? CONFIDENCE_STYLES[confidence] : null;
    const canOneClick =
      confidence === "HIGH" && onAcceptAndSave && suggested_billing_component;

    return (
      <div className="mt-3 rounded-lg border border-indigo-200 bg-indigo-50 p-3">
        <div className="flex items-start gap-2">
          {/* Sparkle icon */}
          <span className="mt-0.5 flex-shrink-0 text-indigo-400 text-base">✦</span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-semibold text-indigo-700">
                AI Suggestion
              </span>
              {conf && (
                <span
                  className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${conf.bg} ${conf.text}`}
                >
                  {conf.label}
                </span>
              )}
            </div>
            <p className="mt-1 font-mono text-xs text-indigo-900">{suggested_code}</p>
            <p className="text-xs text-indigo-700 leading-snug">{label}</p>
            {rationale && (
              <p className="mt-1 text-xs italic text-indigo-500">{rationale}</p>
            )}
            {/* Action buttons — only rendered in the mappings queue (when onAccept is set) */}
            {onAccept && suggested_billing_component && (
              <div className="mt-2 flex items-center gap-2 flex-wrap">
                {/* One-click save — only shown for HIGH confidence */}
                {canOneClick && (
                  <button
                    disabled={isSaving}
                    onClick={() =>
                      onAcceptAndSave(suggested_code, suggested_billing_component)
                    }
                    className="rounded bg-indigo-600 px-3 py-1 text-xs font-semibold text-white hover:bg-indigo-700 transition-colors disabled:opacity-50"
                  >
                    {isSaving ? "Saving…" : "✓ Accept & Save"}
                  </button>
                )}
                {/* Always show the manual override option */}
                <button
                  onClick={() => onAccept(suggested_code, suggested_billing_component)}
                  className="rounded border border-indigo-300 bg-white px-3 py-1 text-xs font-semibold text-indigo-700 hover:bg-indigo-50 transition-colors"
                >
                  {canOneClick ? "Review first…" : "Accept Suggestion"}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ── TAXONOMY_GAP ──────────────────────────────────────────────────────────
  if (verdict === "TAXONOMY_GAP") {
    return (
      <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
        <div className="flex items-start gap-2">
          <span className="mt-0.5 flex-shrink-0 text-amber-500 text-sm">⚠</span>
          <div>
            <p className="text-xs font-semibold text-amber-800">
              AI: Taxonomy gap
            </p>
            <p className="text-xs text-amber-700 leading-snug">
              This appears to be a legitimate billable service, but no existing
              taxonomy code covers it. Consider adding a new code.
            </p>
            {rationale && (
              <p className="mt-1 text-xs italic text-amber-600">{rationale}</p>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ── OUT_OF_SCOPE ──────────────────────────────────────────────────────────
  if (verdict === "OUT_OF_SCOPE") {
    return (
      <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2">
        <div className="flex items-start gap-2">
          <span className="mt-0.5 flex-shrink-0 text-red-500 text-sm">✕</span>
          <div>
            <p className="text-xs font-semibold text-red-800">
              AI: Out of scope
            </p>
            <p className="text-xs text-red-700 leading-snug">
              This charge does not appear to be a legitimate billable service.
            </p>
            {rationale && (
              <p className="mt-1 text-xs italic text-red-600">{rationale}</p>
            )}
          </div>
        </div>
      </div>
    );
  }

  return null;
}
