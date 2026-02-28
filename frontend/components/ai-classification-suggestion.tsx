/**
 * AiClassificationSuggestion
 *
 * Displays Claude's assessment of an UNRECOGNIZED invoice line item.
 * Three visual variants:
 *   SUGGESTED    — indigo card with code label, confidence chip, rationale,
 *                  and optional "Accept Suggestion" button.
 *   TAXONOMY_GAP — amber banner indicating a coverage gap.
 *   OUT_OF_SCOPE — red banner indicating a non-billable charge.
 *
 * When `onAccept` is provided (admin mappings queue), SUGGESTED renders a
 * button that calls onAccept(code, billingComponent) so the OverrideForm
 * can be pre-filled. If `onAccept` is omitted (invoice detail page) the
 * component is informational only.
 */

import type { AiClassificationSuggestion as Suggestion } from "@/lib/types";

// Human-readable labels for all 48 taxonomy codes.
// Mirrors app/taxonomy/constants.py — keeps frontend self-contained.
const TAXONOMY_LABELS: Record<string, string> = {
  "IME.PHY_EXAM.PROF_FEE": "IME Physician Examination — Professional Fee",
  "IME.PHY_EXAM.TRAVEL_TRANSPORT": "IME Physician Examination — Transportation",
  "IME.PHY_EXAM.TRAVEL_LODGING": "IME Physician Examination — Lodging",
  "IME.PHY_EXAM.TRAVEL_MEALS": "IME Physician Examination — Meals & Per Diem",
  "IME.PHY_EXAM.MILEAGE": "IME Physician Examination — Mileage",
  "IME.MULTI_SPECIALTY.PROF_FEE": "IME Multi-Specialty Panel — Professional Fee",
  "IME.RECORDS_REVIEW.PROF_FEE": "IME Records Review (No Exam) — Professional Fee",
  "IME.ADDENDUM.PROF_FEE": "IME Addendum Report — Professional Fee",
  "IME.PEER_REVIEW.PROF_FEE": "IME Peer Review — Professional Fee",
  "IME.CANCELLATION.CANCEL_FEE": "IME Cancellation Fee",
  "IME.NO_SHOW.NO_SHOW_FEE": "IME No-Show Fee",
  "IME.ADMIN.SCHEDULING_FEE": "IME Administrative / Scheduling Fee",
  "ENG.PROPERTY_INSPECT.PROF_FEE": "Engineering Property Inspection — Professional Fee",
  "ENG.PROPERTY_INSPECT.TRAVEL_TRANSPORT": "Engineering Property Inspection — Transportation",
  "ENG.PROPERTY_INSPECT.MILEAGE": "Engineering Property Inspection — Mileage",
  "ENG.CAUSE_ORIGIN.PROF_FEE": "Engineering Cause & Origin Investigation — Professional Fee",
  "ENG.STRUCTURAL_ASSESS.PROF_FEE": "Engineering Structural Assessment — Professional Fee",
  "ENG.EXPERT_REPORT.PROF_FEE": "Engineering Expert Report — Professional Fee",
  "ENG.FILE_REVIEW.PROF_FEE": "Engineering File Review — Professional Fee",
  "ENG.SUPPLEMENTAL_INSPECT.PROF_FEE": "Engineering Supplemental Inspection — Professional Fee",
  "ENG.TESTIMONY_DEPO.PROF_FEE": "Engineering Expert Testimony / Deposition — Professional Fee",
  "IA.FIELD_ASSIGN.PROF_FEE": "Independent Adjusting Field Assignment — Professional Fee",
  "IA.FIELD_ASSIGN.TRAVEL_TRANSPORT": "Independent Adjusting Field Assignment — Transportation",
  "IA.FIELD_ASSIGN.MILEAGE": "Independent Adjusting Field Assignment — Mileage",
  "IA.FIELD_ASSIGN.TRAVEL_LODGING": "Independent Adjusting Field Assignment — Lodging",
  "IA.FIELD_ASSIGN.TRAVEL_MEALS": "Independent Adjusting Field Assignment — Meals & Per Diem",
  "IA.DESK_ASSIGN.PROF_FEE": "Independent Adjusting Desk Assignment — Professional Fee",
  "IA.CAT_ASSIGN.PROF_FEE": "Independent Adjusting Catastrophe Assignment — Professional Fee",
  "IA.PHOTO_DOC.PROF_FEE": "Independent Adjusting Photo & Documentation Services — Professional Fee",
  "IA.SUPPLEMENT_HANDLING.PROF_FEE": "Independent Adjusting Supplement Handling — Professional Fee",
  "IA.ADMIN.FILE_OPEN_FEE": "Independent Adjusting Administrative / File Open Fee",
  "INV.SURVEILLANCE.PROF_FEE": "Investigation Surveillance — Professional Fee",
  "INV.SURVEILLANCE.TRAVEL_TRANSPORT": "Investigation Surveillance — Transportation",
  "INV.SURVEILLANCE.MILEAGE": "Investigation Surveillance — Mileage",
  "INV.STATEMENT.PROF_FEE": "Investigation Recorded Statement — Professional Fee",
  "INV.BACKGROUND_ASSET.PROF_FEE": "Investigation Background / Asset Search — Professional Fee",
  "INV.AOE_COE.PROF_FEE": "Investigation AOE/COE Investigation — Professional Fee",
  "INV.SKIP_TRACE.PROF_FEE": "Investigation Skip Trace — Professional Fee",
  "REC.MED_RECORDS.RETRIEVAL_FEE": "Record Retrieval Medical Records — Retrieval Fee",
  "REC.MED_RECORDS.COPY_REPRO": "Record Retrieval Medical Records — Copy / Reproduction Fee",
  "REC.MED_RECORDS.POSTAGE_COURIER": "Record Retrieval Medical Records — Postage / Courier",
  "REC.MED_RECORDS.RUSH_PREMIUM": "Record Retrieval Medical Records — Rush / Expedite Premium",
  "REC.MED_RECORDS.CERT_COPY_FEE": "Record Retrieval Medical Records — Certified Copy Fee",
  "REC.EMPLOYMENT_RECORDS.RETRIEVAL_FEE": "Record Retrieval Employment Records — Retrieval Fee",
  "REC.LEGAL_RECORDS.RETRIEVAL_FEE": "Record Retrieval Legal / Court Records — Retrieval Fee",
  "REC.ADMIN.PROCESSING_FEE": "Record Retrieval Administrative / Processing Fee",
  "XDOMAIN.PASS_THROUGH.THIRD_PARTY_COST": "Pass-Through Third-Party Cost",
  "XDOMAIN.ADMIN_MISC.ADMIN_FEE": "Miscellaneous Administrative Fee",
};

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
  /** If provided, renders "Accept Suggestion" button on SUGGESTED cards. */
  onAccept?: (code: string, billingComponent: string) => void;
}

export function AiClassificationSuggestion({ suggestion, onAccept }: Props) {
  if (!suggestion) return null;

  const { verdict, suggested_code, suggested_billing_component, confidence, rationale } =
    suggestion;

  // ── SUGGESTED ─────────────────────────────────────────────────────────────
  if (verdict === "SUGGESTED" && suggested_code) {
    const label = TAXONOMY_LABELS[suggested_code] ?? suggested_code;
    const conf = confidence ? CONFIDENCE_STYLES[confidence] : null;

    return (
      <div className="mt-3 rounded-lg border border-indigo-200 bg-indigo-50 p-3">
        <div className="flex items-start gap-2">
          {/* Robot / sparkle icon */}
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
            {onAccept && suggested_billing_component && (
              <button
                onClick={() => onAccept(suggested_code, suggested_billing_component)}
                className="mt-2 rounded bg-indigo-600 px-3 py-1 text-xs font-semibold text-white hover:bg-indigo-700 transition-colors"
              >
                Accept Suggestion
              </button>
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
