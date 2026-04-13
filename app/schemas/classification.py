"""
Classification queue schemas — request/response shapes for the
carrier-facing Classification Review screen.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import Field

from app.schemas.common import BaseSchema, TimestampedSchema


class ClassificationAlternative(BaseSchema):
    """One entry from the ai_alternatives JSONB field."""

    code: str
    label: Optional[str] = None
    billing_component: Optional[str] = None
    confidence: Optional[str] = None  # HIGH | MEDIUM | LOW


class ClassificationQueueItemSummary(TimestampedSchema):
    """
    One classification queue item for the carrier Classification Review list.
    Includes AI proposal, review state, and denormalised display fields.
    """

    line_item_id: uuid.UUID
    supplier_id: uuid.UUID
    supplier_name: Optional[str] = None  # denormalised for display
    invoice_id: Optional[uuid.UUID] = None  # from line_item.invoice_id
    invoice_number: Optional[str] = None  # from line_item.invoice.invoice_number
    line_number: Optional[int] = None  # from line_item.line_number

    # Snapshot captured at queue-creation time
    raw_description: str
    raw_amount: Decimal

    # AI proposal
    ai_proposed_code: Optional[str] = None
    ai_proposed_billing_component: Optional[str] = None
    ai_confidence: Optional[Decimal] = None  # 0.000–1.000
    ai_reasoning: Optional[str] = None
    ai_alternatives: Optional[list[ClassificationAlternative]] = None

    # Review state
    status: str  # PENDING | APPROVED | REJECTED | NEEDS_REVIEW
    reviewed_by_id: Optional[uuid.UUID] = None
    reviewed_at: Optional[datetime] = None
    approved_code: Optional[str] = None
    approved_billing_component: Optional[str] = None
    review_notes: Optional[str] = None
    created_mapping_rule_id: Optional[uuid.UUID] = None


class ClassificationApproveRequest(BaseSchema):
    """
    Carrier confirms a taxonomy code for a pending classification item.

    If approved_code == ai_proposed_code → CARRIER_CONFIRMED (AI was right).
    If approved_code != ai_proposed_code → CARRIER_OVERRIDE (AI was wrong).
    Both paths create a MappingRule so future similar lines auto-classify.
    """

    approved_code: str = Field(..., min_length=1, max_length=64)
    approved_billing_component: str = Field(..., min_length=1, max_length=32)
    review_notes: Optional[str] = Field(default=None, max_length=2000)


class ClassificationRejectRequest(BaseSchema):
    """
    Carrier rejects a queue item — the line is marked DENIED (will not be paid).
    """

    review_notes: Optional[str] = Field(default=None, max_length=2000)


class ClassificationApproveResult(BaseSchema):
    """Response body after a successful approve action."""

    queue_item_id: uuid.UUID
    line_item_id: uuid.UUID
    approved_code: str
    bill_audit_result: str  # "VALIDATED" | "EXCEPTION"
    mapping_rule_created: bool
    message: str


class ClassificationBulkApproveResult(BaseSchema):
    """Response body after a bulk accept-AI-proposals action."""

    approved: int  # items successfully approved using their ai_proposed_code
    skipped: int  # items that had no ai_proposed_code and were left untouched
    bill_audit_exceptions: int  # of the approved items, how many triggered an exception


class ClassificationStats(BaseSchema):
    """Summary stats for the Classification Review screen header card."""

    pending: int = 0
    needs_review: int = 0  # AI has no proposal; priority human attention
    approved_today: int = 0
    rejected_today: int = 0
    total_pending_amount: Decimal = Decimal("0")  # sum of raw_amount for PENDING items
