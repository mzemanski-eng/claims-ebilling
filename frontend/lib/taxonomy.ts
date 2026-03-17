/**
 * Shared TAXONOMY_OPTIONS constant — mirrors app/taxonomy/constants.py.
 *
 * ENG uses level-based billing: 12 service types × 6 levels = 72 codes.
 * Code format: ENG.{SERVICE}.L{N}
 *
 * Level convention:
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
  // ── IME — Independent Medical Examination ─────────────────────────────────
  { code: "IME.PHY_EXAM.PROF_FEE",          label: "Physician Examination — Professional Fee",    domain: "IME" },
  { code: "IME.PHY_EXAM.TRAVEL_TRANSPORT",   label: "Physician Examination — Transportation",      domain: "IME" },
  { code: "IME.PHY_EXAM.TRAVEL_LODGING",     label: "Physician Examination — Lodging",             domain: "IME" },
  { code: "IME.PHY_EXAM.TRAVEL_MEALS",       label: "Physician Examination — Meals & Per Diem",    domain: "IME" },
  { code: "IME.PHY_EXAM.MILEAGE",            label: "Physician Examination — Mileage",             domain: "IME" },
  { code: "IME.MULTI_SPECIALTY.PROF_FEE",    label: "Multi-Specialty Panel",                       domain: "IME" },
  { code: "IME.RECORDS_REVIEW.PROF_FEE",     label: "Records Review (No Exam)",                    domain: "IME" },
  { code: "IME.ADDENDUM.PROF_FEE",           label: "Addendum Report",                             domain: "IME" },
  { code: "IME.PEER_REVIEW.PROF_FEE",        label: "Peer Review",                                 domain: "IME" },
  { code: "IME.CANCELLATION.CANCEL_FEE",     label: "Cancellation Fee",                            domain: "IME" },
  { code: "IME.NO_SHOW.NO_SHOW_FEE",         label: "No-Show Fee",                                 domain: "IME" },
  { code: "IME.ADMIN.SCHEDULING_FEE",        label: "Administrative / Scheduling Fee",             domain: "IME" },

  // ── ENG — Engineering & Forensic Services (12 services × 6 levels) ────────
  ...ENG_OPTIONS,

  // ── IA — Independent Adjusting ────────────────────────────────────────────
  { code: "IA.FIELD_ASSIGN.PROF_FEE",        label: "Field Assignment — Professional Fee",         domain: "IA" },
  { code: "IA.FIELD_ASSIGN.TRAVEL_TRANSPORT",label: "Field Assignment — Transportation",            domain: "IA" },
  { code: "IA.FIELD_ASSIGN.MILEAGE",         label: "Field Assignment — Mileage",                  domain: "IA" },
  { code: "IA.FIELD_ASSIGN.TRAVEL_LODGING",  label: "Field Assignment — Lodging",                  domain: "IA" },
  { code: "IA.FIELD_ASSIGN.TRAVEL_MEALS",    label: "Field Assignment — Meals & Per Diem",         domain: "IA" },
  { code: "IA.DESK_ASSIGN.PROF_FEE",         label: "Desk Assignment — Professional Fee",          domain: "IA" },
  { code: "IA.CAT_ASSIGN.PROF_FEE",          label: "Catastrophe Assignment — Professional Fee",   domain: "IA" },
  { code: "IA.PHOTO_DOC.PROF_FEE",           label: "Photo & Documentation Services",              domain: "IA" },
  { code: "IA.SUPPLEMENT_HANDLING.PROF_FEE", label: "Supplement Handling",                         domain: "IA" },
  { code: "IA.ADMIN.FILE_OPEN_FEE",          label: "Administrative / File Open Fee",              domain: "IA" },

  // ── INV — Investigation & Surveillance ───────────────────────────────────
  { code: "INV.SURVEILLANCE.PROF_FEE",       label: "Surveillance — Professional Fee",             domain: "INV" },
  { code: "INV.SURVEILLANCE.TRAVEL_TRANSPORT",label: "Surveillance — Transportation",              domain: "INV" },
  { code: "INV.SURVEILLANCE.MILEAGE",        label: "Surveillance — Mileage",                      domain: "INV" },
  { code: "INV.STATEMENT.PROF_FEE",          label: "Recorded Statement",                          domain: "INV" },
  { code: "INV.BACKGROUND_ASSET.PROF_FEE",   label: "Background / Asset Search",                   domain: "INV" },
  { code: "INV.AOE_COE.PROF_FEE",            label: "AOE/COE Investigation",                       domain: "INV" },
  { code: "INV.SKIP_TRACE.PROF_FEE",         label: "Skip Trace",                                  domain: "INV" },

  // ── REC — Record Retrieval & Management ──────────────────────────────────
  { code: "REC.MED_RECORDS.RETRIEVAL_FEE",   label: "Medical Records — Retrieval Fee",             domain: "REC" },
  { code: "REC.MED_RECORDS.COPY_REPRO",      label: "Medical Records — Copy / Reproduction",       domain: "REC" },
  { code: "REC.MED_RECORDS.POSTAGE_COURIER", label: "Medical Records — Postage / Courier",         domain: "REC" },
  { code: "REC.MED_RECORDS.RUSH_PREMIUM",    label: "Medical Records — Rush / Expedite Premium",   domain: "REC" },
  { code: "REC.MED_RECORDS.CERT_COPY_FEE",   label: "Medical Records — Certified Copy Fee",        domain: "REC" },
  { code: "REC.EMPLOYMENT_RECORDS.RETRIEVAL_FEE", label: "Employment Records — Retrieval Fee",     domain: "REC" },
  { code: "REC.LEGAL_RECORDS.RETRIEVAL_FEE", label: "Legal / Court Records — Retrieval Fee",       domain: "REC" },
  { code: "REC.ADMIN.PROCESSING_FEE",        label: "Administrative / Processing Fee",             domain: "REC" },

  // ── LA — Ladder Assist & Roof Access ─────────────────────────────────────
  { code: "LA.LADDER_ACCESS.FLAT_FEE",       label: "Ladder Access",                               domain: "LA" },
  { code: "LA.ROOF_INSPECT.FLAT_FEE",        label: "Roof Inspection",                             domain: "LA" },
  { code: "LA.ROOF_INSPECT_HARNESS.FLAT_FEE",label: "Roof Inspection with Harness Equipment",      domain: "LA" },
  { code: "LA.TARP_COVER.FLAT_FEE",          label: "Tarp / Roof Covering",                        domain: "LA" },
  { code: "LA.CANCEL.CANCEL_FEE",            label: "Appointment Cancellation Fee",                domain: "LA" },
  { code: "LA.TRIP_CHARGE.TRIP_FEE",         label: "Trip Charge",                                 domain: "LA" },

  // ── XDOMAIN — Cross-Domain ────────────────────────────────────────────────
  { code: "XDOMAIN.PASS_THROUGH.THIRD_PARTY_COST", label: "Pass-Through Third-Party Cost",         domain: "XDOMAIN" },
  { code: "XDOMAIN.ADMIN_MISC.ADMIN_FEE",    label: "Miscellaneous Administrative Fee",            domain: "XDOMAIN" },
];

/** Unique domain list in display order. */
export const TAXONOMY_DOMAINS = [...new Set(TAXONOMY_OPTIONS.map((t) => t.domain))];
