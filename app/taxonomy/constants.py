"""
Veridian ALAE Taxonomy — canonical code definitions for personal P&C ALAE spend.

Format: each entry is a dict that maps 1:1 to TaxonomyItem columns.
These are the ground-truth definitions; the DB is seeded from this file.

Code format: {DOMAIN}.{SERVICE_ITEM}.{COMPONENT}

Domains:
  IA      Independent Adjusting
  ENG     Engineering & Forensic Services  (level-based: ENG.{SERVICE}.L{1-6})
  REC     Record Retrieval & Management
  LA      Ladder Assist & Roof Access
  INSP    Property Inspections (standalone inspection vendors)
  VIRT    Virtual Assist Inspections
  CR      Court Reporting
  INV     Investigation & Surveillance
  DRNE    Drone & Aerial Inspection
  APPR    Property Appraisal & Umpire
  XDOMAIN Cross-domain (pass-through, misc admin)

ENG level convention:
  L1  Principal Engineer (highest rate)
  L2  Senior Engineer
  L3  Staff Engineer
  L4  Associate Engineer
  L5  Junior Engineer / Technician
  L6  Administrative / Support Staff
"""

# ── ENG level-based entry generator ──────────────────────────────────────────

_ENG_SERVICES: list[tuple[str, str]] = [
    ("AAR", "Auto Accident Reconstruction"),
    ("CT", "Component Testing"),
    ("DA", "Damage Assessment"),
    ("CAO", "Engineering Cause and Origin"),
    ("EA", "Engineering Analysis"),
    ("FA", "Failure Analysis"),
    ("FOC", "Fire Origin and Cause"),
    ("PR", "Peer Review"),
    ("RPT", "Reporting"),
    ("EWD", "Expert Witness / Deposition"),
    ("AOS", "Admin and Office Support"),
    ("PM", "Project Management"),
]

_ENG_LEVEL_TITLES: dict[int, str] = {
    1: "Principal Engineer",
    2: "Senior Engineer",
    3: "Staff Engineer",
    4: "Associate Engineer",
    5: "Junior Engineer / Technician",
    6: "Administrative / Support Staff",
}


def _eng_entries() -> list[dict]:
    """Generate 72 ENG entries: 12 service types × 6 levels."""
    entries = []
    for svc_code, svc_name in _ENG_SERVICES:
        for lvl in range(1, 7):
            lvl_code = f"L{lvl}"
            entries.append(
                {
                    "code": f"ENG.{svc_code}.{lvl_code}",
                    "domain": "ENG",
                    "service_item": svc_code,
                    "billing_component": lvl_code,
                    "unit_model": "per_hour",
                    "label": f"{svc_name} — Level {lvl}",
                    "description": (
                        f"{svc_name} services at Level {lvl} "
                        f"({_ENG_LEVEL_TITLES[lvl]} seniority). Billed per hour."
                    ),
                }
            )
    return entries


TAXONOMY: list[dict] = [
    # ══════════════════════════════════════════════════════════════════════════
    # ENG — Engineering & Forensic Services
    # 12 service types × 6 levels = 72 codes.  See _eng_entries() above.
    # Code format: ENG.{SERVICE}.L{N}  (L1 = Principal … L6 = Admin/Support)
    # ══════════════════════════════════════════════════════════════════════════
    *_eng_entries(),
    # ══════════════════════════════════════════════════════════════════════════
    # IA — Independent Adjusting
    # ══════════════════════════════════════════════════════════════════════════
    {
        "code": "IA.FIELD_ASSIGN.PROF_FEE",
        "domain": "IA",
        "service_item": "FIELD_ASSIGN",
        "billing_component": "PROF_FEE",
        "unit_model": "per_diem",
        "label": "Independent Adjusting Field Assignment — Professional Fee",
        "description": "Per-diem or hourly fee for field adjusting services (on-site claim handling).",
    },
    {
        "code": "IA.FIELD_ASSIGN.TRAVEL_TRANSPORT",
        "domain": "IA",
        "service_item": "FIELD_ASSIGN",
        "billing_component": "TRAVEL_TRANSPORT",
        "unit_model": "actual",
        "label": "Independent Adjusting Field Assignment — Transportation",
        "description": "Actual transportation costs for field adjuster travel.",
    },
    {
        "code": "IA.FIELD_ASSIGN.MILEAGE",
        "domain": "IA",
        "service_item": "FIELD_ASSIGN",
        "billing_component": "MILEAGE",
        "unit_model": "per_mile",
        "label": "Independent Adjusting Field Assignment — Mileage",
        "description": "Mileage reimbursement for field adjuster.",
    },
    {
        "code": "IA.FIELD_ASSIGN.TRAVEL_LODGING",
        "domain": "IA",
        "service_item": "FIELD_ASSIGN",
        "billing_component": "TRAVEL_LODGING",
        "unit_model": "per_night",
        "label": "Independent Adjusting Field Assignment — Lodging",
        "description": "Hotel/lodging for field adjuster overnight assignments.",
    },
    {
        "code": "IA.FIELD_ASSIGN.TRAVEL_MEALS",
        "domain": "IA",
        "service_item": "FIELD_ASSIGN",
        "billing_component": "TRAVEL_MEALS",
        "unit_model": "per_diem",
        "label": "Independent Adjusting Field Assignment — Meals & Per Diem",
        "description": "Meal per diem for field adjuster travel days.",
    },
    {
        "code": "IA.DESK_ASSIGN.PROF_FEE",
        "domain": "IA",
        "service_item": "DESK_ASSIGN",
        "billing_component": "PROF_FEE",
        "unit_model": "per_file",
        "label": "Independent Adjusting Desk Assignment — Professional Fee",
        "description": "Per-file or hourly fee for desk/virtual claim handling without site visit.",
    },
    {
        "code": "IA.CAT_ASSIGN.PROF_FEE",
        "domain": "IA",
        "service_item": "CAT_ASSIGN",
        "billing_component": "PROF_FEE",
        "unit_model": "per_diem",
        "label": "Independent Adjusting Catastrophe Assignment — Professional Fee",
        "description": "Per-diem fee for catastrophe (CAT) deployment adjusting services.",
    },
    {
        "code": "IA.PHOTO_DOC.PROF_FEE",
        "domain": "IA",
        "service_item": "PHOTO_DOC",
        "billing_component": "PROF_FEE",
        "unit_model": "per_file",
        "label": "Independent Adjusting Photo & Documentation Services — Professional Fee",
        "description": "Fee for photographic documentation and scene documentation services.",
    },
    {
        "code": "IA.SUPPLEMENT_HANDLING.PROF_FEE",
        "domain": "IA",
        "service_item": "SUPPLEMENT_HANDLING",
        "billing_component": "PROF_FEE",
        "unit_model": "per_occurrence",
        "label": "Independent Adjusting Supplement Handling — Professional Fee",
        "description": "Fee for handling repair estimate supplements.",
    },
    {
        "code": "IA.ADMIN.FILE_OPEN_FEE",
        "domain": "IA",
        "service_item": "ADMIN",
        "billing_component": "FILE_OPEN_FEE",
        "unit_model": "flat_fee",
        "label": "Independent Adjusting Administrative / File Open Fee",
        "description": "One-time administrative fee for opening and setting up a new claim file.",
    },
    # ══════════════════════════════════════════════════════════════════════════
    # REC — Record Retrieval & Management
    # ══════════════════════════════════════════════════════════════════════════
    {
        "code": "REC.MED_RECORDS.RETRIEVAL_FEE",
        "domain": "REC",
        "service_item": "MED_RECORDS",
        "billing_component": "RETRIEVAL_FEE",
        "unit_model": "per_request",
        "label": "Record Retrieval Medical Records — Retrieval Fee",
        "description": "Fee for requesting and obtaining medical records from a provider.",
    },
    {
        "code": "REC.MED_RECORDS.COPY_REPRO",
        "domain": "REC",
        "service_item": "MED_RECORDS",
        "billing_component": "COPY_REPRO",
        "unit_model": "per_page",
        "label": "Record Retrieval Medical Records — Copy / Reproduction Fee",
        "description": "Per-page copying/reproduction fee for medical records.",
    },
    {
        "code": "REC.MED_RECORDS.POSTAGE_COURIER",
        "domain": "REC",
        "service_item": "MED_RECORDS",
        "billing_component": "POSTAGE_COURIER",
        "unit_model": "actual",
        "label": "Record Retrieval Medical Records — Postage / Courier",
        "description": "Actual postage or courier cost for delivering medical records.",
    },
    {
        "code": "REC.MED_RECORDS.RUSH_PREMIUM",
        "domain": "REC",
        "service_item": "MED_RECORDS",
        "billing_component": "RUSH_PREMIUM",
        "unit_model": "flat_fee",
        "label": "Record Retrieval Medical Records — Rush / Expedite Premium",
        "description": "Additional fee for expedited record retrieval.",
    },
    {
        "code": "REC.MED_RECORDS.CERT_COPY_FEE",
        "domain": "REC",
        "service_item": "MED_RECORDS",
        "billing_component": "CERT_COPY_FEE",
        "unit_model": "per_request",
        "label": "Record Retrieval Medical Records — Certified Copy Fee",
        "description": "Fee for obtaining certified/notarized copies of medical records.",
    },
    {
        "code": "REC.EMPLOYMENT_RECORDS.RETRIEVAL_FEE",
        "domain": "REC",
        "service_item": "EMPLOYMENT_RECORDS",
        "billing_component": "RETRIEVAL_FEE",
        "unit_model": "per_request",
        "label": "Record Retrieval Employment Records — Retrieval Fee",
        "description": "Fee for requesting and obtaining employment or wage records.",
    },
    {
        "code": "REC.LEGAL_RECORDS.RETRIEVAL_FEE",
        "domain": "REC",
        "service_item": "LEGAL_RECORDS",
        "billing_component": "RETRIEVAL_FEE",
        "unit_model": "per_request",
        "label": "Record Retrieval Legal / Court Records — Retrieval Fee",
        "description": "Fee for requesting court documents, police reports, or legal filings.",
    },
    {
        "code": "REC.ADMIN.PROCESSING_FEE",
        "domain": "REC",
        "service_item": "ADMIN",
        "billing_component": "PROCESSING_FEE",
        "unit_model": "flat_fee",
        "label": "Record Retrieval Administrative / Processing Fee",
        "description": "Administrative processing fee for record retrieval management.",
    },
    # ══════════════════════════════════════════════════════════════════════════
    # LA — Ladder Assist & Roof Access
    # ══════════════════════════════════════════════════════════════════════════
    {
        "code": "LA.LADDER_ACCESS.FLAT_FEE",
        "domain": "LA",
        "service_item": "LADDER_ACCESS",
        "billing_component": "FLAT_FEE",
        "unit_model": "per_occurrence",
        "label": "Ladder Access",
        "description": (
            "Ladder placement and stabilisation by a ladder assist technician "
            "to allow adjuster or inspector access to a roof or elevated area."
        ),
    },
    {
        "code": "LA.ROOF_INSPECT.FLAT_FEE",
        "domain": "LA",
        "service_item": "ROOF_INSPECT",
        "billing_component": "FLAT_FEE",
        "unit_model": "per_occurrence",
        "label": "Roof Inspection",
        "description": "On-roof inspection of damage or construction by a ladder assist technician.",
    },
    {
        "code": "LA.ROOF_INSPECT_HARNESS.FLAT_FEE",
        "domain": "LA",
        "service_item": "ROOF_INSPECT_HARNESS",
        "billing_component": "FLAT_FEE",
        "unit_model": "per_occurrence",
        "label": "Roof Inspection with Harness Equipment",
        "description": (
            "On-roof inspection requiring fall-protection harness equipment "
            "(steep pitch or OSHA-mandated). Carries a higher rate than standard inspection."
        ),
    },
    {
        "code": "LA.TARP_COVER.FLAT_FEE",
        "domain": "LA",
        "service_item": "TARP_COVER",
        "billing_component": "FLAT_FEE",
        "unit_model": "per_occurrence",
        "label": "Tarp or Roof Covering",
        "description": (
            "Emergency application of a tarp or other temporary roof covering "
            "to prevent further damage pending permanent repair."
        ),
    },
    {
        "code": "LA.CANCEL.CANCEL_FEE",
        "domain": "LA",
        "service_item": "CANCEL",
        "billing_component": "CANCEL_FEE",
        "unit_model": "flat_fee",
        "label": "Appointment Cancellation Fee",
        "description": (
            "Fee charged when a scheduled ladder assist appointment is cancelled "
            "within the contract-specified notice window."
        ),
    },
    {
        "code": "LA.TRIP_CHARGE.TRIP_FEE",
        "domain": "LA",
        "service_item": "TRIP_CHARGE",
        "billing_component": "TRIP_FEE",
        "unit_model": "flat_fee",
        "label": "Trip Charge",
        "description": (
            "Fee charged when the technician is dispatched and arrives on site "
            "but is unable to complete the service (e.g., access denied, unsafe conditions)."
        ),
    },
    # ══════════════════════════════════════════════════════════════════════════
    # INSP — Property Inspections
    # Standalone inspection vendors (distinct from IA independent adjusters).
    # ══════════════════════════════════════════════════════════════════════════
    {
        "code": "INSP.BASIC.FLAT_FEE",
        "domain": "INSP",
        "service_item": "BASIC",
        "billing_component": "FLAT_FEE",
        "unit_model": "per_occurrence",
        "label": "Basic Property Inspection",
        "description": (
            "Standard interior and exterior property inspection to document "
            "condition, damage, or compliance for a claim."
        ),
    },
    {
        "code": "INSP.REINSPECT.FLAT_FEE",
        "domain": "INSP",
        "service_item": "REINSPECT",
        "billing_component": "FLAT_FEE",
        "unit_model": "per_occurrence",
        "label": "Re-Inspection",
        "description": (
            "Follow-up inspection of a previously inspected property to verify "
            "repairs, changes in condition, or additional damage."
        ),
    },
    {
        "code": "INSP.EXTERIOR.FLAT_FEE",
        "domain": "INSP",
        "service_item": "EXTERIOR",
        "billing_component": "FLAT_FEE",
        "unit_model": "per_occurrence",
        "label": "Exterior / Drive-By Inspection",
        "description": (
            "Exterior-only or drive-by property inspection where interior access "
            "is not required or available."
        ),
    },
    {
        "code": "INSP.INTERIOR.FLAT_FEE",
        "domain": "INSP",
        "service_item": "INTERIOR",
        "billing_component": "FLAT_FEE",
        "unit_model": "per_occurrence",
        "label": "Interior Inspection",
        "description": (
            "Interior property inspection documenting structural elements, "
            "finishes, fixtures, and interior damage."
        ),
    },
    {
        "code": "INSP.DAMAGE_ASSESS.FLAT_FEE",
        "domain": "INSP",
        "service_item": "DAMAGE_ASSESS",
        "billing_component": "FLAT_FEE",
        "unit_model": "per_occurrence",
        "label": "Damage Assessment Report",
        "description": (
            "Detailed written report assessing the nature, scope, and cause of "
            "property damage following an inspection."
        ),
    },
    {
        "code": "INSP.SUPPLEMENT_REVIEW.FLAT_FEE",
        "domain": "INSP",
        "service_item": "SUPPLEMENT_REVIEW",
        "billing_component": "FLAT_FEE",
        "unit_model": "per_occurrence",
        "label": "Supplement Review",
        "description": (
            "Review and field verification of a contractor supplement estimate "
            "to confirm accuracy of additional damage items."
        ),
    },
    {
        "code": "INSP.PHOTO_DOC.FLAT_FEE",
        "domain": "INSP",
        "service_item": "PHOTO_DOC",
        "billing_component": "FLAT_FEE",
        "unit_model": "per_occurrence",
        "label": "Photo Documentation Report",
        "description": (
            "Photographic documentation of property condition or damage, "
            "delivered as an organized photo report."
        ),
    },
    {
        "code": "INSP.DISPUTE_REINSPECT.FLAT_FEE",
        "domain": "INSP",
        "service_item": "DISPUTE_REINSPECT",
        "billing_component": "FLAT_FEE",
        "unit_model": "per_occurrence",
        "label": "Re-Inspection (Disputed Estimate)",
        "description": (
            "Re-inspection conducted specifically to resolve a disputed repair "
            "estimate or appraisal discrepancy."
        ),
    },
    {
        "code": "INSP.CANCEL.CANCEL_FEE",
        "domain": "INSP",
        "service_item": "CANCEL",
        "billing_component": "CANCEL_FEE",
        "unit_model": "flat_fee",
        "label": "Cancellation Fee",
        "description": (
            "Fee charged when a scheduled inspection appointment is cancelled "
            "within the contract-specified notice window."
        ),
    },
    {
        "code": "INSP.TRIP_CHARGE.TRIP_FEE",
        "domain": "INSP",
        "service_item": "TRIP_CHARGE",
        "billing_component": "TRIP_FEE",
        "unit_model": "flat_fee",
        "label": "Trip Charge / No Access",
        "description": (
            "Fee charged when the inspector is dispatched and arrives on site "
            "but is unable to complete the inspection (e.g., access denied, property vacant)."
        ),
    },
    # ══════════════════════════════════════════════════════════════════════════
    # VIRT — Virtual Assist Inspections
    # Remote/digital inspection services: guided video, AI scope, satellite imagery.
    # ══════════════════════════════════════════════════════════════════════════
    {
        "code": "VIRT.GUIDED.FLAT_FEE",
        "domain": "VIRT",
        "service_item": "GUIDED",
        "billing_component": "FLAT_FEE",
        "unit_model": "per_occurrence",
        "label": "Guided Virtual Inspection",
        "description": (
            "Live video-guided inspection where a vendor technician directs the "
            "policyholder or field contact through a structured damage walkthrough."
        ),
    },
    {
        "code": "VIRT.SELF_SERVICE.FLAT_FEE",
        "domain": "VIRT",
        "service_item": "SELF_SERVICE",
        "billing_component": "FLAT_FEE",
        "unit_model": "per_occurrence",
        "label": "Self-Service Video Inspection",
        "description": (
            "App-guided inspection where the policyholder submits photos and video "
            "following a scripted capture workflow; vendor reviews and reports."
        ),
    },
    {
        "code": "VIRT.AI_SCOPE.FLAT_FEE",
        "domain": "VIRT",
        "service_item": "AI_SCOPE",
        "billing_component": "FLAT_FEE",
        "unit_model": "per_occurrence",
        "label": "AI-Assisted Scope / Estimate",
        "description": (
            "Automated damage scoping service using AI image analysis to generate "
            "a preliminary repair estimate from submitted photos or video."
        ),
    },
    {
        "code": "VIRT.AERIAL_ANALYSIS.FLAT_FEE",
        "domain": "VIRT",
        "service_item": "AERIAL_ANALYSIS",
        "billing_component": "FLAT_FEE",
        "unit_model": "per_occurrence",
        "label": "Aerial / Satellite Image Analysis",
        "description": (
            "Roof and property condition analysis using third-party aerial or "
            "satellite imagery (e.g., EagleView, Nearmap, Verisk). "
            "No site visit required."
        ),
    },
    {
        "code": "VIRT.PHOTO_AI.FLAT_FEE",
        "domain": "VIRT",
        "service_item": "PHOTO_AI",
        "billing_component": "FLAT_FEE",
        "unit_model": "per_occurrence",
        "label": "Photo AI Damage Detection",
        "description": (
            "AI-powered review of submitted photographs to detect, classify, "
            "and quantify property damage items."
        ),
    },
    {
        "code": "VIRT.CANCEL.CANCEL_FEE",
        "domain": "VIRT",
        "service_item": "CANCEL",
        "billing_component": "CANCEL_FEE",
        "unit_model": "flat_fee",
        "label": "Virtual Inspection Cancellation Fee",
        "description": (
            "Fee charged when a scheduled virtual inspection session is cancelled "
            "within the contract-specified notice window."
        ),
    },
    # ══════════════════════════════════════════════════════════════════════════
    # CR — Court Reporting
    # Deposition, transcript, and litigation support services.
    # ══════════════════════════════════════════════════════════════════════════
    {
        "code": "CR.DEPO.APPEARANCE_FEE",
        "domain": "CR",
        "service_item": "DEPO",
        "billing_component": "APPEARANCE_FEE",
        "unit_model": "per_occurrence",
        "label": "Court Reporter Appearance Fee",
        "description": "Flat fee for the court reporter's attendance at a deposition.",
    },
    {
        "code": "CR.DEPO.TRANSCRIPT",
        "domain": "CR",
        "service_item": "DEPO",
        "billing_component": "TRANSCRIPT",
        "unit_model": "per_page",
        "label": "Deposition Transcript",
        "description": (
            "Per-page fee for the original deposition transcript. "
            "Rates are often tiered (e.g., first 100 pages / pages 101+)."
        ),
    },
    {
        "code": "CR.DEPO.COPY_FEE",
        "domain": "CR",
        "service_item": "DEPO",
        "billing_component": "COPY_FEE",
        "unit_model": "per_page",
        "label": "Deposition Transcript — Copy Fee",
        "description": "Per-page fee for additional copies of a deposition transcript.",
    },
    {
        "code": "CR.DEPO.VIDEOGRAPHY",
        "domain": "CR",
        "service_item": "DEPO",
        "billing_component": "VIDEOGRAPHY",
        "unit_model": "per_hour",
        "label": "Deposition Videography",
        "description": "Hourly fee for video recording of a deposition.",
    },
    {
        "code": "CR.DEPO.RUSH_TRANSCRIPT",
        "domain": "CR",
        "service_item": "DEPO",
        "billing_component": "RUSH_TRANSCRIPT",
        "unit_model": "per_page",
        "label": "Rush / Expedited Transcript",
        "description": "Premium per-page surcharge for expedited transcript delivery.",
    },
    {
        "code": "CR.DEPO.EXHIBIT_HANDLING",
        "domain": "CR",
        "service_item": "DEPO",
        "billing_component": "EXHIBIT_HANDLING",
        "unit_model": "flat_fee",
        "label": "Exhibit Handling Fee",
        "description": "Flat fee for managing and reproducing deposition exhibits.",
    },
    {
        "code": "CR.DEPO.REMOTE_FEE",
        "domain": "CR",
        "service_item": "DEPO",
        "billing_component": "REMOTE_FEE",
        "unit_model": "flat_fee",
        "label": "Remote / Video Deposition Technology Fee",
        "description": (
            "Platform and connectivity fee for depositions conducted via "
            "videoconference (Zoom, Teams, Veritext Connect, etc.)."
        ),
    },
    {
        "code": "CR.DEPO.TRAVEL_TRANSPORT",
        "domain": "CR",
        "service_item": "DEPO",
        "billing_component": "TRAVEL_TRANSPORT",
        "unit_model": "actual",
        "label": "Court Reporter Travel — Transportation",
        "description": "Actual transportation cost for court reporter travel to deposition location.",
    },
    {
        "code": "CR.DEPO.MILEAGE",
        "domain": "CR",
        "service_item": "DEPO",
        "billing_component": "MILEAGE",
        "unit_model": "per_mile",
        "label": "Court Reporter Travel — Mileage",
        "description": "Mileage reimbursement for court reporter driving to deposition.",
    },
    {
        "code": "CR.CANCEL.CANCEL_FEE",
        "domain": "CR",
        "service_item": "CANCEL",
        "billing_component": "CANCEL_FEE",
        "unit_model": "flat_fee",
        "label": "Cancellation Fee",
        "description": (
            "Fee charged when a scheduled deposition is cancelled within "
            "the contract-specified notice window."
        ),
    },
    {
        "code": "CR.NO_SHOW.NO_SHOW_FEE",
        "domain": "CR",
        "service_item": "NO_SHOW",
        "billing_component": "NO_SHOW_FEE",
        "unit_model": "flat_fee",
        "label": "No-Show Fee",
        "description": "Fee charged when a deposition witness fails to appear.",
    },
    # ══════════════════════════════════════════════════════════════════════════
    # INV — Investigation & Surveillance
    # ══════════════════════════════════════════════════════════════════════════
    {
        "code": "INV.SURVEILLANCE.PROF_FEE",
        "domain": "INV",
        "service_item": "SURVEILLANCE",
        "billing_component": "PROF_FEE",
        "unit_model": "per_hour",
        "label": "Investigation Surveillance — Professional Fee",
        "description": "Hourly fee for claimant surveillance services.",
    },
    {
        "code": "INV.SURVEILLANCE.TRAVEL_TRANSPORT",
        "domain": "INV",
        "service_item": "SURVEILLANCE",
        "billing_component": "TRAVEL_TRANSPORT",
        "unit_model": "actual",
        "label": "Investigation Surveillance — Transportation",
        "description": "Actual transportation costs for surveillance investigators.",
    },
    {
        "code": "INV.SURVEILLANCE.MILEAGE",
        "domain": "INV",
        "service_item": "SURVEILLANCE",
        "billing_component": "MILEAGE",
        "unit_model": "per_mile",
        "label": "Investigation Surveillance — Mileage",
        "description": "Mileage for surveillance investigators.",
    },
    {
        "code": "INV.STATEMENT.PROF_FEE",
        "domain": "INV",
        "service_item": "STATEMENT",
        "billing_component": "PROF_FEE",
        "unit_model": "per_occurrence",
        "label": "Investigation Recorded Statement — Professional Fee",
        "description": "Fee for obtaining a recorded statement from claimant, witness, or involved party.",
    },
    {
        "code": "INV.BACKGROUND_ASSET.PROF_FEE",
        "domain": "INV",
        "service_item": "BACKGROUND_ASSET",
        "billing_component": "PROF_FEE",
        "unit_model": "per_report",
        "label": "Investigation Background / Asset Search — Professional Fee",
        "description": "Fee for background check, asset search, or public records investigation.",
    },
    {
        "code": "INV.AOE_COE.PROF_FEE",
        "domain": "INV",
        "service_item": "AOE_COE",
        "billing_component": "PROF_FEE",
        "unit_model": "per_file",
        "label": "Investigation AOE/COE Investigation — Professional Fee",
        "description": "Arising Out of Employment / Course of Employment investigation.",
    },
    {
        "code": "INV.SKIP_TRACE.PROF_FEE",
        "domain": "INV",
        "service_item": "SKIP_TRACE",
        "billing_component": "PROF_FEE",
        "unit_model": "per_occurrence",
        "label": "Investigation Skip Trace — Professional Fee",
        "description": "Fee for locating a claimant or witness whose address is unknown.",
    },
    # ══════════════════════════════════════════════════════════════════════════
    # DRNE — Drone & Aerial Inspection
    # Physical drone deployments for roof, structural, and site documentation.
    # Distinct from VIRT (no-visit digital services) and INSP (ground inspections).
    # ══════════════════════════════════════════════════════════════════════════
    {
        "code": "DRNE.ROOF_SURVEY.FLAT_FEE",
        "domain": "DRNE",
        "service_item": "ROOF_SURVEY",
        "billing_component": "FLAT_FEE",
        "unit_model": "per_occurrence",
        "label": "Drone Roof Survey",
        "description": (
            "Aerial drone survey of a roof structure to document condition, "
            "damage extent, and measurement data."
        ),
    },
    {
        "code": "DRNE.AERIAL_PHOTO.FLAT_FEE",
        "domain": "DRNE",
        "service_item": "AERIAL_PHOTO",
        "billing_component": "FLAT_FEE",
        "unit_model": "per_occurrence",
        "label": "Aerial Photography & Documentation",
        "description": (
            "Drone-captured still photography of a property for damage documentation, "
            "site orientation, or pre/post loss comparison."
        ),
    },
    {
        "code": "DRNE.VIDEO.FLAT_FEE",
        "domain": "DRNE",
        "service_item": "VIDEO",
        "billing_component": "FLAT_FEE",
        "unit_model": "per_occurrence",
        "label": "Aerial Video Documentation",
        "description": "Drone video footage of a loss site for claim file documentation.",
    },
    {
        "code": "DRNE.THERMAL.FLAT_FEE",
        "domain": "DRNE",
        "service_item": "THERMAL",
        "billing_component": "FLAT_FEE",
        "unit_model": "per_occurrence",
        "label": "Thermal Imaging Survey",
        "description": (
            "Infrared/thermal drone survey to detect moisture intrusion, "
            "heat loss, or hidden damage not visible in standard photography."
        ),
    },
    {
        "code": "DRNE.CANCEL.CANCEL_FEE",
        "domain": "DRNE",
        "service_item": "CANCEL",
        "billing_component": "CANCEL_FEE",
        "unit_model": "flat_fee",
        "label": "Cancellation Fee",
        "description": (
            "Fee charged when a scheduled drone flight is cancelled within "
            "the contract-specified notice window."
        ),
    },
    {
        "code": "DRNE.TRIP_CHARGE.TRIP_FEE",
        "domain": "DRNE",
        "service_item": "TRIP_CHARGE",
        "billing_component": "TRIP_FEE",
        "unit_model": "flat_fee",
        "label": "Trip Charge / No Access",
        "description": (
            "Fee charged when the drone operator is dispatched and arrives on site "
            "but cannot complete the flight (FAA restriction, unsafe weather, access denied)."
        ),
    },
    # ══════════════════════════════════════════════════════════════════════════
    # APPR — Property Appraisal & Umpire
    # Used in contested property claims under the insurance appraisal clause.
    # ══════════════════════════════════════════════════════════════════════════
    {
        "code": "APPR.PROPERTY_APPRAISAL.PROF_FEE",
        "domain": "APPR",
        "service_item": "PROPERTY_APPRAISAL",
        "billing_component": "PROF_FEE",
        "unit_model": "flat_fee",
        "label": "Property Appraisal — Professional Fee",
        "description": (
            "Fee for an independent property appraisal to establish the value of "
            "loss or repair cost as part of the insurance appraisal clause process."
        ),
    },
    {
        "code": "APPR.UMPIRE.PROF_FEE",
        "domain": "APPR",
        "service_item": "UMPIRE",
        "billing_component": "PROF_FEE",
        "unit_model": "flat_fee",
        "label": "Umpire Services — Professional Fee",
        "description": (
            "Fee for a neutral umpire to resolve a disputed appraisal when "
            "the carrier and insured appraisers cannot agree on loss amount."
        ),
    },
    {
        "code": "APPR.SITE_VISIT.FLAT_FEE",
        "domain": "APPR",
        "service_item": "SITE_VISIT",
        "billing_component": "FLAT_FEE",
        "unit_model": "per_occurrence",
        "label": "Appraisal Site Visit",
        "description": "Fee for an appraiser or umpire site visit to inspect the loss property.",
    },
    {
        "code": "APPR.CONTENTS_INVENTORY.PROF_FEE",
        "domain": "APPR",
        "service_item": "CONTENTS_INVENTORY",
        "billing_component": "PROF_FEE",
        "unit_model": "per_file",
        "label": "Contents Inventory & Valuation",
        "description": (
            "Professional inventory and valuation of personal property contents "
            "for homeowners or renters insurance claims."
        ),
    },
    {
        "code": "APPR.ADMIN.FILING_FEE",
        "domain": "APPR",
        "service_item": "ADMIN",
        "billing_component": "FILING_FEE",
        "unit_model": "flat_fee",
        "label": "Appraisal Administrative / Filing Fee",
        "description": "Administrative fee for appraisal process coordination and documentation.",
    },
    # ══════════════════════════════════════════════════════════════════════════
    # XDOMAIN — Cross-Domain (Pass-Through, Misc Admin)
    # ══════════════════════════════════════════════════════════════════════════
    {
        "code": "XDOMAIN.PASS_THROUGH.THIRD_PARTY_COST",
        "domain": "XDOMAIN",
        "service_item": "PASS_THROUGH",
        "billing_component": "THIRD_PARTY_COST",
        "unit_model": "actual",
        "label": "Pass-Through Third-Party Cost",
        "description": (
            "Actual third-party cost paid by vendor on behalf of carrier "
            "(e.g., court filing fees, expert witness subpoena fees). "
            "Requires supporting receipt."
        ),
    },
    {
        "code": "XDOMAIN.ADMIN_MISC.ADMIN_FEE",
        "domain": "XDOMAIN",
        "service_item": "ADMIN_MISC",
        "billing_component": "ADMIN_FEE",
        "unit_model": "flat_fee",
        "label": "Miscellaneous Administrative Fee",
        "description": (
            "Administrative fee not classifiable under a specific service domain. "
            "Requires carrier pre-approval."
        ),
    },
]
