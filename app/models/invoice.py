"""
Invoice-side entities: Invoice, InvoiceVersion, LineItem, RawExtractionArtifact.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.supplier import Contract, Supplier
    from app.models.mapping import MappingRule
    from app.models.validation import ValidationResult, ExceptionRecord


# ── Lifecycle state constants ────────────────────────────────────────────────


class SubmissionStatus:
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    PROCESSING = "PROCESSING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    SUPPLIER_RESPONDED = "SUPPLIER_RESPONDED"
    PENDING_CARRIER_REVIEW = "PENDING_CARRIER_REVIEW"
    CARRIER_REVIEWING = "CARRIER_REVIEWING"
    APPROVED = "APPROVED"
    DISPUTED = "DISPUTED"
    EXPORTED = "EXPORTED"
    WITHDRAWN = "WITHDRAWN"

    ALL = [
        DRAFT,
        SUBMITTED,
        PROCESSING,
        REVIEW_REQUIRED,
        SUPPLIER_RESPONDED,
        PENDING_CARRIER_REVIEW,
        CARRIER_REVIEWING,
        APPROVED,
        DISPUTED,
        EXPORTED,
        WITHDRAWN,
    ]

    # Terminal states — no further transitions allowed
    TERMINAL = {EXPORTED, WITHDRAWN}


class LineItemStatus:
    PENDING = "PENDING"
    CLASSIFIED = "CLASSIFIED"
    VALIDATED = "VALIDATED"
    EXCEPTION = "EXCEPTION"
    OVERRIDE = "OVERRIDE"
    APPROVED = "APPROVED"
    DISPUTED = "DISPUTED"
    RESOLVED = "RESOLVED"


class FileFormat:
    CSV = "csv"
    PDF = "pdf"


# ── Models ───────────────────────────────────────────────────────────────────


class Invoice(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Represents a single invoice submission from a supplier.
    Immutable header; line items carry the detail.
    Resubmissions create new InvoiceVersion rows (not new Invoice rows).
    """

    __tablename__ = "invoices"

    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contracts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Supplier's own invoice number — used for deduplication warning
    invoice_number: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Lifecycle
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=SubmissionStatus.DRAFT,
        index=True,
    )

    # File reference for the most recent version
    raw_file_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    file_format: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Supplier memo on initial submission
    submission_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    supplier: Mapped["Supplier"] = relationship("Supplier", back_populates="invoices")
    contract: Mapped["Contract"] = relationship("Contract", back_populates="invoices")
    versions: Mapped[list["InvoiceVersion"]] = relationship(
        "InvoiceVersion",
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceVersion.version_number",
    )
    line_items: Mapped[list["LineItem"]] = relationship(
        "LineItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="LineItem.line_number",
    )

    def __repr__(self) -> str:
        return (
            f"<Invoice invoice_number={self.invoice_number!r} status={self.status!r}>"
        )


class InvoiceVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Tracks each time a supplier re-uploads an invoice.
    The raw file and extraction artifacts for each attempt are preserved
    for audit and dispute purposes.
    """

    __tablename__ = "invoice_versions"
    __table_args__ = (
        UniqueConstraint("invoice_id", "version_number", name="uq_invoice_version"),
    )

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_format: Mapped[str] = mapped_column(String(8), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="versions")
    extraction_artifacts: Mapped[list["RawExtractionArtifact"]] = relationship(
        "RawExtractionArtifact",
        back_populates="invoice_version",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<InvoiceVersion invoice_id={self.invoice_id} v={self.version_number}>"


class LineItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    A single normalized line from a supplier invoice.

    Raw fields (raw_*): exactly as extracted from the file.
    Mapped fields: set by the classification engine.
    Validation fields: set by the rate/guideline validation engine.
    """

    __tablename__ = "line_items"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invoice_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # ── Status ───────────────────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=LineItemStatus.PENDING,
        index=True,
    )

    # ── Raw extraction ────────────────────────────────────────────────────────
    raw_description: Mapped[str] = mapped_column(Text, nullable=False)
    raw_code: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="Supplier's own billing code, if any"
    )
    raw_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    raw_quantity: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, default=1
    )
    raw_unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Claim context
    claim_number: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )
    service_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # ── Classification output ─────────────────────────────────────────────────
    taxonomy_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("taxonomy_items.code", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    billing_component: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    mapped_unit_model: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    mapping_confidence: Mapped[Optional[str]] = mapped_column(
        String(8), nullable=True, comment="HIGH | MEDIUM | LOW"
    )
    mapping_rule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mapping_rules.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Validation output ─────────────────────────────────────────────────────
    mapped_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    expected_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2), nullable=True
    )

    # Relationships
    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="line_items")
    mapping_rule: Mapped[Optional["MappingRule"]] = relationship("MappingRule")
    validation_results: Mapped[list["ValidationResult"]] = relationship(
        "ValidationResult",
        back_populates="line_item",
        cascade="all, delete-orphan",
    )
    exceptions: Mapped[list["ExceptionRecord"]] = relationship(
        "ExceptionRecord",
        back_populates="line_item",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<LineItem line={self.line_number} "
            f"raw_amount={self.raw_amount} status={self.status!r}>"
        )


class RawExtractionArtifact(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Preserves the raw text extracted from each file page/section.
    Used for dispute resolution — always traceable back to the source document.
    """

    __tablename__ = "raw_extraction_artifacts"

    invoice_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoice_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    page_number: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="Page number for PDFs; NULL for CSV rows"
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_method: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="pdfplumber | csv | manual"
    )
    # Store any per-row/per-page metadata (bounding boxes, column offsets, etc.)
    extraction_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Relationships
    invoice_version: Mapped["InvoiceVersion"] = relationship(
        "InvoiceVersion",
        back_populates="extraction_artifacts",
    )

    def __repr__(self) -> str:
        return f"<RawExtractionArtifact method={self.extraction_method!r} page={self.page_number}>"
