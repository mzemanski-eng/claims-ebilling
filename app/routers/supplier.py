"""
Supplier-facing API routes.

Workflow:
  POST /supplier/invoices                → create invoice record
  POST /supplier/invoices/{id}/upload    → upload file, enqueue processing
  GET  /supplier/invoices                → list all invoices for this supplier
  GET  /supplier/invoices/{id}           → full invoice detail + validation summary
  GET  /supplier/invoices/{id}/lines     → line items with supplier-facing results
  POST /supplier/invoices/{id}/resubmit  → upload new version
  POST /supplier/exceptions/{id}/respond → supplier responds to an exception
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.invoice import (
    Invoice,
    InvoiceVersion,
    LineItem,
    LineItemStatus,
    SubmissionStatus,
)
from app.models.supplier import Contract, User, UserRole
from app.models.validation import ExceptionRecord, ExceptionStatus, ValidationStatus
from app.routers.auth import require_role
from app.schemas.invoice import (
    InvoiceCreate,
    InvoiceListItem,
    InvoiceResponse,
    InvoiceUploadResponse,
    ValidationSummary,
    LineItemSupplierView,
    ValidationResultSupplierView,
    ExceptionSupplierView,
    ExceptionResponsePayload,
)
from app.services.audit import logger as audit
from app.services.ingestion.dispatcher import detect_format
from app.services.storage.base import get_storage
from app.workers.invoice_pipeline import process_invoice_sync
from app.models.audit import ActorType

router = APIRouter(prefix="/supplier", tags=["supplier"])


# ── Contracts ─────────────────────────────────────────────────────────────────


@router.get("/contracts")
def list_supplier_contracts(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.SUPPLIER)),
) -> list[dict]:
    """
    Return all active contracts for the authenticated supplier.
    Used by the frontend to populate the contract selector on the new-invoice form.
    """
    contracts = (
        db.query(Contract)
        .filter(
            Contract.supplier_id == current_user.supplier_id,
            Contract.is_active.is_(True),
        )
        .order_by(Contract.effective_from.desc())
        .all()
    )
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "effective_from": c.effective_from.isoformat(),
            "effective_to": c.effective_to.isoformat() if c.effective_to else None,
            "geography_scope": c.geography_scope,
        }
        for c in contracts
    ]


# ── Create Invoice ────────────────────────────────────────────────────────────


@router.post(
    "/invoices", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED
)
def create_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.SUPPLIER)),
) -> InvoiceResponse:
    """
    Create a new invoice record (before file upload).
    Status starts as DRAFT.
    """
    invoice = Invoice(
        supplier_id=current_user.supplier_id,
        contract_id=payload.contract_id,
        invoice_number=payload.invoice_number,
        invoice_date=payload.invoice_date,
        status=SubmissionStatus.DRAFT,
        submission_notes=payload.submission_notes,
        current_version=1,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    audit.log_event(
        db,
        "invoice",
        invoice.id,
        "invoice.created",
        payload={"invoice_number": invoice.invoice_number, "status": invoice.status},
        actor_type=ActorType.SUPPLIER,
        actor_id=current_user.id,
    )
    db.commit()

    return _to_invoice_response(invoice, db)


# ── Upload File ───────────────────────────────────────────────────────────────


@router.post("/invoices/{invoice_id}/upload", response_model=InvoiceUploadResponse)
def upload_invoice_file(
    invoice_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.SUPPLIER)),
) -> InvoiceUploadResponse:
    """
    Upload a CSV (or PDF) invoice file. Triggers background processing.
    Allowed when status is DRAFT or REVIEW_REQUIRED (resubmission).
    """
    invoice = _get_supplier_invoice(invoice_id, current_user, db)

    if invoice.status not in (SubmissionStatus.DRAFT, SubmissionStatus.REVIEW_REQUIRED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot upload file — invoice is in status '{invoice.status}'. "
            f"Only DRAFT or REVIEW_REQUIRED invoices accept new uploads.",
        )

    # ── Validate file format ──────────────────────────────────────────────────
    filename = file.filename or "invoice.csv"
    try:
        file_format = detect_format(filename)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )

    # ── Store file ────────────────────────────────────────────────────────────
    file_bytes = file.file.read()
    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty",
        )

    storage = get_storage()
    stored_path = storage.save(
        data=file_bytes,
        filename=f"{invoice.id}_v{invoice.current_version}_{filename}",
        subfolder=f"invoices/{invoice.id}",
    )

    # ── Update invoice + create version record ────────────────────────────────
    invoice.raw_file_path = stored_path
    invoice.file_format = file_format
    invoice.status = SubmissionStatus.SUBMITTED
    invoice.submitted_at = datetime.now(timezone.utc)

    version = InvoiceVersion(
        invoice_id=invoice.id,
        version_number=invoice.current_version,
        raw_file_path=stored_path,
        file_format=file_format,
        submitted_at=invoice.submitted_at,
    )
    db.add(version)
    db.flush()

    audit.log_invoice_submitted(db, invoice, actor_id=current_user.id)
    db.commit()

    # ── Process synchronously (file bytes already in memory) ─────────────────
    summary = process_invoice_sync(
        invoice_id=str(invoice.id),
        file_bytes=file_bytes,
        filename=filename,
        db=db,
    )

    # Refresh to get the final status set by the pipeline
    db.refresh(invoice)

    return InvoiceUploadResponse(
        invoice_id=invoice.id,
        status=invoice.status,
        message=(
            f"Invoice processed successfully. "
            f"{summary.get('lines_processed', 0)} lines processed, "
            f"{summary.get('lines_error', 0)} exceptions flagged."
        ),
        version=invoice.current_version,
    )


# ── List Invoices ─────────────────────────────────────────────────────────────


@router.get("/invoices", response_model=list[InvoiceListItem])
def list_invoices(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.SUPPLIER)),
) -> list[InvoiceListItem]:
    """Return all invoices for the current supplier, newest first."""
    invoices = (
        db.query(Invoice)
        .filter(Invoice.supplier_id == current_user.supplier_id)
        .order_by(Invoice.created_at.desc())
        .all()
    )
    return [_to_invoice_list_item(inv, db) for inv in invoices]


# ── Invoice Detail ────────────────────────────────────────────────────────────


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.SUPPLIER)),
) -> InvoiceResponse:
    invoice = _get_supplier_invoice(invoice_id, current_user, db)
    return _to_invoice_response(invoice, db)


# ── Line Items ────────────────────────────────────────────────────────────────


@router.get("/invoices/{invoice_id}/lines", response_model=list[LineItemSupplierView])
def get_line_items(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.SUPPLIER)),
) -> list[LineItemSupplierView]:
    """Return all line items for the invoice with supplier-facing validation results."""
    invoice = _get_supplier_invoice(invoice_id, current_user, db)
    return [_to_line_item_supplier_view(li) for li in invoice.line_items]


# ── Resubmit ──────────────────────────────────────────────────────────────────


@router.post("/invoices/{invoice_id}/resubmit", response_model=InvoiceUploadResponse)
def resubmit_invoice(
    invoice_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.SUPPLIER)),
) -> InvoiceUploadResponse:
    """
    Submit a new version of an invoice.
    Bumps current_version and triggers re-processing.
    Previous line items and validation results are preserved for audit.
    """
    invoice = _get_supplier_invoice(invoice_id, current_user, db)

    if invoice.status not in (
        SubmissionStatus.REVIEW_REQUIRED,
        SubmissionStatus.SUPPLIER_RESPONDED,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Resubmission not allowed in status '{invoice.status}'.",
        )

    invoice.current_version += 1
    db.flush()

    # Delegate to upload handler (which creates the version record + enqueues)
    return upload_invoice_file(invoice_id, file, db, current_user)


# ── Exception Response ────────────────────────────────────────────────────────


@router.post("/exceptions/{exception_id}/respond", status_code=status.HTTP_200_OK)
def respond_to_exception(
    exception_id: uuid.UUID,
    payload: ExceptionResponsePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.SUPPLIER)),
) -> dict:
    """
    Supplier responds to an open exception with text and/or an attached doc.
    Transitions exception to SUPPLIER_RESPONDED.
    """
    exc = db.get(ExceptionRecord, exception_id)
    if exc is None:
        raise HTTPException(status_code=404, detail="Exception not found")

    # Verify this exception belongs to the supplier's invoice
    line_item = db.get(LineItem, exc.line_item_id)
    if line_item is None:
        raise HTTPException(status_code=404, detail="Line item not found")

    invoice = db.get(Invoice, line_item.invoice_id)
    if invoice is None or invoice.supplier_id != current_user.supplier_id:
        raise HTTPException(status_code=403, detail="Access denied")

    if exc.status != ExceptionStatus.OPEN:
        raise HTTPException(
            status_code=409,
            detail=f"Exception is in status '{exc.status}' and cannot be responded to.",
        )

    exc.supplier_response = payload.supplier_response
    exc.status = ExceptionStatus.SUPPLIER_RESPONDED

    # Update invoice status
    if invoice.status == SubmissionStatus.REVIEW_REQUIRED:
        invoice.status = SubmissionStatus.SUPPLIER_RESPONDED

    audit.log_event(
        db,
        "exception",
        exc.id,
        "exception.supplier_responded",
        payload={"supplier_response": payload.supplier_response},
        actor_type=ActorType.SUPPLIER,
        actor_id=current_user.id,
    )
    db.commit()

    return {"message": "Response recorded. The carrier will review your response."}


# ── Private helpers ───────────────────────────────────────────────────────────


def _get_supplier_invoice(invoice_id: uuid.UUID, user: User, db: Session) -> Invoice:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.supplier_id != user.supplier_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return invoice


def _to_invoice_response(invoice: Invoice, db: Session) -> InvoiceResponse:
    summary = _build_validation_summary(invoice, db)
    return InvoiceResponse(
        id=invoice.id,
        supplier_id=invoice.supplier_id,
        contract_id=invoice.contract_id,
        invoice_number=invoice.invoice_number,
        invoice_date=invoice.invoice_date,
        status=invoice.status,
        current_version=invoice.current_version,
        file_format=invoice.file_format,
        submitted_at=invoice.submitted_at,
        submission_notes=invoice.submission_notes,
        created_at=invoice.created_at,
        updated_at=invoice.updated_at,
        validation_summary=summary,
    )


def _to_invoice_list_item(invoice: Invoice, db: Session) -> InvoiceListItem:
    total_billed = (
        sum(li.raw_amount for li in invoice.line_items) if invoice.line_items else None
    )
    exc_count = sum(
        1
        for li in invoice.line_items
        for exc in li.exceptions
        if exc.status == ExceptionStatus.OPEN
    )
    return InvoiceListItem(
        id=invoice.id,
        invoice_number=invoice.invoice_number,
        invoice_date=invoice.invoice_date,
        status=invoice.status,
        current_version=invoice.current_version,
        submitted_at=invoice.submitted_at,
        total_billed=total_billed,
        exception_count=exc_count,
    )


def _build_validation_summary(
    invoice: Invoice, db: Session
) -> ValidationSummary | None:
    lines = invoice.line_items
    if not lines:
        return None

    total_billed = sum(li.raw_amount for li in lines)
    total_payable = Decimal("0")
    total_in_dispute = Decimal("0")
    total_denied = Decimal("0")
    validated = 0
    with_exceptions = 0
    pending_review = 0
    lines_denied = 0

    for li in lines:
        # DENIED lines are carrier-final: excluded from both payable and in-dispute
        if li.status == LineItemStatus.DENIED:
            lines_denied += 1
            total_denied += li.raw_amount
            continue

        has_error = any(
            v.status == ValidationStatus.FAIL for v in li.validation_results
        )
        has_low_confidence = li.mapping_confidence in ("LOW", "MEDIUM")

        if has_error:
            with_exceptions += 1
            total_in_dispute += li.raw_amount
        else:
            validated += 1
            total_payable += li.expected_amount or li.raw_amount

        if has_low_confidence and not has_error:
            pending_review += 1

    return ValidationSummary(
        total_lines=len(lines),
        lines_validated=validated,
        lines_with_exceptions=with_exceptions,
        lines_pending_review=pending_review,
        total_billed=total_billed,
        total_payable=total_payable,
        total_in_dispute=total_in_dispute,
        lines_denied=lines_denied,
        total_denied=total_denied,
    )


def _to_line_item_supplier_view(li: LineItem) -> LineItemSupplierView:
    validations = [
        ValidationResultSupplierView(
            status=v.status,
            severity=v.severity,
            message=v.message,
            expected_value=v.expected_value,
            actual_value=v.actual_value,
            required_action=v.required_action,
        )
        for v in li.validation_results
    ]
    exceptions = [
        ExceptionSupplierView(
            exception_id=exc.id,
            status=exc.status,
            message=exc.validation_result.message if exc.validation_result else "",
            severity=exc.validation_result.severity
            if exc.validation_result
            else "ERROR",
            required_action=exc.validation_result.required_action
            if exc.validation_result
            else "NONE",
            supplier_response=exc.supplier_response,
        )
        for exc in li.exceptions
    ]
    return LineItemSupplierView(
        id=li.id,
        line_number=li.line_number,
        status=li.status,
        raw_description=li.raw_description,
        raw_amount=li.raw_amount,
        raw_quantity=li.raw_quantity,
        raw_unit=li.raw_unit,
        claim_number=li.claim_number,
        service_date=li.service_date,
        expected_amount=li.expected_amount,
        validations=validations,
        exceptions=exceptions,
        needs_review=li.mapping_confidence in ("LOW", "MEDIUM"),
    )
