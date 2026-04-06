"""
Pydantic schema for per-carrier pipeline configuration.

Stored as JSONB on the Carrier model (carriers.settings).
All fields are optional — omitted / null values inherit the platform-level default
defined in app/settings.py.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class CarrierSettings(BaseModel):
    """
    Per-carrier pipeline and processing configuration.

    Serialised to/from carriers.settings (JSONB).  Any field set to None
    means "use the platform default" (AUTO_APPROVE_CLEAN_INVOICES env var, etc.).
    """

    # ── Invoice auto-approval ─────────────────────────────────────────────────

    auto_approve_clean_invoices: Optional[bool] = Field(
        default=None,
        description=(
            "When true, invoices with zero ERROR exceptions are automatically approved "
            "without carrier review.  None = inherit platform default "
            "(AUTO_APPROVE_CLEAN_INVOICES env var, currently True)."
        ),
    )

    auto_approve_max_amount: Optional[float] = Field(
        default=None,
        ge=0,
        description=(
            "Only auto-approve invoices whose total billed amount is ≤ this value. "
            "None = no upper-bound on auto-approval amount."
        ),
    )

    require_review_above_amount: Optional[float] = Field(
        default=None,
        ge=0,
        description=(
            "Always queue for carrier review when the invoice total exceeds this amount, "
            "even if the invoice is otherwise clean.  None = disabled."
        ),
    )

    # ── Risk tolerance ────────────────────────────────────────────────────────

    risk_tolerance: Literal["strict", "standard", "relaxed"] = Field(
        default="standard",
        description=(
            "strict:   WARNING-severity exceptions are treated as ERRORs — more conservative. "
            "standard: only ERROR-severity exceptions trigger REVIEW_REQUIRED (platform default). "
            "relaxed:  only rate/spend ERRORs require review; classification warnings pass."
        ),
    )

    # ── AI classification mode ────────────────────────────────────────────────

    ai_classification_mode: Literal["auto", "supervised"] = Field(
        default="auto",
        description=(
            "auto:       AI auto-resolves HIGH/MEDIUM confidence classification exceptions "
            "            without human review (platform default). "
            "supervised: all classification exceptions are queued for carrier review."
        ),
    )

    class Config:
        # Allow extra keys so future additions don't break older schema versions
        extra = "ignore"
