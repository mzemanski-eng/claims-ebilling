"""
Base classes, shared dataclasses, rate constants, and helpers for the
synthetic data generation agents.
"""

from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

import anthropic
from sqlalchemy.orm import Session

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.settings import settings

# ── US States ────────────────────────────────────────────────────────────────

US_STATES = [
    "AL", "AZ", "CA", "CO", "FL", "GA", "IL", "IN", "KY", "LA",
    "MD", "MI", "MN", "MO", "NC", "NJ", "NY", "OH", "OK", "OR",
    "PA", "TN", "TX", "VA", "WA", "WI",
]

# ── Supplier / domain plan ────────────────────────────────────────────────────

SUPPLIER_DOMAIN_PLAN: list[dict] = [
    {"tax_id": "SEED-IA-001",   "domains": ["IA",   "XDOMAIN"], "primary": "IA"},
    {"tax_id": "SEED-ENG-002",  "domains": ["ENG",  "ENG"],     "primary": "ENG"},
    {"tax_id": "SEED-CR-003",   "domains": ["CR",   "INV"],     "primary": "CR"},
    {"tax_id": "SEED-DRNE-004", "domains": ["DRNE", "INSP"],    "primary": "DRNE"},
    {"tax_id": "SEED-LA-005",   "domains": ["LA",   "VIRT"],    "primary": "LA"},
    {"tax_id": "SEED-REC-006",  "domains": ["REC",  "APPR"],    "primary": "REC"},
]

# ── Rate ranges: {taxonomy_code: (min_rate, max_rate, rate_type)} ────────────
# rate_type: flat | hourly | mileage | per_diem

DOMAIN_RATE_RANGES: dict[str, tuple[Decimal, Decimal, str]] = {
    # ── IA — Independent Adjusting ─────────────────────────────────────────
    "IA.FIELD_ASSIGN.PROF_FEE":          (Decimal("400"), Decimal("650"),  "per_diem"),
    "IA.FIELD_ASSIGN.MILEAGE":           (Decimal("0.67"), Decimal("0.67"), "mileage"),
    "IA.FIELD_ASSIGN.TRAVEL_LODGING":    (Decimal("135"), Decimal("195"),  "flat"),
    "IA.FIELD_ASSIGN.TRAVEL_TRANSPORT":  (Decimal("150"), Decimal("400"),  "flat"),
    "IA.FIELD_ASSIGN.TRAVEL_MEALS":      (Decimal("55"),  Decimal("75"),   "flat"),
    "IA.DESK_ASSIGN.PROF_FEE":           (Decimal("175"), Decimal("325"),  "flat"),
    "IA.CAT_ASSIGN.PROF_FEE":            (Decimal("425"), Decimal("700"),  "per_diem"),
    "IA.PHOTO_DOC.PROF_FEE":             (Decimal("125"), Decimal("225"),  "flat"),
    "IA.SUPPLEMENT_HANDLING.PROF_FEE":   (Decimal("75"),  Decimal("150"),  "flat"),
    "IA.ADMIN.FILE_OPEN_FEE":            (Decimal("25"),  Decimal("50"),   "flat"),
    # ── ENG — Engineering (per hour, by level) ─────────────────────────────
    "ENG.*.L1": (Decimal("275"), Decimal("375"), "hourly"),
    "ENG.*.L2": (Decimal("200"), Decimal("275"), "hourly"),
    "ENG.*.L3": (Decimal("150"), Decimal("200"), "hourly"),
    "ENG.*.L4": (Decimal("110"), Decimal("150"), "hourly"),
    "ENG.*.L5": (Decimal("75"),  Decimal("110"), "hourly"),
    "ENG.*.L6": (Decimal("55"),  Decimal("85"),  "hourly"),
    # ── REC — Record Retrieval ─────────────────────────────────────────────
    "REC.MED_RECORDS.RETRIEVAL_FEE":       (Decimal("20"),   Decimal("45"),   "flat"),
    "REC.MED_RECORDS.COPY_REPRO":          (Decimal("0.15"), Decimal("0.50"), "flat"),
    "REC.MED_RECORDS.RUSH_PREMIUM":        (Decimal("35"),   Decimal("75"),   "flat"),
    "REC.MED_RECORDS.POSTAGE_COURIER":     (Decimal("8"),    Decimal("25"),   "flat"),
    "REC.MED_RECORDS.CERT_COPY_FEE":       (Decimal("25"),   Decimal("55"),   "flat"),
    "REC.EMPLOYMENT_RECORDS.RETRIEVAL_FEE":(Decimal("25"),   Decimal("55"),   "flat"),
    "REC.LEGAL_RECORDS.RETRIEVAL_FEE":     (Decimal("30"),   Decimal("65"),   "flat"),
    "REC.ADMIN.PROCESSING_FEE":            (Decimal("15"),   Decimal("35"),   "flat"),
    # ── LA — Ladder Assist ─────────────────────────────────────────────────
    "LA.LADDER_ACCESS.FLAT_FEE":        (Decimal("100"), Decimal("165"), "flat"),
    "LA.ROOF_INSPECT.FLAT_FEE":         (Decimal("150"), Decimal("225"), "flat"),
    "LA.ROOF_INSPECT_HARNESS.FLAT_FEE": (Decimal("200"), Decimal("275"), "flat"),
    "LA.TARP_COVER.FLAT_FEE":           (Decimal("275"), Decimal("450"), "flat"),
    "LA.CANCEL.CANCEL_FEE":             (Decimal("65"),  Decimal("100"), "flat"),
    "LA.TRIP_CHARGE.TRIP_FEE":          (Decimal("55"),  Decimal("85"),  "flat"),
    # ── INSP — Property Inspections ────────────────────────────────────────
    "INSP.BASIC.FLAT_FEE":              (Decimal("95"),  Decimal("175"), "flat"),
    "INSP.REINSPECT.FLAT_FEE":          (Decimal("85"),  Decimal("150"), "flat"),
    "INSP.EXTERIOR.FLAT_FEE":           (Decimal("75"),  Decimal("125"), "flat"),
    "INSP.INTERIOR.FLAT_FEE":           (Decimal("125"), Decimal("200"), "flat"),
    "INSP.DAMAGE_ASSESS.FLAT_FEE":      (Decimal("150"), Decimal("275"), "flat"),
    "INSP.SUPPLEMENT_REVIEW.FLAT_FEE":  (Decimal("75"),  Decimal("125"), "flat"),
    "INSP.PHOTO_DOC.FLAT_FEE":          (Decimal("65"),  Decimal("115"), "flat"),
    "INSP.DISPUTE_REINSPECT.FLAT_FEE":  (Decimal("95"),  Decimal("175"), "flat"),
    "INSP.CANCEL.CANCEL_FEE":           (Decimal("45"),  Decimal("75"),  "flat"),
    "INSP.TRIP_CHARGE.TRIP_FEE":        (Decimal("40"),  Decimal("65"),  "flat"),
    # ── VIRT — Virtual Assist ─────────────────────────────────────────────
    "VIRT.GUIDED.FLAT_FEE":             (Decimal("75"),  Decimal("150"), "flat"),
    "VIRT.SELF_SERVICE.FLAT_FEE":       (Decimal("45"),  Decimal("95"),  "flat"),
    "VIRT.AI_SCOPE.FLAT_FEE":           (Decimal("85"),  Decimal("165"), "flat"),
    "VIRT.AERIAL_ANALYSIS.FLAT_FEE":    (Decimal("125"), Decimal("225"), "flat"),
    "VIRT.PHOTO_AI.FLAT_FEE":           (Decimal("55"),  Decimal("115"), "flat"),
    "VIRT.CANCEL.CANCEL_FEE":           (Decimal("35"),  Decimal("65"),  "flat"),
    # ── CR — Court Reporting ───────────────────────────────────────────────
    "CR.DEPO.APPEARANCE_FEE":           (Decimal("75"),  Decimal("150"), "flat"),
    "CR.DEPO.TRANSCRIPT":               (Decimal("3.50"), Decimal("5.50"), "flat"),
    "CR.DEPO.COPY_FEE":                 (Decimal("1.00"), Decimal("2.50"), "flat"),
    "CR.DEPO.VIDEOGRAPHY":              (Decimal("95"),  Decimal("175"), "hourly"),
    "CR.DEPO.RUSH_TRANSCRIPT":          (Decimal("1.50"), Decimal("3.00"), "flat"),
    "CR.DEPO.EXHIBIT_HANDLING":         (Decimal("35"),  Decimal("75"),  "flat"),
    "CR.DEPO.REMOTE_FEE":               (Decimal("45"),  Decimal("95"),  "flat"),
    "CR.DEPO.TRAVEL_TRANSPORT":         (Decimal("75"),  Decimal("250"), "flat"),
    "CR.DEPO.MILEAGE":                  (Decimal("0.67"), Decimal("0.67"), "mileage"),
    "CR.CANCEL.CANCEL_FEE":             (Decimal("75"),  Decimal("125"), "flat"),
    "CR.NO_SHOW.NO_SHOW_FEE":           (Decimal("85"),  Decimal("150"), "flat"),
    # ── INV — Investigation ────────────────────────────────────────────────
    "INV.SURVEILLANCE.PROF_FEE":        (Decimal("85"),  Decimal("145"), "hourly"),
    "INV.SURVEILLANCE.TRAVEL_TRANSPORT":(Decimal("50"),  Decimal("200"), "flat"),
    "INV.SURVEILLANCE.MILEAGE":         (Decimal("0.67"), Decimal("0.67"), "mileage"),
    "INV.STATEMENT.PROF_FEE":           (Decimal("175"), Decimal("275"), "flat"),
    "INV.BACKGROUND_ASSET.PROF_FEE":    (Decimal("125"), Decimal("225"), "flat"),
    "INV.AOE_COE.PROF_FEE":             (Decimal("350"), Decimal("550"), "flat"),
    "INV.SKIP_TRACE.PROF_FEE":          (Decimal("75"),  Decimal("150"), "flat"),
    # ── DRNE — Drone & Aerial ─────────────────────────────────────────────
    "DRNE.ROOF_SURVEY.FLAT_FEE":        (Decimal("175"), Decimal("325"), "flat"),
    "DRNE.AERIAL_PHOTO.FLAT_FEE":       (Decimal("150"), Decimal("275"), "flat"),
    "DRNE.VIDEO.FLAT_FEE":              (Decimal("200"), Decimal("350"), "flat"),
    "DRNE.THERMAL.FLAT_FEE":            (Decimal("250"), Decimal("400"), "flat"),
    "DRNE.CANCEL.CANCEL_FEE":           (Decimal("75"),  Decimal("125"), "flat"),
    "DRNE.TRIP_CHARGE.TRIP_FEE":        (Decimal("55"),  Decimal("95"),  "flat"),
    # ── APPR — Property Appraisal ─────────────────────────────────────────
    "APPR.PROPERTY_APPRAISAL.PROF_FEE": (Decimal("750"), Decimal("2500"), "flat"),
    "APPR.UMPIRE.PROF_FEE":             (Decimal("1500"), Decimal("5000"), "flat"),
    "APPR.SITE_VISIT.FLAT_FEE":         (Decimal("350"), Decimal("650"),  "flat"),
    "APPR.CONTENTS_INVENTORY.PROF_FEE": (Decimal("400"), Decimal("1200"), "flat"),
    "APPR.ADMIN.FILING_FEE":            (Decimal("50"),  Decimal("150"),  "flat"),
    # ── XDOMAIN ────────────────────────────────────────────────────────────
    "XDOMAIN.PASS_THROUGH.THIRD_PARTY_COST": (Decimal("50"),  Decimal("500"), "flat"),
    "XDOMAIN.ADMIN_MISC.ADMIN_FEE":          (Decimal("25"),  Decimal("150"), "flat"),
}

# Domain → list of taxonomy codes to use for rate cards
DOMAIN_CODES: dict[str, list[str]] = {
    "IA": [
        "IA.FIELD_ASSIGN.PROF_FEE",
        "IA.FIELD_ASSIGN.MILEAGE",
        "IA.FIELD_ASSIGN.TRAVEL_LODGING",
        "IA.FIELD_ASSIGN.TRAVEL_TRANSPORT",
        "IA.FIELD_ASSIGN.TRAVEL_MEALS",
        "IA.DESK_ASSIGN.PROF_FEE",
        "IA.CAT_ASSIGN.PROF_FEE",
        "IA.PHOTO_DOC.PROF_FEE",
        "IA.SUPPLEMENT_HANDLING.PROF_FEE",
        "IA.ADMIN.FILE_OPEN_FEE",
    ],
    "ENG": [
        # Contract 0 — FOC, EA, DA, RPT, AOS + levels
        "ENG.FOC.L1", "ENG.FOC.L2", "ENG.FOC.L3",
        "ENG.EA.L1",  "ENG.EA.L2",  "ENG.EA.L3",
        "ENG.DA.L2",  "ENG.DA.L3",
        "ENG.RPT.L3", "ENG.RPT.L5",
        "ENG.AOS.L6",
        "ENG.EWD.L1",
    ],
    "ENG_CONTRACT2": [
        # Contract 1 — different service mix: AAR, CT, FA, CAO, PM
        "ENG.AAR.L1", "ENG.AAR.L2",
        "ENG.CT.L2",  "ENG.CT.L3",
        "ENG.FA.L1",  "ENG.FA.L2",
        "ENG.CAO.L1", "ENG.CAO.L2",
        "ENG.PM.L3",  "ENG.PM.L4",
        "ENG.AOS.L6",
    ],
    "CR": [
        "CR.DEPO.APPEARANCE_FEE",
        "CR.DEPO.TRANSCRIPT",
        "CR.DEPO.COPY_FEE",
        "CR.DEPO.VIDEOGRAPHY",
        "CR.DEPO.RUSH_TRANSCRIPT",
        "CR.DEPO.EXHIBIT_HANDLING",
        "CR.DEPO.REMOTE_FEE",
        "CR.DEPO.TRAVEL_TRANSPORT",
        "CR.DEPO.MILEAGE",
        "CR.CANCEL.CANCEL_FEE",
        "CR.NO_SHOW.NO_SHOW_FEE",
    ],
    "INV": [
        "INV.SURVEILLANCE.PROF_FEE",
        "INV.SURVEILLANCE.TRAVEL_TRANSPORT",
        "INV.SURVEILLANCE.MILEAGE",
        "INV.STATEMENT.PROF_FEE",
        "INV.BACKGROUND_ASSET.PROF_FEE",
        "INV.AOE_COE.PROF_FEE",
        "INV.SKIP_TRACE.PROF_FEE",
    ],
    "DRNE": [
        "DRNE.ROOF_SURVEY.FLAT_FEE",
        "DRNE.AERIAL_PHOTO.FLAT_FEE",
        "DRNE.VIDEO.FLAT_FEE",
        "DRNE.THERMAL.FLAT_FEE",
        "DRNE.CANCEL.CANCEL_FEE",
        "DRNE.TRIP_CHARGE.TRIP_FEE",
    ],
    "INSP": [
        "INSP.BASIC.FLAT_FEE",
        "INSP.REINSPECT.FLAT_FEE",
        "INSP.EXTERIOR.FLAT_FEE",
        "INSP.INTERIOR.FLAT_FEE",
        "INSP.DAMAGE_ASSESS.FLAT_FEE",
        "INSP.SUPPLEMENT_REVIEW.FLAT_FEE",
        "INSP.PHOTO_DOC.FLAT_FEE",
        "INSP.DISPUTE_REINSPECT.FLAT_FEE",
        "INSP.CANCEL.CANCEL_FEE",
        "INSP.TRIP_CHARGE.TRIP_FEE",
    ],
    "LA": [
        "LA.LADDER_ACCESS.FLAT_FEE",
        "LA.ROOF_INSPECT.FLAT_FEE",
        "LA.ROOF_INSPECT_HARNESS.FLAT_FEE",
        "LA.TARP_COVER.FLAT_FEE",
        "LA.CANCEL.CANCEL_FEE",
        "LA.TRIP_CHARGE.TRIP_FEE",
    ],
    "VIRT": [
        "VIRT.GUIDED.FLAT_FEE",
        "VIRT.SELF_SERVICE.FLAT_FEE",
        "VIRT.AI_SCOPE.FLAT_FEE",
        "VIRT.AERIAL_ANALYSIS.FLAT_FEE",
        "VIRT.PHOTO_AI.FLAT_FEE",
        "VIRT.CANCEL.CANCEL_FEE",
    ],
    "REC": [
        "REC.MED_RECORDS.RETRIEVAL_FEE",
        "REC.MED_RECORDS.COPY_REPRO",
        "REC.MED_RECORDS.RUSH_PREMIUM",
        "REC.MED_RECORDS.POSTAGE_COURIER",
        "REC.MED_RECORDS.CERT_COPY_FEE",
        "REC.EMPLOYMENT_RECORDS.RETRIEVAL_FEE",
        "REC.LEGAL_RECORDS.RETRIEVAL_FEE",
        "REC.ADMIN.PROCESSING_FEE",
    ],
    "APPR": [
        "APPR.PROPERTY_APPRAISAL.PROF_FEE",
        "APPR.UMPIRE.PROF_FEE",
        "APPR.SITE_VISIT.FLAT_FEE",
        "APPR.CONTENTS_INVENTORY.PROF_FEE",
        "APPR.ADMIN.FILING_FEE",
    ],
    "XDOMAIN": [
        "XDOMAIN.PASS_THROUGH.THIRD_PARTY_COST",
        "XDOMAIN.ADMIN_MISC.ADMIN_FEE",
    ],
}

# ── Quantity by unit_model ────────────────────────────────────────────────────

def random_quantity(taxonomy_code: str, rate_type: str) -> Decimal:
    """Return a realistic quantity for a line item based on taxonomy code."""
    code_lower = taxonomy_code.lower()
    if "mileage" in code_lower or rate_type == "mileage":
        return Decimal(str(random.randint(15, 85)))
    if "transcript" in code_lower:
        return Decimal(str(random.randint(50, 280)))
    if "copy_fee" in code_lower:
        return Decimal(str(random.randint(10, 120)))
    if rate_type in ("hourly",):
        # Round to nearest 0.25
        hours = random.randint(2, 32) * 0.25  # 0.5 - 8.0
        return Decimal(str(hours))
    if "videography" in code_lower:
        hours = random.randint(2, 8) * 0.25
        return Decimal(str(hours))
    # Default: single occurrence
    return Decimal("1")


# ── Rate helpers ──────────────────────────────────────────────────────────────

def pick_rate(taxonomy_code: str, contract_idx: int = 0) -> tuple[Decimal, str]:
    """
    Return (contracted_rate, rate_type) for a taxonomy code.
    contract_idx=0 → lower end; contract_idx=1 → higher end.
    Applies wildcard match for ENG level codes.
    """
    # Direct match
    if taxonomy_code in DOMAIN_RATE_RANGES:
        lo, hi, rate_type = DOMAIN_RATE_RANGES[taxonomy_code]
    else:
        # Try ENG level wildcard: ENG.{SVC}.L{N}
        parts = taxonomy_code.split(".")
        if len(parts) == 3 and parts[0] == "ENG":
            wildcard_key = f"ENG.*.{parts[2]}"
            if wildcard_key in DOMAIN_RATE_RANGES:
                lo, hi, rate_type = DOMAIN_RATE_RANGES[wildcard_key]
            else:
                lo, hi, rate_type = Decimal("100"), Decimal("200"), "flat"
        else:
            lo, hi, rate_type = Decimal("100"), Decimal("200"), "flat"

    # Pick a rate: contract 0 = lower 40%, contract 1 = upper 40%
    spread = hi - lo
    if contract_idx == 0:
        midpoint = lo + spread * Decimal("0.3")
    else:
        midpoint = lo + spread * Decimal("0.7")

    # Round to 2 decimal places
    rate = midpoint.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return rate, rate_type


def calc_amount(rate: Decimal, quantity: Decimal) -> Decimal:
    """rate × quantity, rounded to 2dp."""
    return (rate * quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ── Random helpers ────────────────────────────────────────────────────────────

def random_claim_number() -> str:
    year = random.choice([2024, 2025, 2026])
    seq = random.randint(10000, 99999)
    return f"CLM-{year}-{seq}"


def random_invoice_number(domain_prefix: str, seq: int) -> str:
    prefix = domain_prefix[:3].upper()
    year = random.choice([2024, 2025])
    return f"{prefix}-{year}-{seq:04d}"


def random_service_date(invoice_date: date) -> date:
    """Service happened 3–15 days before invoice date."""
    delta = random.randint(3, 15)
    return invoice_date - timedelta(days=delta)


def random_invoice_date(contract_idx: int) -> date:
    """
    contract_idx 0 → 2024 dates (expired contract)
    contract_idx 1 → 2025–2026 dates (active contract)
    """
    if contract_idx == 0:
        # Random date in 2024
        start = date(2024, 1, 15)
        end = date(2024, 12, 15)
    else:
        # Random date 2025-01-01 to today
        start = date(2025, 1, 15)
        end = date(2026, 3, 20)
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


# ── Spec dataclasses ──────────────────────────────────────────────────────────

@dataclass
class RateCardSpec:
    taxonomy_code: str
    contracted_rate: Decimal
    rate_type: str
    max_units: Optional[Decimal]
    is_all_inclusive: bool
    effective_from: date
    notes: str
    db_id: Optional[uuid.UUID] = None


@dataclass
class GuidelineSpec:
    taxonomy_code: Optional[str]
    domain: Optional[str]
    rule_type: str
    rule_params: dict
    severity: str
    narrative_source: str
    db_id: Optional[uuid.UUID] = None


@dataclass
class ContractSpec:
    supplier_idx: int
    domain: str
    contract_idx: int  # 0=legacy, 1=active
    name: str
    effective_from: date
    effective_to: Optional[date]
    notes: str
    rate_cards: list[RateCardSpec] = field(default_factory=list)
    guidelines: list[GuidelineSpec] = field(default_factory=list)
    db_id: Optional[uuid.UUID] = None
    supplier_db_id: Optional[uuid.UUID] = None


@dataclass
class SupplierSpec:
    name: str
    tax_id: str
    primary_domain: str
    domains: list[str]
    contracts: list[ContractSpec] = field(default_factory=list)
    db_id: Optional[uuid.UUID] = None


@dataclass
class LineItemSpec:
    line_number: int
    raw_description: str
    raw_code: Optional[str]
    raw_amount: Decimal
    raw_quantity: Decimal
    raw_unit: str
    taxonomy_code: str
    contracted_rate: Decimal
    expected_amount: Decimal
    claim_number: str
    service_date: date
    service_state: str
    scenario: str  # clean | rate_discrepancy | guideline_violation
    db_id: Optional[uuid.UUID] = None


@dataclass
class InvoiceSpec:
    contract_idx_global: int  # index into RunContext.contracts
    supplier_idx: int
    invoice_number: str
    invoice_date: date
    status: str  # APPROVED | REVIEW_REQUIRED
    line_items: list[LineItemSpec] = field(default_factory=list)
    db_id: Optional[uuid.UUID] = None
    # Set by Biller in pipeline mode — CSV bytes ready for process_invoice_sync
    csv_bytes: Optional[bytes] = None


@dataclass
class RunContext:
    carrier_id: uuid.UUID
    dry_run: bool
    pipeline: bool = False  # when True, Biller writes SUBMITTED invoices + CSV bytes
    suppliers: list[SupplierSpec] = field(default_factory=list)
    contracts: list[ContractSpec] = field(default_factory=list)
    invoices: list[InvoiceSpec] = field(default_factory=list)


# ── BaseAgent ─────────────────────────────────────────────────────────────────

class BaseAgent:
    DEFAULT_MODEL = "claude-haiku-4-5"

    def __init__(self, ctx: RunContext, db: Session) -> None:
        self.ctx = ctx
        self.db = db
        self.dry_run = ctx.dry_run
        self.logger = logging.getLogger(self.__class__.__name__)
        self._client: Optional[anthropic.Anthropic] = None

    def _get_client(self) -> anthropic.Anthropic:
        if self._client is None:
            api_key = settings.anthropic_api_key
            if not api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY is not set. "
                    "Cannot generate synthetic data without the API key."
                )
            self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    def _call_claude(
        self,
        system: str,
        user: str,
        model: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> str:
        """Call Claude and return the response text. Raises on API error."""
        client = self._get_client()
        response = client.messages.create(
            model=model or self.DEFAULT_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text.strip()

    def _parse_json_response(self, text: str) -> object:
        """Strip markdown fences and parse JSON."""
        import json
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # drop first and last line (``` fences)
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return json.loads(text)

    def run(self) -> None:
        raise NotImplementedError
