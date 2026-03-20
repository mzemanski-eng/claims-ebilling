"""
Pydantic schemas for Contract, RateCard, and Guideline CRUD,
plus the AI PDF extraction result shape.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import model_validator

from app.schemas.common import BaseSchema


# ── Rate Card ─────────────────────────────────────────────────────────────────


class RateTier(BaseSchema):
    """
    A single band in a tiered rate schedule.
    Example: pages 1–20 at $0.85, pages 21+ at $0.55.
    """
    from_unit: int
    to_unit: Optional[int] = None  # None = unlimited / all remaining units
    rate: Decimal


class RateCardCreate(BaseSchema):
    taxonomy_code: str
    rate_type: str = "flat"  # flat | tiered | hourly | mileage | per_diem
    contracted_rate: Optional[Decimal] = None  # Required for non-tiered
    rate_tiers: Optional[list[RateTier]] = None  # Required for tiered
    max_units: Optional[Decimal] = None
    is_all_inclusive: bool = False
    effective_from: date
    effective_to: Optional[date] = None

    @model_validator(mode="after")
    def validate_rate_fields(self) -> "RateCardCreate":
        if self.rate_type == "tiered":
            if not self.rate_tiers:
                raise ValueError("rate_tiers is required when rate_type is 'tiered'")
        else:
            if self.contracted_rate is None:
                raise ValueError("contracted_rate is required when rate_type is not 'tiered'")
        return self


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
