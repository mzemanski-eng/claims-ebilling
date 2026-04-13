"""
Carrier-facing API routes.

All queries are scoped to the current user's carrier_id via the contracts table.
A carrier user can NEVER see invoices belonging to another carrier's contracts.

Workflow:
  GET  /carrier/invoices                            → queue of invoices for this carrier
  GET  /carrier/invoices/{id}                       → invoice detail with validation summary
  GET  /carrier/invoices/{id}/lines                 → line items with taxonomy + confidence
  POST /carrier/invoices/{id}/approve               → approve full invoice (waives open exceptions)
  POST /carrier/invoices/{id}/request-changes       → return invoice to supplier for correction
  POST /carrier/exceptions/{id}/resolve             → resolve a single exception with typed action
  GET  /carrier/invoices/{id}/export                → export approved lines as CSV (terminal)

  GET  /carrier/classification                      → Classification Review queue for this carrier
  GET  /carrier/classification/stats                → pending count, needs_review count, totals
  POST /carrier/classification/{item_id}/approve    → confirm taxonomy; run bill audit on line
  POST /carrier/classification/{item_id}/reject     → reject line (marks DENIED)

Role guard policy:
  Read endpoints  → CARRIER_ADMIN, CARRIER_REVIEWER
  Write endpoints → CARRIER_ADMIN only
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.audit import ActorType
from app.models.classification import ClassificationQueueItem, ClassificationQueueStatus
from app.models.invoice import Invoice, LineItem, LineItemStatus, SubmissionStatus
from app.models.mapping import ConfirmedBy
from app.models.supplier import Contract, User, UserRole
from app.models.validation import (
    ExceptionRecord,
    ExceptionStatus,
    ResolutionAction,
    ValidationResult,
    ValidationStatus,
)
from app.routers.admin import _to_invoice_list_item, _to_line_item_carrier_view
from app.routers.auth import require_role
from app.routers.supplier import _to_invoice_response
from app.schemas.carrier import (
    CarrierApprovalRequest,
    CarrierExceptionResolvePayload,
    RequestChangesPayload,
)
from app.schemas.classification import (
    ClassificationApproveRequest,
    ClassificationApproveResult,
    ClassificationQueueItemSummary,
    ClassificationRejectRequest,
    ClassificationStats,
)
from app.schemas.invoice import InvoiceListItem, InvoiceResponse, LineItemCarrierView
from app.services.audit import logger as audit
from app.services.classification.mapping_learner import record_confirmed_mapping
from app.services.validation.guideline_validator import GuidelineValidator
from app.services.validation.rate_validator import RateValidator

logger = logging.getLogger(__name__)

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


# ── Classification Review ──────────────────────────────────────────────────────


@router.get(
    "/classification",
    response_model=list[ClassificationQueueItemSummary],
)
def list_classification_queue(
    status_filter: str = "PENDING",
    invoice_id: uuid.UUID | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_READ_ROLES)),
) -> list[ClassificationQueueItemSummary]:
    """
    Return classification queue items for this carrier's suppliers.

    status_filter: PENDING (default) | NEEDS_REVIEW | APPROVED | REJECTED
    invoice_id: optional UUID to restrict results to a single invoice's lines.
    Results ordered oldest-first so reviewers work through the backlog in FIFO order.
    """
    # Collect all supplier IDs that have an active contract with this carrier
    carrier_supplier_ids = (
        db.query(Contract.supplier_id)
        .filter(Contract.carrier_id == current_user.carrier_id)
        .subquery()
    )

    query = db.query(ClassificationQueueItem).filter(
        ClassificationQueueItem.supplier_id.in_(carrier_supplier_ids),
        ClassificationQueueItem.status == status_filter,
    )

    # Optional: narrow to a specific invoice by joining through line_item
    if invoice_id is not None:
        query = query.join(
            LineItem,
            ClassificationQueueItem.line_item_id == LineItem.id,
        ).filter(LineItem.invoice_id == invoice_id)

    items = query.order_by(ClassificationQueueItem.created_at.asc()).all()

    return [_to_classification_summary(item, db) for item in items]


@router.get("/classification/stats", response_model=ClassificationStats)
def get_classification_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_READ_ROLES)),
) -> ClassificationStats:
    """
    Summary counts and totals for the Classification Review screen header.
    """
    from sqlalchemy import func

    carrier_supplier_ids = (
        db.query(Contract.supplier_id)
        .filter(Contract.carrier_id == current_user.carrier_id)
        .subquery()
    )
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    base = db.query(ClassificationQueueItem).filter(
        ClassificationQueueItem.supplier_id.in_(carrier_supplier_ids)
    )

    pending_count = base.filter(
        ClassificationQueueItem.status == ClassificationQueueStatus.PENDING
    ).count()

    needs_review_count = base.filter(
        ClassificationQueueItem.status == ClassificationQueueStatus.NEEDS_REVIEW
    ).count()

    approved_today = base.filter(
        ClassificationQueueItem.status == ClassificationQueueStatus.APPROVED,
        ClassificationQueueItem.reviewed_at >= today_start,
    ).count()

    rejected_today = base.filter(
        ClassificationQueueItem.status == ClassificationQueueStatus.REJECTED,
        ClassificationQueueItem.reviewed_at >= today_start,
    ).count()

    total_pending_amount_row = (
        base.filter(
            ClassificationQueueItem.status.in_(
                [
                    ClassificationQueueStatus.PENDING,
                    ClassificationQueueStatus.NEEDS_REVIEW,
                ]
            )
        )
        .with_entities(func.coalesce(func.sum(ClassificationQueueItem.raw_amount), 0))
        .one()
    )
    total_pending_amount = total_pending_amount_row[0]

    return ClassificationStats(
        pending=pending_count,
        needs_review=needs_review_count,
        approved_today=approved_today,
        rejected_today=rejected_today,
        total_pending_amount=total_pending_amount,
    )


@router.post(
    "/classification/{item_id}/approve",
    response_model=ClassificationApproveResult,
    status_code=status.HTTP_200_OK,
)
def approve_classification_item(
    item_id: uuid.UUID,
    payload: ClassificationApproveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_WRITE_ROLES)),
) -> ClassificationApproveResult:
    """
    Approve a classification queue item.

    Steps:
      1. Confirm taxonomy code on the line item (CLASSIFIED).
      2. Create a CARRIER_CONFIRMED MappingRule via mapping_learner.
      3. Run bill audit (rate + guideline validation) on the line.
      4. Advance the line to VALIDATED or EXCEPTION.
      5. If all CLASSIFICATION_PENDING lines for this invoice are resolved and
         new spend exceptions exist, transition invoice to REVIEW_REQUIRED.
    """
    item = db.get(ClassificationQueueItem, item_id)
    if item is None:
        raise HTTPException(
            status_code=404, detail="Classification queue item not found"
        )

    _verify_classification_carrier_access(item, current_user, db)

    if item.status not in (
        ClassificationQueueStatus.PENDING,
        ClassificationQueueStatus.NEEDS_REVIEW,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Item in status '{item.status}' cannot be approved. "
                "Only PENDING or NEEDS_REVIEW items can be approved."
            ),
        )

    now = datetime.now(timezone.utc)
    line_item = db.get(LineItem, item.line_item_id)
    if line_item is None:
        raise HTTPException(status_code=404, detail="Associated line item not found")

    # ── 1. Update line item with confirmed taxonomy ───────────────────────────
    line_item.taxonomy_code = payload.approved_code
    line_item.billing_component = payload.approved_billing_component
    line_item.mapping_confidence = "HIGH"
    line_item.mapping_rule_id = None  # will be set once rule is created
    line_item.status = LineItemStatus.CLASSIFIED
    db.flush()

    # ── 2. Write confirmed mapping to MappingRule corpus ─────────────────────
    # Determine provenance: CONFIRMED if AI suggested the same code, OVERRIDE otherwise.
    confirmed_by = (
        ConfirmedBy.CARRIER_CONFIRMED
        if payload.approved_code == item.ai_proposed_code
        else ConfirmedBy.CARRIER_OVERRIDE
    )
    new_rule = record_confirmed_mapping(
        db=db,
        line_item=line_item,
        taxonomy_code=payload.approved_code,
        billing_component=payload.approved_billing_component,
        source=confirmed_by,
        user_id=current_user.id,
        scope="this_supplier",
        notes=payload.review_notes,
    )
    mapping_rule_created = new_rule is not None

    # ── 3 & 4. Run bill audit and update line status ──────────────────────────
    invoice = db.get(Invoice, line_item.invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Associated invoice not found")

    bill_audit_status = _run_post_classification_bill_audit(db, line_item, invoice)

    # ── Update queue item ─────────────────────────────────────────────────────
    item.status = ClassificationQueueStatus.APPROVED
    item.reviewed_by_id = current_user.id
    item.reviewed_at = now
    item.approved_code = payload.approved_code
    item.approved_billing_component = payload.approved_billing_component
    item.review_notes = payload.review_notes
    if new_rule is not None:
        item.created_mapping_rule_id = new_rule.id
        line_item.mapping_rule_id = new_rule.id

    db.flush()

    # ── 5. Update invoice status if all classification queue items resolved ───
    _recalculate_invoice_status_after_classification(db, invoice)

    db.commit()

    return ClassificationApproveResult(
        queue_item_id=item.id,
        line_item_id=line_item.id,
        approved_code=payload.approved_code,
        bill_audit_result=bill_audit_status,
        mapping_rule_created=mapping_rule_created,
        message=(
            f"Line classified as '{payload.approved_code}'. "
            f"Bill audit result: {bill_audit_status}."
        ),
    )


@router.post(
    "/classification/{item_id}/reject",
    status_code=status.HTTP_200_OK,
)
def reject_classification_item(
    item_id: uuid.UUID,
    payload: ClassificationRejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_WRITE_ROLES)),
) -> dict:
    """
    Reject a classification queue item.

    The associated line item is marked DENIED — it will not be paid.
    A CARRIER_CONFIRMED MappingRule is NOT created (we have no confirmed code).
    """
    item = db.get(ClassificationQueueItem, item_id)
    if item is None:
        raise HTTPException(
            status_code=404, detail="Classification queue item not found"
        )

    _verify_classification_carrier_access(item, current_user, db)

    if item.status not in (
        ClassificationQueueStatus.PENDING,
        ClassificationQueueStatus.NEEDS_REVIEW,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Item in status '{item.status}' cannot be rejected. "
                "Only PENDING or NEEDS_REVIEW items can be rejected."
            ),
        )

    now = datetime.now(timezone.utc)

    # Mark queue item REJECTED
    item.status = ClassificationQueueStatus.REJECTED
    item.reviewed_by_id = current_user.id
    item.reviewed_at = now
    item.review_notes = payload.review_notes

    # Mark the line DENIED — carrier will not pay an unclassifiable line
    line_item = db.get(LineItem, item.line_item_id)
    if line_item is not None:
        line_item.status = LineItemStatus.DENIED

    db.flush()

    # Recalculate invoice status
    invoice = db.get(Invoice, line_item.invoice_id) if line_item else None
    if invoice:
        _recalculate_invoice_status_after_classification(db, invoice)

    db.commit()

    return {"message": "Classification item rejected. Line marked as DENIED."}


# ── Private helpers ───────────────────────────────────────────────────────────


def _to_classification_summary(
    item: ClassificationQueueItem, db: Session
) -> ClassificationQueueItemSummary:
    """Convert ORM item to summary schema, joining supplier name and invoice context."""
    from app.models.supplier import Supplier

    supplier_name = None
    supplier = db.get(Supplier, item.supplier_id)
    if supplier:
        supplier_name = supplier.name

    invoice_id = None
    invoice_number = None
    line_number = None
    line_item = db.get(LineItem, item.line_item_id)
    if line_item:
        line_number = line_item.line_number
        invoice = db.get(Invoice, line_item.invoice_id)
        if invoice:
            invoice_id = invoice.id
            invoice_number = invoice.invoice_number

    # Deserialise ai_alternatives JSONB list into schema objects
    alternatives = None
    if item.ai_alternatives:
        from app.schemas.classification import ClassificationAlternative

        try:
            alternatives = [
                ClassificationAlternative(**a) for a in item.ai_alternatives
            ]
        except Exception:
            alternatives = None

    return ClassificationQueueItemSummary(
        id=item.id,
        created_at=item.created_at,
        updated_at=item.updated_at,
        line_item_id=item.line_item_id,
        supplier_id=item.supplier_id,
        supplier_name=supplier_name,
        invoice_id=invoice_id,
        invoice_number=invoice_number,
        line_number=line_number,
        raw_description=item.raw_description,
        raw_amount=item.raw_amount,
        ai_proposed_code=item.ai_proposed_code,
        ai_proposed_billing_component=item.ai_proposed_billing_component,
        ai_confidence=item.ai_confidence,
        ai_reasoning=item.ai_reasoning,
        ai_alternatives=alternatives,
        status=item.status,
        reviewed_by_id=item.reviewed_by_id,
        reviewed_at=item.reviewed_at,
        approved_code=item.approved_code,
        approved_billing_component=item.approved_billing_component,
        review_notes=item.review_notes,
        created_mapping_rule_id=item.created_mapping_rule_id,
    )


def _verify_classification_carrier_access(
    item: ClassificationQueueItem, user: User, db: Session
) -> None:
    """
    Raise 403 if the queue item's supplier does not have a contract with this carrier.
    """
    contract = (
        db.query(Contract)
        .filter(
            Contract.supplier_id == item.supplier_id,
            Contract.carrier_id == user.carrier_id,
        )
        .first()
    )
    if contract is None:
        raise HTTPException(
            status_code=403,
            detail="Access denied: this classification item does not belong to your carrier.",
        )


def _run_post_classification_bill_audit(
    db: Session,
    line_item: LineItem,
    invoice: Invoice,
) -> str:
    """
    Run rate and guideline validation on a line item after its taxonomy has been
    confirmed in the Classification Review queue.

    Creates ValidationResult and ExceptionRecord rows as needed, updates
    line_item.status and line_item.expected_amount, and returns the final status:
      "VALIDATED" — all checks passed
      "EXCEPTION" — one or more rate/guideline failures found
    """
    contract = invoice.contract
    if contract is None:
        logger.warning(
            "post-classification bill audit: contract not found for invoice %s",
            invoice.id,
        )
        line_item.status = LineItemStatus.VALIDATED
        return "VALIDATED"

    guidelines = [g for g in contract.guidelines if g.is_active]

    rate_validator = RateValidator(db)
    guideline_validator = GuidelineValidator()

    error_count = 0
    expected_amount = float(line_item.raw_amount)

    # ── Rate validation ───────────────────────────────────────────────────────
    rate_results = rate_validator.validate(line_item, contract)
    for rate_result in rate_results:
        val = ValidationResult(
            line_item_id=line_item.id,
            validation_type=rate_result.validation_type,
            rate_card_id=uuid.UUID(rate_result.rate_card_id)
            if rate_result.rate_card_id
            else None,
            status=rate_result.status,
            severity=rate_result.severity,
            message=rate_result.message,
            expected_value=rate_result.expected_value,
            actual_value=rate_result.actual_value,
            required_action=rate_result.required_action,
        )
        db.add(val)
        db.flush()

        if rate_result.status == ValidationStatus.FAIL:
            exc_record = ExceptionRecord(
                line_item_id=line_item.id,
                validation_result_id=val.id,
                status=ExceptionStatus.OPEN,
            )
            db.add(exc_record)
            audit.log_line_item_exception_opened(db, line_item, rate_result)
            error_count += 1
            if rate_result.expected_value:
                try:
                    expected_amount = float(
                        rate_result.expected_value.replace("$", "").replace(",", "")
                    )
                except (ValueError, AttributeError):
                    pass

    # ── Guideline validation ──────────────────────────────────────────────────
    guide_results = guideline_validator.validate(line_item, guidelines)
    for guide_result in guide_results:
        val = ValidationResult(
            line_item_id=line_item.id,
            validation_type=guide_result.validation_type,
            guideline_id=uuid.UUID(guide_result.guideline_id)
            if guide_result.guideline_id
            else None,
            status=guide_result.status,
            severity=guide_result.severity,
            message=guide_result.message,
            expected_value=guide_result.expected_value,
            actual_value=guide_result.actual_value,
            required_action=guide_result.required_action,
        )
        db.add(val)
        db.flush()

        if guide_result.status == ValidationStatus.FAIL:
            exc_record = ExceptionRecord(
                line_item_id=line_item.id,
                validation_result_id=val.id,
                status=ExceptionStatus.OPEN,
            )
            db.add(exc_record)
            audit.log_line_item_exception_opened(db, line_item, guide_result)
            error_count += 1

    line_item.status = (
        LineItemStatus.EXCEPTION if error_count > 0 else LineItemStatus.VALIDATED
    )
    line_item.expected_amount = expected_amount
    db.flush()

    return "EXCEPTION" if error_count > 0 else "VALIDATED"


def _recalculate_invoice_status_after_classification(
    db: Session,
    invoice: Invoice,
) -> None:
    """
    After one or more classification queue items are resolved, check whether the
    invoice should transition to REVIEW_REQUIRED (newly discovered spend exceptions).

    Rules:
      - If any CLASSIFICATION_PENDING lines remain → leave invoice unchanged
        (more classification work to do before bill audit can conclude).
      - If no CLASSIFICATION_PENDING lines remain AND open spend exceptions exist
        → transition to REVIEW_REQUIRED so the supplier is notified.
      - Otherwise leave at PENDING_CARRIER_REVIEW for the carrier to finalise.
    """
    pending_remaining = (
        db.query(LineItem)
        .filter(
            LineItem.invoice_id == invoice.id,
            LineItem.status == LineItemStatus.CLASSIFICATION_PENDING,
        )
        .count()
    )

    if pending_remaining > 0:
        # More items still pending — don't touch invoice status yet.
        return

    # All classification items resolved: check for new spend exceptions.
    open_spend_exceptions = (
        db.query(ExceptionRecord)
        .join(LineItem, LineItem.id == ExceptionRecord.line_item_id)
        .filter(
            LineItem.invoice_id == invoice.id,
            ExceptionRecord.status == ExceptionStatus.OPEN,
        )
        .count()
    )

    if (
        open_spend_exceptions > 0
        and invoice.status == SubmissionStatus.PENDING_CARRIER_REVIEW
    ):
        invoice.status = SubmissionStatus.REVIEW_REQUIRED
        audit.log_invoice_status_changed(
            db,
            invoice,
            from_status=SubmissionStatus.PENDING_CARRIER_REVIEW,
            to_status=SubmissionStatus.REVIEW_REQUIRED,
            actor_type=ActorType.CARRIER,
            actor_id=None,
        )
        logger.info(
            "Invoice %s → REVIEW_REQUIRED after classification resolution "
            "(%d open spend exceptions discovered)",
            invoice.id,
            open_spend_exceptions,
        )


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
