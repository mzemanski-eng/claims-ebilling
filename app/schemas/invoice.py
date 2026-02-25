"""
Invoice and LineItem schemas — request and response shapes for the API.

Design principle: suppliers never see taxonomy codes.
They see plain-language labels and validation messages only.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import Field, field_validator

from app.schemas.common import BaseSchema, TimestampedSchema


# ── Invoice schemas ──────────────────────────────────────────────────────────


class InvoiceCreate(BaseSchema):
    """Payload when a supplier initiates an invoice (before file upload)."""

    contract_id: uuid.UUID
    invoice_number: str = Field(..., min_length=1, max_length=128)
    invoice_date: date
    submission_notes: Optional[str] = None


class InvoiceUploadResponse(BaseSchema):
    """Returned immediately after file upload — before processing completes."""

    invoice_id: uuid.UUID
    status: str
    message: str
    version: int


class ValidationSummary(BaseSchema):
    """
    High-level validation summary shown to supplier.
    Counts only — no taxonomy codes exposed.
    """

    total_lines: int
    lines_validated: int  # PASS
    lines_with_exceptions: int  # FAIL or WARNING (ERROR severity)
    lines_pending_review: int  # LOW/MEDIUM confidence mappings
    total_billed: Decimal
    total_payable: Decimal  # validated amount (may be less than billed)
    total_in_dispute: Decimal  # lines with open exceptions


class InvoiceResponse(TimestampedSchema):
    """Full invoice detail — returned to supplier and carrier."""

    supplier_id: uuid.UUID
    contract_id: uuid.UUID
    invoice_number: str
    invoice_date: date
    status: str
    current_version: int
    file_format: Optional[str]
    submitted_at: Optional[datetime]
    submission_notes: Optional[str]
    validation_summary: Optional[ValidationSummary] = None


class InvoiceListItem(BaseSchema):
    """Compact row for listing invoices in the supplier dashboard."""

    id: uuid.UUID
    invoice_number: str
    invoice_date: date
    status: str
    current_version: int
    submitted_at: Optional[datetime]
    total_billed: Optional[Decimal] = None
    exception_count: int = 0


# ── LineItem schemas ──────────────────────────────────────────────────────────


class ValidationResultSupplierView(BaseSchema):
    """
    What the supplier sees for a single validation check on their line.
    No taxonomy codes. Plain language only.
    """

    status: str  # PASS | FAIL | WARNING
    severity: str  # ERROR | WARNING | INFO
    message: str  # Human-readable explanation
    expected_value: Optional[str] = None  # e.g. "$325.00"
    actual_value: Optional[str] = None  # e.g. "$650.00"
    required_action: str  # NONE | REUPLOAD | ATTACH_DOC | ...


class ExceptionSupplierView(BaseSchema):
    """What the supplier sees for an open exception."""

    exception_id: uuid.UUID
    status: str
    message: str  # From the ValidationResult
    severity: str
    required_action: str
    supplier_response: Optional[str] = None


class LineItemSupplierView(BaseSchema):
    """
    A single normalized line — supplier-facing.
    Deliberately hides taxonomy_code and mapping internals.
    """

    id: uuid.UUID
    line_number: int
    status: str

    # What the supplier submitted
    raw_description: str
    raw_amount: Decimal
    raw_quantity: Decimal
    raw_unit: Optional[str]
    claim_number: Optional[str]
    service_date: Optional[date]

    # What the system will pay (None if still processing)
    expected_amount: Optional[Decimal] = None

    # Validation results visible to supplier
    validations: list[ValidationResultSupplierView] = []
    exceptions: list[ExceptionSupplierView] = []

    # Confidence note (no code exposed — just a flag for supplier awareness)
    needs_review: bool = False  # True if mapping confidence is LOW/MEDIUM


class LineItemCarrierView(LineItemSupplierView):
    """
    Extended view for carrier admins — includes taxonomy internals.
    Inherits all supplier fields and adds classification detail.
    """

    taxonomy_code: Optional[str] = None
    taxonomy_label: Optional[str] = None  # Human-readable label from TaxonomyItem
    billing_component: Optional[str] = None
    mapped_unit_model: Optional[str] = None
    mapping_confidence: Optional[str] = None
    mapped_rate: Optional[Decimal] = None


# ── Exception resolution schemas ─────────────────────────────────────────────


class ExceptionResponsePayload(BaseSchema):
    """Supplier submits this to respond to an exception."""

    exception_id: uuid.UUID
    supplier_response: str = Field(..., min_length=1)
    # supporting_doc uploaded separately via file endpoint


class ResubmitInvoice(BaseSchema):
    """Supplier requests a re-upload (new version)."""

    notes: Optional[str] = None


# ── Admin schemas ─────────────────────────────────────────────────────────────


class MappingOverrideRequest(BaseSchema):
    """Carrier admin overrides the taxonomy mapping for a line item."""

    line_item_id: uuid.UUID
    taxonomy_code: str = Field(..., min_length=1)
    billing_component: str = Field(..., min_length=1)
    scope: str = Field(
        default="this_line", description="this_line | this_supplier | global"
    )
    notes: Optional[str] = None

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, v: str) -> str:
        if v not in ("this_line", "this_supplier", "global"):
            raise ValueError("scope must be this_line, this_supplier, or global")
        return v


class ApprovalRequest(BaseSchema):
    """Carrier admin approves an invoice (or specific line items)."""

    invoice_id: uuid.UUID
    line_item_ids: Optional[list[uuid.UUID]] = None  # None = approve all
    notes: Optional[str] = None


class ExportResponse(BaseSchema):
    """Returned when carrier exports approved lines."""

    invoice_id: uuid.UUID
    export_file_path: str
    line_count: int
    total_approved: Decimal
    exported_at: datetime
