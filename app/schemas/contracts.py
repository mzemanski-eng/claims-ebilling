"""
Pydantic schemas for Contract, RateCard, and Guideline CRUD,
plus the AI PDF extraction result shape.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from app.schemas.common import BaseSchema


# ── Rate Card ─────────────────────────────────────────────────────────────────


class RateCardCreate(BaseSchema):
    taxonomy_code: str
    contracted_rate: Decimal
    max_units: Optional[Decimal] = None
    is_all_inclusive: bool = False
    effective_from: date
    effective_to: Optional[date] = None


class RateCardDetail(RateCardCreate):
    id: uuid.UUID
    taxonomy_label: Optional[str] = None  # joined from TaxonomyItem


# ── Guideline ─────────────────────────────────────────────────────────────────


class GuidelineCreate(BaseSchema):
    taxonomy_code: Optional[str] = None  # None = domain-wide rule
    domain: Optional[str] = None
    rule_type: str  # max_units | cap_amount | billing_increment | bundling_prohibition | requires_auth
    rule_params: dict = {}
    severity: str = "ERROR"
    narrative_source: Optional[str] = None


class GuidelineDetail(GuidelineCreate):
    id: uuid.UUID
    is_active: bool


# ── Contract ──────────────────────────────────────────────────────────────────


class ContractCreate(BaseSchema):
    supplier_id: uuid.UUID
    name: str
    effective_from: date
    effective_to: Optional[date] = None
    geography_scope: str = "national"
    state_codes: Optional[list[str]] = None
    notes: Optional[str] = None


class ContractDetail(BaseSchema):
    id: uuid.UUID
    name: str
    supplier_id: uuid.UUID
    supplier_name: Optional[str]
    carrier_id: uuid.UUID
    effective_from: date
    effective_to: Optional[date]
    geography_scope: str
    state_codes: Optional[list[str]]
    notes: Optional[str]
    is_active: bool
    rate_cards: list[RateCardDetail]
    guidelines: list[GuidelineDetail]


# ── AI Extraction Result ──────────────────────────────────────────────────────


class ParsedContractResult(BaseSchema):
    """AI extraction result — NOT yet saved to DB."""

    contract: ContractCreate
    rate_cards: list[RateCardCreate]
    guidelines: list[GuidelineCreate]
    extraction_notes: str  # Claude's confidence/caveats
