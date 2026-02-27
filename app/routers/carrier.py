"""
Carrier-facing API routes.

All queries are scoped to the current user's carrier_id via the contracts table.
A carrier user can NEVER see invoices belonging to another carrier's contracts.

Workflow:
  GET  /carrier/invoices                        → queue of invoices for this carrier
  GET  /carrier/invoices/{id}                   → invoice detail with validation summary
  GET  /carrier/invoices/{id}/lines             → line items with taxonomy + confidence
  POST /carrier/invoices/{id}/approve           → approve full invoice (waives open exceptions)
  POST /carrier/invoices/{id}/request-changes   → return invoice to supplier for correction
  POST /carrier/exceptions/{id}/resolve         → resolve a single exception with typed action
  GET  /carrier/invoices/{id}/export            → export approved lines as CSV (terminal)

Role guard policy:
  Read endpoints  → CARRIER_ADMIN, CARRIER_REVIEWER
  Write endpoints → CARRIER_ADMIN only
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.audit import ActorType
from app.models.invoice import Invoice, LineItem, LineItemStatus, SubmissionStatus
from app.models.supplier import Contract, User, UserRole
from app.models.validation import ExceptionRecord, ExceptionStatus, ResolutionAction
from app.routers.admin import _to_invoice_list_item, _to_line_item_carrier_view
from app.routers.auth import require_role
from app.routers.supplier import _to_invoice_response
from app.schemas.carrier import (
    CarrierApprovalRequest,
    CarrierExceptionResolvePayload,
    RequestChangesPayload,
)
from app.schemas.invoice import InvoiceListItem, InvoiceResponse, LineItemCarrierView
from app.services.audit import logger as audit

router = APIRouter(prefix="/carrier", tags=["carrier"])

_READ_ROLES = (UserRole.CARRIER_ADMIN, UserRole.CARRIER_REVIEWER)
_WRITE_ROLES = (UserRole.CARRIER_ADMIN,)


# ── Invoice Queue ─────────────────────────────────────────────────────────────


@router.get("/invoices", response_model=list[InvoiceListItem])
def list_carrier_invoices(
    status_filter: str = "PENDING_CARRIER_REVIEW",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_READ_ROLES)),
) -> list[InvoiceListItem]:
    """
    Return invoices belonging to this carrier's contracts, filtered by status.
    Default: PENDING_CARRIER_REVIEW (the review queue).
    Pass ?status_filter=APPROVED for approved invoice history, etc.
    Results are ordered oldest-first (FIFO queue).
    """
    carrier_contract_ids = (
        db.query(Contract.id)
        .filter(Contract.carrier_id == current_user.carrier_id)
        .subquery()
    )
    invoices = (
        db.query(Invoice)
        .filter(
            Invoice.contract_id.in_(carrier_contract_ids),
            Invoice.status == status_filter,
        )
        .order_by(Invoice.submitted_at.asc())
        .all()
    )
    return [_to_invoice_list_item(inv) for inv in invoices]


# ── Invoice Detail ────────────────────────────────────────────────────────────


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
def get_carrier_invoice_detail(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_READ_ROLES)),
) -> InvoiceResponse:
    """Single invoice detail with full validation summary. Verifies carrier ownership."""
    invoice = _get_carrier_invoice(invoice_id, current_user, db)
    return _to_invoice_response(invoice, db)


# ── Line Items ────────────────────────────────────────────────────────────────


@router.get("/invoices/{invoice_id}/lines", response_model=list[LineItemCarrierView])
def get_carrier_invoice_lines(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_READ_ROLES)),
) -> list[LineItemCarrierView]:
    """
    Full line item detail including taxonomy codes, mapping confidence, and exceptions.
    Carrier view exposes fields not visible to suppliers.
    """
    invoice = _get_carrier_invoice(invoice_id, current_user, db)
    return [_to_line_item_carrier_view(li, db) for li in invoice.line_items]


# ── Approve Invoice ───────────────────────────────────────────────────────────


@router.post("/invoices/{invoice_id}/approve", status_code=status.HTTP_200_OK)
def approve_carrier_invoice(
    invoice_id: uuid.UUID,
    payload: CarrierApprovalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_WRITE_ROLES)),
) -> dict:
    """
    Approve a full invoice.

    Before approving:
      - All remaining OPEN exceptions are force-transitioned to WAIVED.
      - All approvable line items (VALIDATED, OVERRIDE, RESOLVED, EXCEPTION) are set to APPROVED.
      - Invoice is set to APPROVED.

    Valid from: PENDING_CARRIER_REVIEW, CARRIER_REVIEWING
    """
    invoice = _get_carrier_invoice(invoice_id, current_user, db)

    if invoice.status not in (
        SubmissionStatus.PENDING_CARRIER_REVIEW,
        SubmissionStatus.CARRIER_REVIEWING,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot approve invoice in status '{invoice.status}'. "
            f"Invoice must be in PENDING_CARRIER_REVIEW or CARRIER_REVIEWING.",
        )

    now = datetime.now(timezone.utc)

    # Force-waive all remaining open exceptions
    for li in invoice.line_items:
        for exc in li.exceptions:
            if exc.status == ExceptionStatus.OPEN:
                exc.status = ExceptionStatus.WAIVED
                exc.resolution_action = ResolutionAction.WAIVED
                exc.resolution_notes = payload.notes or "Waived on invoice approval"
                exc.resolved_at = now
                exc.resolved_by_user_id = current_user.id
                audit.log_exception_resolved(db, exc, actor_id=current_user.id)

    # Approve all eligible line items (including EXCEPTION — just waived above)
    _approvable = {
        LineItemStatus.VALIDATED,
        LineItemStatus.OVERRIDE,
        LineItemStatus.RESOLVED,
        LineItemStatus.EXCEPTION,
    }
    for li in invoice.line_items:
        if li.status in _approvable:
            li.status = LineItemStatus.APPROVED

    old_status = invoice.status
    invoice.status = SubmissionStatus.APPROVED
    db.flush()

    audit.log_invoice_status_changed(
        db,
        invoice,
        from_status=old_status,
        to_status=SubmissionStatus.APPROVED,
        actor_type=ActorType.CARRIER,
        actor_id=current_user.id,
    )
    db.commit()

    return {"message": f"Invoice {invoice.invoice_number} approved."}


# ── Request Changes ───────────────────────────────────────────────────────────


@router.post("/invoices/{invoice_id}/request-changes", status_code=status.HTTP_200_OK)
def request_invoice_changes(
    invoice_id: uuid.UUID,
    payload: RequestChangesPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_WRITE_ROLES)),
) -> dict:
    """
    Return an invoice to the supplier for correction.

    Transitions: PENDING_CARRIER_REVIEW → REVIEW_REQUIRED
    Carrier notes are stored in the immutable audit event and returned in the response.
    The supplier will see the invoice return to REVIEW_REQUIRED status and can resubmit.
    """
    invoice = _get_carrier_invoice(invoice_id, current_user, db)

    if invoice.status != SubmissionStatus.PENDING_CARRIER_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"request-changes is only valid from PENDING_CARRIER_REVIEW "
                f"(current status: '{invoice.status}')."
            ),
        )

    old_status = invoice.status
    invoice.status = SubmissionStatus.REVIEW_REQUIRED
    db.flush()

    # Notes stored in audit log — no schema change needed, always recoverable
    audit.log_invoice_changes_requested(
        db,
        invoice,
        carrier_notes=payload.carrier_notes,
        actor_id=current_user.id,
    )
    audit.log_invoice_status_changed(
        db,
        invoice,
        from_status=old_status,
        to_status=SubmissionStatus.REVIEW_REQUIRED,
        actor_type=ActorType.CARRIER,
        actor_id=current_user.id,
    )
    db.commit()

    return {
        "message": "Invoice returned to supplier for correction.",
        "carrier_notes": payload.carrier_notes,
    }


# ── Resolve Exception ─────────────────────────────────────────────────────────


@router.post("/exceptions/{exception_id}/resolve", status_code=status.HTTP_200_OK)
def resolve_carrier_exception(
    exception_id: uuid.UUID,
    payload: CarrierExceptionResolvePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_WRITE_ROLES)),
) -> dict:
    """
    Resolve a single exception with a typed action and optional notes.
    Verifies the exception belongs to this carrier's invoice before resolving.

    resolution_action: WAIVED | HELD_CONTRACT_RATE | RECLASSIFIED | ACCEPTED_REDUCTION | DENIED

    DENIED marks the line item as non-payable (carrier-final). The line item status is
    set to DENIED and excluded from payable totals. No invoice resubmission is required.
    """
    exc = db.get(ExceptionRecord, exception_id)
    if exc is None:
        raise HTTPException(status_code=404, detail="Exception not found")

    # Verify carrier ownership: exception → line item → invoice → contract
    line_item = db.get(LineItem, exc.line_item_id)
    if line_item is None:
        raise HTTPException(status_code=404, detail="Line item not found")

    # _get_carrier_invoice raises 403 if the invoice doesn't belong to this carrier
    _get_carrier_invoice(line_item.invoice_id, current_user, db)

    if exc.status not in (ExceptionStatus.OPEN, ExceptionStatus.SUPPLIER_RESPONDED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Exception in status '{exc.status}' cannot be resolved. "
                f"Only OPEN or SUPPLIER_RESPONDED exceptions can be resolved."
            ),
        )

    # WAIVED gets its own terminal status; all other actions → RESOLVED
    exc.status = (
        ExceptionStatus.WAIVED
        if payload.resolution_action == ResolutionAction.WAIVED
        else ExceptionStatus.RESOLVED
    )
    exc.resolution_action = payload.resolution_action
    exc.resolution_notes = payload.resolution_notes
    exc.resolved_at = datetime.now(timezone.utc)
    exc.resolved_by_user_id = current_user.id

    # DENIED: transition the line item to a non-payable terminal state
    if payload.resolution_action == ResolutionAction.DENIED:
        line_item.status = LineItemStatus.DENIED

    audit.log_exception_resolved(db, exc, actor_id=current_user.id)
    db.commit()

    return {"message": f"Exception resolved with action: {payload.resolution_action}"}


# ── Export ────────────────────────────────────────────────────────────────────


@router.get("/invoices/{invoice_id}/export")
def export_carrier_invoice(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_READ_ROLES)),
) -> Response:
    """
    Export approved line items as CSV for AP system import.
    Sets invoice status to EXPORTED (terminal state — cannot be un-exported).
    Invoice must be in APPROVED status before export is allowed.
    """
    import csv
    import io

    invoice = _get_carrier_invoice(invoice_id, current_user, db)

    if invoice.status != SubmissionStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invoice must be APPROVED before export (current: '{invoice.status}').",
        )

    approved_lines = [
        li for li in invoice.line_items if li.status == LineItemStatus.APPROVED
    ]
    if not approved_lines:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No approved lines to export",
        )

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "invoice_number",
            "claim_number",
            "service_date",
            "description",
            "taxonomy_code",
            "billing_component",
            "quantity",
            "unit",
            "billed_amount",
            "approved_amount",
        ],
    )
    writer.writeheader()
    for li in approved_lines:
        writer.writerow(
            {
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
            }
        )

    old_status = invoice.status
    invoice.status = SubmissionStatus.EXPORTED
    audit.log_invoice_status_changed(
        db,
        invoice,
        from_status=old_status,
        to_status=SubmissionStatus.EXPORTED,
        actor_type=ActorType.CARRIER,
        actor_id=current_user.id,
    )
    db.commit()

    csv_bytes = output.getvalue().encode("utf-8")
    filename = (
        f"approved_{invoice.invoice_number}_"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    )
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Private helpers ───────────────────────────────────────────────────────────


def _get_carrier_invoice(invoice_id: uuid.UUID, user: User, db: Session) -> Invoice:
    """
    Fetch invoice by ID and verify it belongs to the current carrier.

    Raises:
        404 if invoice does not exist.
        403 if the invoice belongs to a different carrier's contract.
    """
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")

    contract = db.get(Contract, invoice.contract_id)
    if contract is None or contract.carrier_id != user.carrier_id:
        raise HTTPException(status_code=403, detail="Access denied")

    return invoice
