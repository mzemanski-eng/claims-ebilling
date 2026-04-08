"""
ClassificationQueueItem — provisional queue for line items whose AI classification
confidence fell below the auto-proceed threshold (< 90%).

Workflow:
  1. Pipeline classifies a line item; confidence < 0.90 → create queue item,
     set line_item.status = CLASSIFICATION_PENDING, halt further validation.
  2. Carrier reviews in the Classification Review screen (AI proposal + alternatives).
  3. On APPROVE → update line item taxonomy, create CARRIER_CONFIRMED MappingRule,
     advance line item to CLASSIFIED, re-enqueue for bill audit.
  4. On REJECT → line marked accordingly; carrier decides next step (deny, manual entry).

MappingRule stays the canonical inference engine. Approving a queue item always
produces a CARRIER_CONFIRMED MappingRule so future similar lines auto-classify
without hitting the queue.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.invoice import LineItem
    from app.models.mapping import MappingRule
    from app.models.supplier import Supplier, User


class ClassificationQueueStatus:
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_REVIEW = (
        "NEEDS_REVIEW"  # AI confidence very low or contradictory; flag for attention
    )


class ClassificationQueueItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    One queue item per line item.  Created by the pipeline when AI confidence
    is below the auto-proceed threshold; resolved by a carrier reviewer.

    The AI proposal fields are a snapshot taken at queue-creation time.
    If the line item is re-processed (e.g. after a supplier resubmission)
    the queue item is replaced rather than mutated.
    """

    __tablename__ = "classification_queue_items"

    # ── Subject ───────────────────────────────────────────────────────────────
    line_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("line_items.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # one queue item per line item
        index=True,
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Denormalised from line_item.invoice.supplier_id for fast filtering",
    )
    # Snapshot of the raw description at queue-creation time; preserved for
    # the review UI even if the line item is later edited.
    raw_description: Mapped[str] = mapped_column(Text, nullable=False)
    raw_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="Snapshot of line_item.raw_amount for display without a join",
    )

    # ── AI proposal ───────────────────────────────────────────────────────────
    ai_proposed_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("taxonomy_items.code", ondelete="SET NULL"),
        nullable=True,
        comment="Top-ranked taxonomy code from the AI classifier",
    )
    ai_proposed_billing_component: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )
    ai_confidence: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(4, 3),
        nullable=True,
        comment="0.000–1.000; below 0.900 triggers queue creation",
    )
    ai_reasoning: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Human-readable rationale from the AI for the proposed code",
    )
    # [{code, label, billing_component, confidence}, ...] — up to 3 alternatives
    # shown in the review UI so the carrier can pick a different code easily.
    ai_alternatives: Mapped[Optional[list]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Top alternative taxonomy codes with their confidence scores",
    )

    # ── Review ────────────────────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ClassificationQueueStatus.PENDING,
        index=True,
        comment="PENDING | APPROVED | REJECTED | NEEDS_REVIEW",
    )
    reviewed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Carrier's final decision — may differ from ai_proposed_code.
    approved_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("taxonomy_items.code", ondelete="SET NULL"),
        nullable=True,
    )
    approved_billing_component: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True
    )
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Outcome ───────────────────────────────────────────────────────────────
    # Set on approval: the CARRIER_CONFIRMED MappingRule created so future
    # similar lines auto-classify without hitting the queue.
    created_mapping_rule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mapping_rules.id", ondelete="SET NULL"),
        nullable=True,
        comment="MappingRule produced when this item was approved",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    line_item: Mapped["LineItem"] = relationship(
        "LineItem",
        back_populates="classification_queue_item",
    )
    supplier: Mapped["Supplier"] = relationship("Supplier")
    reviewed_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[reviewed_by_id]
    )
    created_mapping_rule: Mapped[Optional["MappingRule"]] = relationship(
        "MappingRule", foreign_keys=[created_mapping_rule_id]
    )

    def __repr__(self) -> str:
        return (
            f"<ClassificationQueueItem line_item_id={self.line_item_id} "
            f"status={self.status!r} ai_confidence={self.ai_confidence}>"
        )
