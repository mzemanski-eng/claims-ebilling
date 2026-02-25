"""
Claims UTMSB Taxonomy — canonical code definitions.

Format: each entry is a dict that maps 1:1 to TaxonomyItem columns.
These are the ground-truth definitions; the DB is seeded from this file.

Code format: {DOMAIN}.{SERVICE_ITEM}.{COMPONENT}

Domains:
  IME     Independent Medical Examination
  ENG     Engineering & Forensic Services
  IA      Independent Adjusting
  INV     Investigation & Surveillance
  REC     Record Retrieval & Management
  XDOMAIN Cross-domain (pass-through, misc admin)
"""

TAXONOMY: list[dict] = [
    # ══════════════════════════════════════════════════════════════════════════
    # IME — Independent Medical Examination
    # ══════════════════════════════════════════════════════════════════════════
    {
        "code": "IME.PHY_EXAM.PROF_FEE",
        "domain": "IME",
        "service_item": "PHY_EXAM",
        "billing_component": "PROF_FEE",
        "unit_model": "per_report",
        "label": "IME Physician Examination — Professional Fee",
        "description": (
            "Fee for a single-specialty independent medical examination by a "
            "physician. Includes examination, medical records review, and written report."
        ),
    },
    {
        "code": "IME.PHY_EXAM.TRAVEL_TRANSPORT",
        "domain": "IME",
        "service_item": "PHY_EXAM",
        "billing_component": "TRAVEL_TRANSPORT",
        "unit_model": "actual",
        "label": "IME Physician Examination — Transportation",
        "description": "Actual transportation cost (airfare, train, taxi) for physician travel.",
    },
    {
        "code": "IME.PHY_EXAM.TRAVEL_LODGING",
        "domain": "IME",
        "service_item": "PHY_EXAM",
        "billing_component": "TRAVEL_LODGING",
        "unit_model": "per_night",
        "label": "IME Physician Examination — Lodging",
        "description": "Hotel/lodging for physician overnight travel.",
    },
    {
        "code": "IME.PHY_EXAM.TRAVEL_MEALS",
        "domain": "IME",
        "service_item": "PHY_EXAM",
        "billing_component": "TRAVEL_MEALS",
        "unit_model": "per_diem",
        "label": "IME Physician Examination — Meals & Per Diem",
        "description": "Meal per diem for physician travel days.",
    },
    {
        "code": "IME.PHY_EXAM.MILEAGE",
        "domain": "IME",
        "service_item": "PHY_EXAM",
        "billing_component": "MILEAGE",
        "unit_model": "per_mile",
        "label": "IME Physician Examination — Mileage",
        "description": "Mileage reimbursement for physician driving to examination location.",
    },
    {
        "code": "IME.MULTI_SPECIALTY.PROF_FEE",
        "domain": "IME",
        "service_item": "MULTI_SPECIALTY",
        "billing_component": "PROF_FEE",
        "unit_model": "per_report",
        "label": "IME Multi-Specialty Panel — Professional Fee",
        "description": "Fee for IME involving two or more specialty physicians in one session.",
    },
    {
        "code": "IME.RECORDS_REVIEW.PROF_FEE",
        "domain": "IME",
        "service_item": "RECORDS_REVIEW",
        "billing_component": "PROF_FEE",
        "unit_model": "per_report",
        "label": "IME Records Review (No Exam) — Professional Fee",
        "description": "Physician review of medical records without a physical examination.",
    },
    {
        "code": "IME.ADDENDUM.PROF_FEE",
        "domain": "IME",
        "service_item": "ADDENDUM",
        "billing_component": "PROF_FEE",
        "unit_model": "per_report",
        "label": "IME Addendum Report — Professional Fee",
        "description": "Supplemental report responding to additional records or questions after initial IME.",
    },
    {
        "code": "IME.PEER_REVIEW.PROF_FEE",
        "domain": "IME",
        "service_item": "PEER_REVIEW",
        "billing_component": "PROF_FEE",
        "unit_model": "per_report",
        "label": "IME Peer Review — Professional Fee",
        "description": "Physician review of another provider's treatment plan or records.",
    },
    {
        "code": "IME.CANCELLATION.CANCEL_FEE",
        "domain": "IME",
        "service_item": "CANCELLATION",
        "billing_component": "CANCEL_FEE",
        "unit_model": "flat_fee",
        "label": "IME Cancellation Fee",
        "description": "Fee charged when an IME is cancelled within the contract-specified notice window.",
    },
    {
        "code": "IME.NO_SHOW.NO_SHOW_FEE",
        "domain": "IME",
        "service_item": "NO_SHOW",
        "billing_component": "NO_SHOW_FEE",
        "unit_model": "flat_fee",
        "label": "IME No-Show Fee",
        "description": "Fee charged when the claimant fails to appear for a scheduled IME.",
    },
    {
        "code": "IME.ADMIN.SCHEDULING_FEE",
        "domain": "IME",
        "service_item": "ADMIN",
        "billing_component": "SCHEDULING_FEE",
        "unit_model": "flat_fee",
        "label": "IME Administrative / Scheduling Fee",
        "description": "Administrative fee for IME scheduling and coordination services.",
    },
    # ══════════════════════════════════════════════════════════════════════════
    # ENG — Engineering & Forensic Services
    # ══════════════════════════════════════════════════════════════════════════
    {
        "code": "ENG.PROPERTY_INSPECT.PROF_FEE",
        "domain": "ENG",
        "service_item": "PROPERTY_INSPECT",
        "billing_component": "PROF_FEE",
        "unit_model": "per_file",
        "label": "Engineering Property Inspection — Professional Fee",
        "description": "On-site property inspection by a licensed engineer or inspector.",
    },
    {
        "code": "ENG.PROPERTY_INSPECT.TRAVEL_TRANSPORT",
        "domain": "ENG",
        "service_item": "PROPERTY_INSPECT",
        "billing_component": "TRAVEL_TRANSPORT",
        "unit_model": "actual",
        "label": "Engineering Property Inspection — Transportation",
        "description": "Actual transportation cost for engineer travel to inspection site.",
    },
    {
        "code": "ENG.PROPERTY_INSPECT.MILEAGE",
        "domain": "ENG",
        "service_item": "PROPERTY_INSPECT",
        "billing_component": "MILEAGE",
        "unit_model": "per_mile",
        "label": "Engineering Property Inspection — Mileage",
        "description": "Mileage reimbursement for engineer driving to inspection site.",
    },
    {
        "code": "ENG.CAUSE_ORIGIN.PROF_FEE",
        "domain": "ENG",
        "service_item": "CAUSE_ORIGIN",
        "billing_component": "PROF_FEE",
        "unit_model": "per_file",
        "label": "Engineering Cause & Origin Investigation — Professional Fee",
        "description": "Investigation to determine the cause and origin of loss (fire, water, mechanical failure, etc.).",
    },
    {
        "code": "ENG.STRUCTURAL_ASSESS.PROF_FEE",
        "domain": "ENG",
        "service_item": "STRUCTURAL_ASSESS",
        "billing_component": "PROF_FEE",
        "unit_model": "per_file",
        "label": "Engineering Structural Assessment — Professional Fee",
        "description": "Assessment of structural integrity, damage, or construction defect.",
    },
    {
        "code": "ENG.EXPERT_REPORT.PROF_FEE",
        "domain": "ENG",
        "service_item": "EXPERT_REPORT",
        "billing_component": "PROF_FEE",
        "unit_model": "per_report",
        "label": "Engineering Expert Report — Professional Fee",
        "description": "Formal written expert report for litigation or claim resolution.",
    },
    {
        "code": "ENG.FILE_REVIEW.PROF_FEE",
        "domain": "ENG",
        "service_item": "FILE_REVIEW",
        "billing_component": "PROF_FEE",
        "unit_model": "per_hour",
        "label": "Engineering File Review — Professional Fee",
        "description": "Hourly fee for engineer review of documents, photos, or records without site visit.",
    },
    {
        "code": "ENG.SUPPLEMENTAL_INSPECT.PROF_FEE",
        "domain": "ENG",
        "service_item": "SUPPLEMENTAL_INSPECT",
        "billing_component": "PROF_FEE",
        "unit_model": "per_file",
        "label": "Engineering Supplemental Inspection — Professional Fee",
        "description": "Follow-up inspection after initial report (re-inspection, supplement, or reinspection).",
    },
    {
        "code": "ENG.TESTIMONY_DEPO.PROF_FEE",
        "domain": "ENG",
        "service_item": "TESTIMONY_DEPO",
        "billing_component": "PROF_FEE",
        "unit_model": "per_hour",
        "label": "Engineering Expert Testimony / Deposition — Professional Fee",
        "description": "Hourly fee for deposition or trial testimony by engineering expert.",
    },
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
