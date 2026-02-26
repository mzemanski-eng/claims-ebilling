"""
Carrier-specific request schemas.

Kept separate from invoice.py to maintain clean supplier/carrier schema boundaries.
Response shapes (InvoiceListItem, InvoiceResponse, LineItemCarrierView) are reused
from invoice.py — no duplication needed.
"""

from typing import Optional

from pydantic import Field, field_validator

from app.models.validation import ResolutionAction
from app.schemas.common import BaseSchema


class RequestChangesPayload(BaseSchema):
    """
    Carrier returns an invoice to the supplier for correction.
    Transitions PENDING_CARRIER_REVIEW → REVIEW_REQUIRED.
    Carrier notes are stored in the audit event (immutable, always recoverable).
    """

    carrier_notes: str = Field(..., min_length=1, max_length=2000)


class CarrierExceptionResolvePayload(BaseSchema):
    """
    Carrier resolves a single exception with a typed action + optional notes.
    Uses a proper request body instead of query params for clear API design.
    """

    resolution_action: str = Field(...)
    resolution_notes: str = Field(default="", max_length=2000)

    @field_validator("resolution_action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        valid = {
            ResolutionAction.WAIVED,
            ResolutionAction.HELD_CONTRACT_RATE,
            ResolutionAction.RECLASSIFIED,
            ResolutionAction.ACCEPTED_REDUCTION,
        }
        if v not in valid:
            raise ValueError(f"resolution_action must be one of: {sorted(valid)}")
        return v


class CarrierApprovalRequest(BaseSchema):
    """
    Carrier approves a full invoice.
    All remaining OPEN exceptions are force-waived as part of the approval action.
    Unlike ApprovalRequest in invoice.py, there is no partial line-item selection —
    the exception resolution panel is the correct tool for per-line decisions.
    """

    notes: Optional[str] = Field(default=None, max_length=2000)
