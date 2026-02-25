"""
Carrier admin API routes.

Workflow:
  GET  /admin/invoices                          → queue of invoices pending review
  GET  /admin/invoices/{id}                     → full carrier view of invoice
  GET  /admin/invoices/{id}/lines               → line items with taxonomy detail
  POST /admin/invoices/{id}/approve             → approve invoice (or specific lines)
  POST /admin/mappings/override                 → override a line's taxonomy mapping
  GET  /admin/mappings                          → review low-confidence mapping queue
  POST /admin/exceptions/{id}/resolve           → carrier resolves an exception
  GET  /admin/invoices/{id}/export              → export approved lines to CSV
"""

import csv
import io
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.audit import ActorType
from app.models.invoice import Invoice, LineItem, SubmissionStatus, LineItemStatus
from app.models.mapping import MappingRule, MatchType, ConfirmedBy
from app.models.supplier import User, UserRole
from app.models.validation import (
    ExceptionRecord, ExceptionStatus, ResolutionAction, ValidationStatus,
)
from app.routers.auth import get_current_user, require_role
from app.schemas.invoice import (
    ApprovalRequest, ExportResponse, LineItemCarrierView,
    InvoiceResponse, InvoiceListItem, MappingOverrideRequest,
    ValidationResultSupplierView, ExceptionSupplierView,
)
from app.services.audit import logger as audit

router = APIRouter(prefix="/admin", tags=["admin"])

_CARRIER_ROLES = (UserRole.CARRIER_ADMIN, UserRole.CARRIER_REVIEWER, UserRole.SYSTEM_ADMIN)


# ── Invoice Queue ─────────────────────────────────────────────────────────────

@router.get("/invoices", response_model=list[InvoiceListItem])
def list_pending_invoices(
    status_filter: str = "PENDING_CARRIER_REVIEW",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
) -> list[InvoiceListItem]:
    """
    Returns invoices awaiting carrier action.
    Default: PENDING_CARRIER_REVIEW. Pass ?status_filter=REVIEW_REQUIRED for exception queues.
    """
    invoices = (
        db.query(Invoice)
        .filter(Invoice.status == status_filter)
        .order_by(Invoice.submitted_at.asc())  # oldest first (FIFO queue)
        .all()
    )
    return [_to_invoice_list_item(inv) for inv in invoices]


# ── Invoice Detail (carrier view) ─────────────────────────────────────────────

@router.get("/invoices/{invoice_id}/lines", response_model=list[LineItemCarrierView])
def get_line_items_carrier(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
) -> list[LineItemCarrierView]:
    """Full line item detail including taxonomy codes and mapping internals."""
    invoice = _get_invoice(invoice_id, db)
    return [_to_line_item_carrier_view(li, db) for li in invoice.line_items]


# ── Mapping Override ──────────────────────────────────────────────────────────

@router.post("/mappings/override", status_code=status.HTTP_200_OK)
def override_mapping(
    payload: MappingOverrideRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CARRIER_ADMIN, UserRole.SYSTEM_ADMIN)),
) -> dict:
    """
    Carrier admin corrects the taxonomy classification for a line item.
    Optionally creates a persistent MappingRule so future invoices are auto-classified.
    """
    line_item = db.get(LineItem, payload.line_item_id)
    if line_item is None:
        raise HTTPException(status_code=404, detail="Line item not found")

    old_taxonomy = line_item.taxonomy_code

    # ── Update the line item ──────────────────────────────────────────────────
    line_item.taxonomy_code = payload.taxonomy_code
    line_item.billing_component = payload.billing_component
    line_item.mapping_confidence = "HIGH"
    line_item.status = LineItemStatus.OVERRIDE
    db.flush()

    audit.log_mapping_overridden(db, line_item, old_taxonomy, current_user.id)

    # ── Create persistent MappingRule (if scope > this_line) ─────────────────
    rule_id = None
    if payload.scope in ("this_supplier", "global"):
        supplier_id = None
        if payload.scope == "this_supplier":
            invoice = db.get(Invoice, line_item.invoice_id)
            supplier_id = invoice.supplier_id if invoice else None

        # Expire any existing active rule for this pattern
        existing = (
            db.query(MappingRule)
            .filter(
                MappingRule.match_pattern == line_item.raw_description,
                MappingRule.match_type == MatchType.KEYWORD_SET,
                MappingRule.effective_to.is_(None),
                MappingRule.supplier_id == supplier_id,
            )
            .first()
        )
        if existing:
            existing.effective_to = datetime.now(timezone.utc)
            db.flush()

        new_rule = MappingRule(
            supplier_id=supplier_id,
            match_type=MatchType.KEYWORD_SET,
            match_pattern=line_item.raw_description,
            taxonomy_code=payload.taxonomy_code,
            billing_component=payload.billing_component,
            confidence_weight=1.0,
            confidence_label="HIGH",
            confirmed_by=ConfirmedBy.CARRIER_OVERRIDE,
            confirmed_by_user_id=current_user.id,
            confirmed_at=datetime.now(timezone.utc),
            effective_from=datetime.now(timezone.utc),
            supersedes_rule_id=existing.id if existing else None,
            version=((existing.version + 1) if existing else 1),
            notes=payload.notes,
        )
        db.add(new_rule)
        db.flush()
        rule_id = new_rule.id

        audit.log_mapping_overridden(db, new_rule, old_taxonomy, current_user.id)

    db.commit()

    return {
        "message": f"Mapping updated to {payload.taxonomy_code}.",
        "scope": payload.scope,
        "rule_created": rule_id is not None,
        "rule_id": str(rule_id) if rule_id else None,
    }


# ── Mapping Review Queue ──────────────────────────────────────────────────────

@router.get("/mappings/review-queue")
def get_mapping_review_queue(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
) -> list[dict]:
    """
    Returns line items with LOW or MEDIUM mapping confidence for carrier review.
    These are lines where the system classified but isn't confident.
    """
    lines = (
        db.query(LineItem)
        .filter(LineItem.mapping_confidence.in_(["LOW", "MEDIUM"]))
        .order_by(LineItem.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "line_item_id": str(li.id),
            "invoice_id": str(li.invoice_id),
            "line_number": li.line_number,
            "raw_description": li.raw_description,
            "raw_code": li.raw_code,
            "taxonomy_code": li.taxonomy_code,
            "billing_component": li.billing_component,
            "mapping_confidence": li.mapping_confidence,
            "raw_amount": str(li.raw_amount),
        }
        for li in lines
    ]


# ── Exception Resolution ──────────────────────────────────────────────────────

@router.post("/exceptions/{exception_id}/resolve")
def resolve_exception(
    exception_id: uuid.UUID,
    resolution_action: str,
    resolution_notes: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CARRIER_ADMIN, UserRole.SYSTEM_ADMIN)),
) -> dict:
    """
    Carrier resolves an exception.
    resolution_action: WAIVED | HELD_CONTRACT_RATE | RECLASSIFIED | ACCEPTED_REDUCTION
    """
    valid_actions = {
        ResolutionAction.WAIVED, ResolutionAction.HELD_CONTRACT_RATE,
        ResolutionAction.RECLASSIFIED, ResolutionAction.ACCEPTED_REDUCTION,
    }
    if resolution_action not in valid_actions:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid resolution_action. Must be one of: {valid_actions}",
        )

    exc = db.get(ExceptionRecord, exception_id)
    if exc is None:
        raise HTTPException(status_code=404, detail="Exception not found")

    exc.status = ExceptionStatus.RESOLVED
    exc.resolution_action = resolution_action
    exc.resolution_notes = resolution_notes
    exc.resolved_at = datetime.now(timezone.utc)
    exc.resolved_by_user_id = current_user.id

    audit.log_exception_resolved(db, exc, actor_id=current_user.id)
    db.commit()

    return {"message": f"Exception resolved with action: {resolution_action}"}


# ── Approve Invoice ───────────────────────────────────────────────────────────

@router.post("/invoices/{invoice_id}/approve")
def approve_invoice(
    invoice_id: uuid.UUID,
    payload: ApprovalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CARRIER_ADMIN, UserRole.SYSTEM_ADMIN)),
) -> dict:
    """
    Approve an invoice (or specific line items).
    Sets status to APPROVED.
    """
    invoice = _get_invoice(invoice_id, db)

    if invoice.status not in (
        SubmissionStatus.PENDING_CARRIER_REVIEW, SubmissionStatus.CARRIER_REVIEWING
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot approve invoice in status '{invoice.status}'.",
        )

    # Approve specific lines or all lines
    line_ids = set(payload.line_item_ids) if payload.line_item_ids else None
    for li in invoice.line_items:
        if line_ids is None or li.id in line_ids:
            if li.status in (LineItemStatus.VALIDATED, LineItemStatus.OVERRIDE, LineItemStatus.RESOLVED):
                li.status = LineItemStatus.APPROVED

    old_status = invoice.status
    invoice.status = SubmissionStatus.APPROVED
    db.flush()

    audit.log_invoice_status_changed(
        db, invoice, from_status=old_status, to_status=SubmissionStatus.APPROVED,
        actor_type=ActorType.CARRIER, actor_id=current_user.id,
    )
    db.commit()

    return {"message": f"Invoice {invoice.invoice_number} approved."}


# ── Export ────────────────────────────────────────────────────────────────────

@router.get("/invoices/{invoice_id}/export")
def export_invoice(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
) -> Response:
    """
    Export approved line items as CSV for AP system import.
    Sets invoice status to EXPORTED (terminal state).
    """
    invoice = _get_invoice(invoice_id, db)

    if invoice.status != SubmissionStatus.APPROVED:
        raise HTTPException(
            status_code=409,
            detail=f"Invoice must be APPROVED before export (current: '{invoice.status}').",
        )

    approved_lines = [
        li for li in invoice.line_items if li.status == LineItemStatus.APPROVED
    ]
    if not approved_lines:
        raise HTTPException(status_code=422, detail="No approved lines to export")

    # ── Build CSV ─────────────────────────────────────────────────────────────
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "invoice_number", "claim_number", "service_date",
        "description", "taxonomy_code", "billing_component",
        "quantity", "unit", "billed_amount", "approved_amount",
    ])
    writer.writeheader()
    for li in approved_lines:
        writer.writerow({
            "invoice_number": invoice.invoice_number,
            "claim_number": li.claim_number or "",
            "service_date": li.service_date.isoformat() if li.service_date else "",
            "description": li.raw_description,
            "taxonomy_code": li.taxonomy_code or "",
            "billing_component": li.billing_component or "",
            "quantity": str(li.raw_quantity),
            "unit": li.raw_unit or "",
            "billed_amount": str(li.raw_amount),
            "approved_amount": str(li.expected_amount or li.raw_amount),
        })

    # ── Set invoice to EXPORTED (terminal) ────────────────────────────────────
    old_status = invoice.status
    invoice.status = SubmissionStatus.EXPORTED
    audit.log_invoice_status_changed(
        db, invoice, from_status=old_status, to_status=SubmissionStatus.EXPORTED,
        actor_type=ActorType.CARRIER, actor_id=current_user.id,
    )
    db.commit()

    csv_bytes = output.getvalue().encode("utf-8")
    filename = f"approved_{invoice.invoice_number}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"

    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Private helpers ───────────────────────────────────────────────────────────

def _get_invoice(invoice_id: uuid.UUID, db: Session) -> Invoice:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


def _to_invoice_list_item(invoice: Invoice) -> InvoiceListItem:
    total_billed = sum(li.raw_amount for li in invoice.line_items) if invoice.line_items else None
    exc_count = sum(
        1 for li in invoice.line_items
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


def _to_line_item_carrier_view(li: LineItem, db: Session) -> LineItemCarrierView:
    from app.models.taxonomy import TaxonomyItem
    taxonomy_label = None
    if li.taxonomy_code:
        item = db.get(TaxonomyItem, li.taxonomy_code)
        taxonomy_label = item.label if item else li.taxonomy_code

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
            severity=exc.validation_result.severity if exc.validation_result else "ERROR",
            required_action=exc.validation_result.required_action if exc.validation_result else "NONE",
            supplier_response=exc.supplier_response,
        )
        for exc in li.exceptions
    ]
    return LineItemCarrierView(
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
        taxonomy_code=li.taxonomy_code,
        taxonomy_label=taxonomy_label,
        billing_component=li.billing_component,
        mapped_unit_model=li.mapped_unit_model,
        mapping_confidence=li.mapping_confidence,
        mapped_rate=li.mapped_rate,
    )
