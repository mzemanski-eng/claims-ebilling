/**
 * Veridian ALAE Taxonomy — mirrors app/taxonomy/constants.py.
 *
 * Domains:
 *   IA      Independent Adjusting
 *   ENG     Engineering & Forensic Services (12 services × 6 levels = 72 codes)
 *   REC     Record Retrieval & Management
 *   LA      Ladder Assist & Roof Access
 *   INSP    Property Inspections
 *   VIRT    Virtual Assist Inspections
 *   CR      Court Reporting
 *   INV     Investigation & Surveillance
 *   DRNE    Drone & Aerial Inspection
 *   APPR    Property Appraisal & Umpire
 *   XDOMAIN Cross-Domain / Pass-Through
 *
 * ENG level convention:
 *   L1  Principal Engineer (highest rate)
 *   L2  Senior Engineer
 *   L3  Staff Engineer
 *   L4  Associate Engineer
 *   L5  Junior Engineer / Technician
 *   L6  Administrative / Support Staff
 */

export interface TaxonomyOption {
  code: string;
  label: string;
  domain: string;
}

// ── ENG level-based entry generator ─────────────────────────────────────────

const ENG_SERVICES: [string, string][] = [
  ["AAR",  "Auto Accident Reconstruction"],
  ["CT",   "Component Testing"],
  ["DA",   "Damage Assessment"],
  ["CAO",  "Engineering Cause and Origin"],
  ["EA",   "Engineering Analysis"],
  ["FA",   "Failure Analysis"],
  ["FOC",  "Fire Origin and Cause"],
  ["PR",   "Peer Review"],
  ["RPT",  "Reporting"],
  ["EWD",  "Expert Witness / Deposition"],
  ["AOS",  "Admin and Office Support"],
  ["PM",   "Project Management"],
];

const ENG_OPTIONS: TaxonomyOption[] = ENG_SERVICES.flatMap(([code, name]) =>
  [1, 2, 3, 4, 5, 6].map((level) => ({
    code:   `ENG.${code}.L${level}`,
    label:  `${name} — Level ${level}`,
    domain: "ENG",
  })),
);

// ── Full taxonomy options list ───────────────────────────────────────────────

export const TAXONOMY_OPTIONS: TaxonomyOption[] = [
  // ── ENG — Engineering & Forensic Services (12 services × 6 levels) ────────
  ...ENG_OPTIONS,

  // ── IA — Independent Adjusting ────────────────────────────────────────────
  { code: "IA.FIELD_ASSIGN.PROF_FEE",         label: "Field Assignment — Professional Fee",         domain: "IA" },
  { code: "IA.FIELD_ASSIGN.TRAVEL_TRANSPORT",  label: "Field Assignment — Transportation",           domain: "IA" },
  { code: "IA.FIELD_ASSIGN.MILEAGE",           label: "Field Assignment — Mileage",                  domain: "IA" },
  { code: "IA.FIELD_ASSIGN.TRAVEL_LODGING",    label: "Field Assignment — Lodging",                  domain: "IA" },
  { code: "IA.FIELD_ASSIGN.TRAVEL_MEALS",      label: "Field Assignment — Meals & Per Diem",         domain: "IA" },
  { code: "IA.DESK_ASSIGN.PROF_FEE",           label: "Desk Assignment — Professional Fee",          domain: "IA" },
  { code: "IA.CAT_ASSIGN.PROF_FEE",            label: "Catastrophe Assignment — Professional Fee",   domain: "IA" },
  { code: "IA.PHOTO_DOC.PROF_FEE",             label: "Photo & Documentation Services",              domain: "IA" },
  { code: "IA.SUPPLEMENT_HANDLING.PROF_FEE",   label: "Supplement Handling",                         domain: "IA" },
  { code: "IA.ADMIN.FILE_OPEN_FEE",            label: "Administrative / File Open Fee",              domain: "IA" },

  // ── REC — Record Retrieval & Management ──────────────────────────────────
  { code: "REC.MED_RECORDS.RETRIEVAL_FEE",     label: "Medical Records — Retrieval Fee",             domain: "REC" },
  { code: "REC.MED_RECORDS.COPY_REPRO",        label: "Medical Records — Copy / Reproduction",       domain: "REC" },
  { code: "REC.MED_RECORDS.POSTAGE_COURIER",   label: "Medical Records — Postage / Courier",         domain: "REC" },
  { code: "REC.MED_RECORDS.RUSH_PREMIUM",      label: "Medical Records — Rush / Expedite Premium",   domain: "REC" },
  { code: "REC.MED_RECORDS.CERT_COPY_FEE",     label: "Medical Records — Certified Copy Fee",        domain: "REC" },
  { code: "REC.EMPLOYMENT_RECORDS.RETRIEVAL_FEE", label: "Employment Records — Retrieval Fee",       domain: "REC" },
  { code: "REC.LEGAL_RECORDS.RETRIEVAL_FEE",   label: "Legal / Court Records — Retrieval Fee",       domain: "REC" },
  { code: "REC.ADMIN.PROCESSING_FEE",          label: "Administrative / Processing Fee",             domain: "REC" },

  // ── LA — Ladder Assist & Roof Access ─────────────────────────────────────
  { code: "LA.LADDER_ACCESS.FLAT_FEE",         label: "Ladder Access",                               domain: "LA" },
  { code: "LA.ROOF_INSPECT.FLAT_FEE",          label: "Roof Inspection",                             domain: "LA" },
  { code: "LA.ROOF_INSPECT_HARNESS.FLAT_FEE",  label: "Roof Inspection with Harness Equipment",      domain: "LA" },
  { code: "LA.TARP_COVER.FLAT_FEE",            label: "Tarp / Roof Covering",                        domain: "LA" },
  { code: "LA.CANCEL.CANCEL_FEE",              label: "Appointment Cancellation Fee",                domain: "LA" },
  { code: "LA.TRIP_CHARGE.TRIP_FEE",           label: "Trip Charge",                                 domain: "LA" },

  // ── INSP — Property Inspections ──────────────────────────────────────────
  { code: "INSP.BASIC.FLAT_FEE",               label: "Basic Property Inspection",                   domain: "INSP" },
  { code: "INSP.REINSPECT.FLAT_FEE",           label: "Re-Inspection",                               domain: "INSP" },
  { code: "INSP.EXTERIOR.FLAT_FEE",            label: "Exterior / Drive-By Inspection",              domain: "INSP" },
  { code: "INSP.INTERIOR.FLAT_FEE",            label: "Interior Inspection",                         domain: "INSP" },
  { code: "INSP.DAMAGE_ASSESS.FLAT_FEE",       label: "Damage Assessment Report",                    domain: "INSP" },
  { code: "INSP.SUPPLEMENT_REVIEW.FLAT_FEE",   label: "Supplement Review",                           domain: "INSP" },
  { code: "INSP.PHOTO_DOC.FLAT_FEE",           label: "Photo Documentation Report",                  domain: "INSP" },
  { code: "INSP.DISPUTE_REINSPECT.FLAT_FEE",   label: "Re-Inspection (Disputed Estimate)",           domain: "INSP" },
  { code: "INSP.CANCEL.CANCEL_FEE",            label: "Cancellation Fee",                            domain: "INSP" },
  { code: "INSP.TRIP_CHARGE.TRIP_FEE",         label: "Trip Charge / No Access",                     domain: "INSP" },

  // ── VIRT — Virtual Assist Inspections ────────────────────────────────────
  { code: "VIRT.GUIDED.FLAT_FEE",              label: "Guided Virtual Inspection",                   domain: "VIRT" },
  { code: "VIRT.SELF_SERVICE.FLAT_FEE",        label: "Self-Service Video Inspection",               domain: "VIRT" },
  { code: "VIRT.AI_SCOPE.FLAT_FEE",            label: "AI-Assisted Scope / Estimate",                domain: "VIRT" },
  { code: "VIRT.AERIAL_ANALYSIS.FLAT_FEE",     label: "Aerial / Satellite Image Analysis",           domain: "VIRT" },
  { code: "VIRT.PHOTO_AI.FLAT_FEE",            label: "Photo AI Damage Detection",                   domain: "VIRT" },
  { code: "VIRT.CANCEL.CANCEL_FEE",            label: "Virtual Inspection Cancellation Fee",         domain: "VIRT" },

  // ── CR — Court Reporting ──────────────────────────────────────────────────
  { code: "CR.DEPO.APPEARANCE_FEE",            label: "Court Reporter Appearance Fee",               domain: "CR" },
  { code: "CR.DEPO.TRANSCRIPT",                label: "Deposition Transcript",                       domain: "CR" },
  { code: "CR.DEPO.COPY_FEE",                  label: "Deposition Transcript — Copy Fee",            domain: "CR" },
  { code: "CR.DEPO.VIDEOGRAPHY",               label: "Deposition Videography",                      domain: "CR" },
  { code: "CR.DEPO.RUSH_TRANSCRIPT",           label: "Rush / Expedited Transcript",                 domain: "CR" },
  { code: "CR.DEPO.EXHIBIT_HANDLING",          label: "Exhibit Handling Fee",                        domain: "CR" },
  { code: "CR.DEPO.REMOTE_FEE",                label: "Remote / Video Deposition Technology Fee",    domain: "CR" },
  { code: "CR.DEPO.TRAVEL_TRANSPORT",          label: "Court Reporter Travel — Transportation",      domain: "CR" },
  { code: "CR.DEPO.MILEAGE",                   label: "Court Reporter Travel — Mileage",             domain: "CR" },
  { code: "CR.CANCEL.CANCEL_FEE",              label: "Cancellation Fee",                            domain: "CR" },
  { code: "CR.NO_SHOW.NO_SHOW_FEE",            label: "No-Show Fee",                                 domain: "CR" },

  // ── INV — Investigation & Surveillance ───────────────────────────────────
  { code: "INV.SURVEILLANCE.PROF_FEE",         label: "Surveillance — Professional Fee",             domain: "INV" },
  { code: "INV.SURVEILLANCE.TRAVEL_TRANSPORT", label: "Surveillance — Transportation",               domain: "INV" },
  { code: "INV.SURVEILLANCE.MILEAGE",          label: "Surveillance — Mileage",                      domain: "INV" },
  { code: "INV.STATEMENT.PROF_FEE",            label: "Recorded Statement",                          domain: "INV" },
  { code: "INV.BACKGROUND_ASSET.PROF_FEE",     label: "Background / Asset Search",                   domain: "INV" },
  { code: "INV.AOE_COE.PROF_FEE",              label: "AOE/COE Investigation",                       domain: "INV" },
  { code: "INV.SKIP_TRACE.PROF_FEE",           label: "Skip Trace",                                  domain: "INV" },

  // ── DRNE — Drone & Aerial Inspection ─────────────────────────────────────
  { code: "DRNE.ROOF_SURVEY.FLAT_FEE",         label: "Drone Roof Survey",                           domain: "DRNE" },
  { code: "DRNE.AERIAL_PHOTO.FLAT_FEE",        label: "Aerial Photography & Documentation",          domain: "DRNE" },
  { code: "DRNE.VIDEO.FLAT_FEE",               label: "Aerial Video Documentation",                  domain: "DRNE" },
  { code: "DRNE.THERMAL.FLAT_FEE",             label: "Thermal Imaging Survey",                      domain: "DRNE" },
  { code: "DRNE.CANCEL.CANCEL_FEE",            label: "Cancellation Fee",                            domain: "DRNE" },
  { code: "DRNE.TRIP_CHARGE.TRIP_FEE",         label: "Trip Charge / No Access",                     domain: "DRNE" },

  // ── APPR — Property Appraisal & Umpire ───────────────────────────────────
  { code: "APPR.PROPERTY_APPRAISAL.PROF_FEE",  label: "Property Appraisal — Professional Fee",       domain: "APPR" },
  { code: "APPR.UMPIRE.PROF_FEE",              label: "Umpire Services — Professional Fee",          domain: "APPR" },
  { code: "APPR.SITE_VISIT.FLAT_FEE",          label: "Appraisal Site Visit",                        domain: "APPR" },
  { code: "APPR.CONTENTS_INVENTORY.PROF_FEE",  label: "Contents Inventory & Valuation",              domain: "APPR" },
  { code: "APPR.ADMIN.FILING_FEE",             label: "Appraisal Administrative / Filing Fee",       domain: "APPR" },

  // ── XDOMAIN — Cross-Domain ────────────────────────────────────────────────
  { code: "XDOMAIN.PASS_THROUGH.THIRD_PARTY_COST", label: "Pass-Through Third-Party Cost",          domain: "XDOMAIN" },
  { code: "XDOMAIN.ADMIN_MISC.ADMIN_FEE",      label: "Miscellaneous Administrative Fee",           domain: "XDOMAIN" },
];

/** Unique domain list in display order. */
export const TAXONOMY_DOMAINS = Array.from(new Set(TAXONOMY_OPTIONS.map((t) => t.domain)));

/** Human-readable display labels for each domain, used in UI optgroup headers. */
export const DOMAIN_LABELS: Record<string, string> = {
  IA:      "Independent Adjusting",
  ENG:     "Engineering & Forensic",
  REC:     "Record Retrieval",
  LA:      "Ladder Assist",
  INSP:    "Property Inspections",
  VIRT:    "Virtual Assist Inspections",
  CR:      "Court Reporting",
  INV:     "Investigation & Surveillance",
  DRNE:    "Drone & Aerial Inspection",
  APPR:    "Property Appraisal & Umpire",
  XDOMAIN: "Cross-Domain / Pass-Through",
};
