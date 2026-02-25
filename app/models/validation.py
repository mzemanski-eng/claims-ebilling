"""
ValidationResult and ExceptionRecord.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.invoice import LineItem
    from app.models.supplier import RateCard, Guideline


# ── Constant classes (avoid Enum to keep migrations simple) ─────────────────


class ValidationType:
    RATE = "RATE"
    GUIDELINE = "GUIDELINE"
    CLASSIFICATION = "CLASSIFICATION"  # e.g. UNRECOGNIZED_SERVICE


class ValidationStatus:
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"


class ValidationSeverity:
    ERROR = "ERROR"  # Blocks payment; supplier must act
    WARNING = "WARNING"  # Flagged for carrier review; does not block
    INFO = "INFO"  # Recorded for audit; no action required


class RequiredAction:
    NONE = "NONE"
    REUPLOAD = "REUPLOAD"
    ATTACH_DOC = "ATTACH_DOC"
    REQUEST_RECLASSIFICATION = "REQUEST_RECLASSIFICATION"
    ACCEPT_REDUCTION = "ACCEPT_REDUCTION"


class ExceptionStatus:
    OPEN = "OPEN"
    SUPPLIER_RESPONDED = "SUPPLIER_RESPONDED"
    CARRIER_REVIEWING = "CARRIER_REVIEWING"
    RESOLVED = "RESOLVED"
    WAIVED = "WAIVED"


class ResolutionAction:
    REUPLOAD = "REUPLOAD"
    WAIVED = "WAIVED"
    HELD_CONTRACT_RATE = "HELD_CONTRACT_RATE"
    RECLASSIFIED = "RECLASSIFIED"
    ACCEPTED_REDUCTION = "ACCEPTED_REDUCTION"


# ── Models ───────────────────────────────────────────────────────────────────


class ValidationResult(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    The result of one validation check against one line item.
    A single line item may have multiple ValidationResults
    (one per rate check, one per guideline rule).

    These records are immutable once written — they represent what the
    system found at a specific point in time. Reprocessing creates new records.
    """

    __tablename__ = "validation_results"

    line_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("line_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    validation_type: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="RATE | GUIDELINE | CLASSIFICATION"
    )

    # FK to the specific rule that produced this result (one or the other)
    rate_card_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rate_cards.id", ondelete="SET NULL"),
        nullable=True,
    )
    guideline_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("guidelines.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Result ────────────────────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="PASS | FAIL | WARNING"
    )
    severity: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ValidationSeverity.ERROR,
        comment="ERROR | WARNING | INFO",
    )

    # Human-readable explanation — shown to both supplier and carrier
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Machine-readable values for UI rendering
    expected_value: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    actual_value: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # What the supplier needs to do next
    required_action: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=RequiredAction.NONE,
        comment="NONE | REUPLOAD | ATTACH_DOC | REQUEST_RECLASSIFICATION | ACCEPT_REDUCTION",
    )

    # Relationships
    line_item: Mapped["LineItem"] = relationship(
        "LineItem", back_populates="validation_results"
    )
    rate_card: Mapped[Optional["RateCard"]] = relationship("RateCard")
    guideline: Mapped[Optional["Guideline"]] = relationship("Guideline")

    def __repr__(self) -> str:
        return (
            f"<ValidationResult type={self.validation_type!r} "
            f"status={self.status!r} severity={self.severity!r}>"
        )


class ExceptionRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    An open issue on a line item requiring action.
    Created for every FAIL/WARNING ValidationResult.
    Tracks the full resolution lifecycle.

    Key principle: exceptions are NEVER deleted, only transitioned through states.
    """

    __tablename__ = "exception_records"

    line_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("line_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    validation_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("validation_results.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ExceptionStatus.OPEN,
        index=True,
        comment="OPEN | SUPPLIER_RESPONDED | CARRIER_REVIEWING | RESOLVED | WAIVED",
    )

    # ── Supplier response fields ──────────────────────────────────────────────
    supplier_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    supporting_doc_path: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True
    )

    # ── Resolution fields (set by carrier) ────────────────────────────────────
    resolution_action: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        comment="REUPLOAD | WAIVED | HELD_CONTRACT_RATE | RECLASSIFIED | ACCEPTED_REDUCTION",
    )
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    line_item: Mapped["LineItem"] = relationship(
        "LineItem", back_populates="exceptions"
    )
    validation_result: Mapped["ValidationResult"] = relationship("ValidationResult")

    def __repr__(self) -> str:
        return (
            f"<ExceptionRecord status={self.status!r} line_item_id={self.line_item_id}>"
        )
