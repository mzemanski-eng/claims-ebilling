"""
Carrier admin API routes.

Workflow:
  GET  /admin/invoices                          → queue of invoices pending review
  GET  /admin/invoices/{id}/lines               → line items with taxonomy detail
  POST /admin/invoices/{id}/approve             → approve invoice (or specific lines)
  POST /admin/invoices/bulk-approve             → approve multiple invoices at once
  DELETE /admin/invoices/{id}                   → delete invoice (staging only)
  POST /admin/mappings/override                 → override a line's taxonomy mapping
  GET  /admin/mappings/review-queue             → review low-confidence mapping queue
  POST /admin/exceptions/{id}/resolve           → carrier resolves an exception
  GET  /admin/invoices/{id}/export              → export approved lines to CSV
  GET  /admin/suppliers                         → list all suppliers
  POST /admin/suppliers                         → create a new supplier
  GET  /admin/suppliers/{id}/users              → list user accounts for a supplier
  POST /admin/suppliers/{id}/users              → create a login for a supplier
  POST /admin/suppliers/{id}/audit              → AI audit report (on-demand, no DB write)
  GET  /admin/contracts                         → list all contracts
  GET  /admin/contracts/{id}                    → contract detail with rate cards + guidelines
  POST /admin/contracts                         → create contract
  POST /admin/contracts/parse-pdf               → AI PDF extraction (no DB write)
  POST /admin/contracts/{id}/rate-cards         → add rate card
  DELETE /admin/contracts/{id}/rate-cards/{rc}  → delete rate card
  POST /admin/contracts/{id}/guidelines         → add guideline
  PUT  /admin/contracts/{id}/guidelines/{g}     → toggle is_active
  DELETE /admin/contracts/{id}/guidelines/{g}   → delete guideline
"""

import csv
import io
import uuid
from datetime import date as date_type, datetime, timedelta, timezone

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.audit import ActorType
from app.models.invoice import Invoice, LineItem, LineItemStatus, SubmissionStatus
from app.models.mapping import ConfirmedBy, MatchType, MappingRule
from app.models.supplier import Contract, Guideline, RateCard, Supplier, User, UserRole
from app.models.taxonomy import TaxonomyItem
from app.schemas.contracts import (
    ContractCreate,
    ContractDetail,
    GuidelineCreate,
    GuidelineDetail,
    RateCardCreate,
    RateCardDetail,
)
from app.models.validation import (
    ExceptionRecord,
    ExceptionStatus,
    ResolutionAction,
)
from app.routers.auth import require_role
from app.schemas.invoice import (
    ApprovalRequest,
    BulkApprovalRequest,
    ExceptionSupplierView,
    InvoiceListItem,
    LineItemCarrierView,
    MappingOverrideRequest,
    ValidationResultSupplierView,
)
from app.services.ai_assessment.supplier_auditor import audit_supplier
from app.services.audit import logger as audit
from app.services.notifications.email import notify_exception_resolved
from app.settings import settings

router = APIRouter(prefix="/admin", tags=["admin"])

_CARRIER_ROLES = (
    UserRole.CARRIER_ADMIN,
    UserRole.CARRIER_REVIEWER,
    UserRole.SYSTEM_ADMIN,
)


# ── Invoice Queue ─────────────────────────────────────────────────────────────


@router.get("/invoices", response_model=list[InvoiceListItem])
def list_pending_invoices(
    status_filter: str | None = None,
    search: str | None = None,
    supplier_id: str | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
) -> list[InvoiceListItem]:
    """
    Returns invoices, newest first. All filters are optional and combinable:
      ?status_filter=PENDING_CARRIER_REVIEW
      &search=INV-001          (case-insensitive invoice_number match)
      &supplier_id=<uuid>
      &date_from=2025-01-01    (submitted_at range, inclusive)
      &date_to=2025-12-31
    """
    q = (
        db.query(Invoice)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(Contract.carrier_id == current_user.carrier_id)
        .order_by(Invoice.submitted_at.desc().nulls_last())
    )
    if status_filter:
        q = q.filter(Invoice.status == status_filter)
    if search:
        q = q.filter(Invoice.invoice_number.ilike(f"%{search}%"))
    if supplier_id:
        q = q.filter(Invoice.supplier_id == supplier_id)
    if date_from:
        q = q.filter(Invoice.submitted_at >= date_from)
    if date_to:
        q = q.filter(Invoice.submitted_at < date_to + timedelta(days=1))
    return [_to_invoice_list_item(inv) for inv in q.all()]


# ── Invoice Detail (admin / carrier view) ─────────────────────────────────────


@router.get("/invoices/{invoice_id}")
def get_invoice_detail(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
) -> dict:
    """Single invoice detail with supplier + contract metadata (admin enrichment)."""
    from app.routers.supplier import _to_invoice_response

    invoice = _get_invoice(invoice_id, db, current_user)
    base = _to_invoice_response(invoice, db)
    return {
        **base.model_dump(),
        "supplier_name": invoice.supplier.name if invoice.supplier else None,
        "contract_name": invoice.contract.name if invoice.contract else None,
        "triage_risk_level": invoice.triage_risk_level,
        "triage_notes": invoice.triage_notes,
    }


@router.get("/invoices/{invoice_id}/lines", response_model=list[LineItemCarrierView])
def get_line_items_carrier(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
) -> list[LineItemCarrierView]:
    """Full line item detail including taxonomy codes and mapping internals."""
    invoice = _get_invoice(invoice_id, db, current_user)
    return [_to_line_item_carrier_view(li, db) for li in invoice.line_items]


# ── Mapping Override ──────────────────────────────────────────────────────────


@router.post("/mappings/override", status_code=status.HTTP_200_OK)
def override_mapping(
    payload: MappingOverrideRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.CARRIER_ADMIN, UserRole.SYSTEM_ADMIN)
    ),
) -> dict:
    """
    Carrier admin corrects the taxonomy classification for a line item.
    Optionally creates a persistent MappingRule so future invoices are auto-classified.
    """
    line_item = db.get(LineItem, payload.line_item_id)
    if line_item is None:
        raise HTTPException(status_code=404, detail="Line item not found")

    # Verify this line item belongs to the current carrier
    _inv = db.get(Invoice, line_item.invoice_id)
    _contract = db.get(Contract, _inv.contract_id) if _inv else None
    if _contract is None or _contract.carrier_id != current_user.carrier_id:
        raise HTTPException(status_code=403, detail="Access denied")

    old_taxonomy = line_item.taxonomy_code

    # ── Update the line item ──────────────────────────────────────────────────
    line_item.taxonomy_code = payload.taxonomy_code
    line_item.billing_component = payload.billing_component
    line_item.mapping_confidence = "HIGH"
    line_item.status = LineItemStatus.OVERRIDE
    db.flush()

    audit.log_event(
        db,
        "line_item",
        line_item.id,
        "line_item.mapping_overridden",
        payload={
            "old_taxonomy_code": old_taxonomy,
            "new_taxonomy_code": line_item.taxonomy_code,
            "billing_component": line_item.billing_component,
            "scope": payload.scope,
        },
        actor_type=ActorType.CARRIER,
        actor_id=current_user.id,
    )

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
    Returns line items requiring mapping review:
      - LOW or MEDIUM confidence mappings (classified but uncertain)
      - UNRECOGNIZED lines (taxonomy_code IS NULL, status = EXCEPTION)

    Scoped to the current carrier. If the user has category_scope or
    supplier_scope set, the queue is pre-filtered to their assigned domains /
    suppliers. Unclassified lines (NULL taxonomy_code) always appear regardless
    of scope so they can be triaged.
    """
    from sqlalchemy import or_

    q = (
        db.query(LineItem)
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            Contract.carrier_id == current_user.carrier_id,
            (LineItem.mapping_confidence.in_(["LOW", "MEDIUM"]))
            | (LineItem.taxonomy_code.is_(None) & (LineItem.status == "EXCEPTION")),
        )
    )

    # Auditor scope: filter classified lines to assigned taxonomy domains
    if current_user.category_scope:
        domain_filters = [
            LineItem.taxonomy_code.like(f"{domain}.%")
            for domain in current_user.category_scope
        ]
        # Always include unclassified lines (NULL taxonomy) — they need triage
        q = q.filter(or_(*domain_filters, LineItem.taxonomy_code.is_(None)))

    # Auditor scope: filter to assigned suppliers
    if current_user.supplier_scope:
        q = q.filter(Invoice.supplier_id.in_(current_user.supplier_scope))

    lines = q.order_by(LineItem.created_at.desc()).limit(100).all()
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
            "ai_classification_suggestion": li.ai_classification_suggestion,
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
    current_user: User = Depends(
        require_role(UserRole.CARRIER_ADMIN, UserRole.SYSTEM_ADMIN)
    ),
) -> dict:
    """
    Carrier resolves an exception.

    resolution_action options:
      WAIVED            — rule waived for this instance; line accepted as billed
      ACCEPTED_REDUCTION— supplier agreed to reduced amount (rate/cap exception)
      HELD_CONTRACT_RATE— contract rate enforced; supplier accepts reduction
      RECLASSIFIED      — line reclassified to a different taxonomy code
      DENIED            — line rejected; supplier must correct and resubmit

    After resolving:
    - Accepting actions (all except DENIED) promote the line to APPROVED if no
      other open exceptions remain on that line.
    - When all exceptions on the invoice reach a terminal state, the invoice
      advances from REVIEW_REQUIRED → PENDING_CARRIER_REVIEW automatically.
    - If AUTO_APPROVE_CLEAN_INVOICES is enabled and no lines remain in EXCEPTION
      status, the invoice advances directly to APPROVED.
    """
    # ── Accepting actions promote the line; DENIED leaves it flagged ─────────
    _ACCEPTING = {
        ResolutionAction.WAIVED,
        ResolutionAction.HELD_CONTRACT_RATE,
        ResolutionAction.RECLASSIFIED,
        ResolutionAction.ACCEPTED_REDUCTION,
    }
    valid_actions = _ACCEPTING | {ResolutionAction.DENIED}
    if resolution_action not in valid_actions:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid resolution_action. Must be one of: {sorted(valid_actions)}",
        )

    exc = db.get(ExceptionRecord, exception_id)
    if exc is None:
        raise HTTPException(status_code=404, detail="Exception not found")

    # Verify this exception belongs to the current carrier
    _exc_contract = db.get(Contract, exc.line_item.invoice.contract_id)
    if _exc_contract is None or _exc_contract.carrier_id != current_user.carrier_id:
        raise HTTPException(status_code=403, detail="Access denied")

    _ACTIVE_STATUSES = {
        ExceptionStatus.OPEN,
        ExceptionStatus.SUPPLIER_RESPONDED,
        ExceptionStatus.CARRIER_REVIEWING,
    }
    if exc.status not in _ACTIVE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Exception is already in a terminal state: {exc.status}",
        )

    # ── Resolve the exception record ──────────────────────────────────────────
    exc.status = ExceptionStatus.RESOLVED
    exc.resolution_action = resolution_action
    exc.resolution_notes = resolution_notes or None
    exc.resolved_at = datetime.now(timezone.utc)
    exc.resolved_by_user_id = current_user.id

    # ── AI accuracy tracking ───────────────────────────────────────────────────
    # Record whether the carrier accepted the AI recommendation.
    # NULL means no AI recommendation existed at resolution time.
    if exc.ai_recommendation is not None:
        exc.ai_recommendation_accepted = resolution_action == exc.ai_recommendation

    db.flush()

    audit.log_exception_resolved(db, exc, actor_id=current_user.id)

    # ── Promote line item if this was an accepting resolution ─────────────────
    line_item = exc.line_item
    if resolution_action in _ACCEPTING:
        other_open_on_line = [
            e
            for e in line_item.exceptions
            if e.id != exc.id and e.status in _ACTIVE_STATUSES
        ]
        if not other_open_on_line:
            line_item.status = LineItemStatus.APPROVED

    # ── Auto-advance invoice if all exceptions are now resolved ───────────────
    invoice = line_item.invoice
    if invoice.status == SubmissionStatus.REVIEW_REQUIRED:
        remaining_open = [
            e
            for li in invoice.line_items
            for e in li.exceptions
            if e.id != exc.id and e.status in _ACTIVE_STATUSES
        ]
        if not remaining_open:
            old_inv_status = invoice.status
            # If any lines are still EXCEPTION (DENIED), require manual approve.
            # Otherwise auto-approve if configured.
            exception_lines = [
                li for li in invoice.line_items if li.status == LineItemStatus.EXCEPTION
            ]
            if settings.auto_approve_clean_invoices and not exception_lines:
                invoice.status = SubmissionStatus.APPROVED
                for li in invoice.line_items:
                    if li.status == LineItemStatus.VALIDATED:
                        li.status = LineItemStatus.APPROVED
            else:
                invoice.status = SubmissionStatus.PENDING_CARRIER_REVIEW

            audit.log_invoice_status_changed(
                db, invoice, from_status=old_inv_status, to_status=invoice.status
            )

    db.commit()

    # ── Supplier notification (non-blocking — never raises) ───────────────────
    notify_exception_resolved(db, invoice, line_item, exc, resolution_action)

    return {
        "message": f"Exception resolved: {resolution_action}",
        "invoice_status": invoice.status,
        "line_status": line_item.status,
    }


# ── Approve Invoice ───────────────────────────────────────────────────────────


@router.post("/invoices/{invoice_id}/approve")
def approve_invoice(
    invoice_id: uuid.UUID,
    payload: ApprovalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.CARRIER_ADMIN, UserRole.SYSTEM_ADMIN)
    ),
) -> dict:
    """
    Approve an invoice (or specific line items).
    Sets status to APPROVED.
    """
    invoice = _get_invoice(invoice_id, db, current_user)

    if invoice.status not in (
        SubmissionStatus.PENDING_CARRIER_REVIEW,
        SubmissionStatus.CARRIER_REVIEWING,
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot approve invoice in status '{invoice.status}'.",
        )

    # Approve specific lines or all lines
    line_ids = set(payload.line_item_ids) if payload.line_item_ids else None
    for li in invoice.line_items:
        if line_ids is None or li.id in line_ids:
            if li.status in (
                LineItemStatus.VALIDATED,
                LineItemStatus.OVERRIDE,
                LineItemStatus.RESOLVED,
            ):
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


# ── Bulk Approve ──────────────────────────────────────────────────────────────


@router.post("/invoices/bulk-approve")
def bulk_approve_invoices(
    payload: BulkApprovalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.CARRIER_ADMIN, UserRole.SYSTEM_ADMIN)
    ),
) -> dict:
    """
    Approve multiple invoices in a single request.

    Invoices not in PENDING_CARRIER_REVIEW or CARRIER_REVIEWING are silently
    skipped (they may have already been approved or are in an unresolvable state).
    Returns counts so the frontend can show a precise summary toast.
    """
    approved = 0
    skipped = 0
    approved_numbers: list[str] = []

    for invoice_id in payload.invoice_ids:
        invoice = db.get(Invoice, invoice_id)
        if invoice is None:
            skipped += 1
            continue

        # Carrier isolation check
        _bulk_contract = db.get(Contract, invoice.contract_id)
        if _bulk_contract is None or _bulk_contract.carrier_id != current_user.carrier_id:
            skipped += 1
            continue

        if invoice.status not in (
            SubmissionStatus.PENDING_CARRIER_REVIEW,
            SubmissionStatus.CARRIER_REVIEWING,
        ):
            skipped += 1
            continue

        # Advance all eligible line items to APPROVED
        for li in invoice.line_items:
            if li.status in (
                LineItemStatus.VALIDATED,
                LineItemStatus.OVERRIDE,
                LineItemStatus.RESOLVED,
            ):
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
        approved += 1
        approved_numbers.append(invoice.invoice_number)

    db.commit()

    return {
        "approved": approved,
        "skipped": skipped,
        "approved_invoice_numbers": approved_numbers,
    }


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
    invoice = _get_invoice(invoice_id, db, current_user)

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

    # ── Set invoice to EXPORTED (terminal) ────────────────────────────────────
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
    filename = f"approved_{invoice.invoice_number}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"

    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Suppliers ─────────────────────────────────────────────────────────────────


@router.get("/suppliers")
def list_suppliers(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
) -> list[dict]:
    """List suppliers that have at least one contract with the current carrier."""
    supplier_ids_subq = (
        db.query(Contract.supplier_id)
        .filter(Contract.carrier_id == current_user.carrier_id)
        .distinct()
        .subquery()
    )
    suppliers = (
        db.query(Supplier)
        .filter(Supplier.id.in_(supplier_ids_subq))
        .order_by(Supplier.name)
        .all()
    )
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "tax_id": s.tax_id,
            "is_active": s.is_active,
            "contract_count": len(s.contracts),
            "invoice_count": len(s.invoices),
            "user_count": sum(
                1 for u in s.users if u.role == UserRole.SUPPLIER and u.is_active
            ),
        }
        for s in suppliers
    ]


@router.post("/suppliers", status_code=201)
def create_supplier(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("CARRIER_ADMIN", "SYSTEM_ADMIN")),
) -> dict:
    """
    Create a new supplier.

    Body: { "name": str (required), "tax_id": str (optional) }
    Returns the created supplier with basic stats.
    """
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Supplier name is required.")

    existing = db.query(Supplier).filter(Supplier.name == name).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A supplier named '{name}' already exists.",
        )

    supplier = Supplier(
        name=name,
        tax_id=(payload.get("tax_id") or "").strip() or None,
        is_active=True,
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    return {
        "id": str(supplier.id),
        "name": supplier.name,
        "tax_id": supplier.tax_id,
        "is_active": supplier.is_active,
        "contract_count": 0,
        "invoice_count": 0,
    }


@router.get("/suppliers/{supplier_id}/users")
def list_supplier_users(
    supplier_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("CARRIER_ADMIN", "SYSTEM_ADMIN")),
) -> list[dict]:
    """List all user accounts linked to a supplier."""
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")

    users = (
        db.query(User)
        .filter(User.supplier_id == supplier_id, User.role == UserRole.SUPPLIER)
        .order_by(User.email)
        .all()
    )
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "is_active": u.is_active,
        }
        for u in users
    ]


@router.post("/suppliers/{supplier_id}/users", status_code=201)
def create_supplier_user(
    supplier_id: uuid.UUID,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("CARRIER_ADMIN", "SYSTEM_ADMIN")),
) -> dict:
    """
    Create a login account for a supplier.

    Body: { "email": str, "password": str }
    The user is created with role=SUPPLIER and linked to the given supplier.
    Returns 404 if supplier not found, 409 if email already exists.
    """
    from app.routers.auth import hash_password

    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")

    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    if not email:
        raise HTTPException(status_code=422, detail="Email is required.")
    if len(password) < 8:
        raise HTTPException(
            status_code=422, detail="Password must be at least 8 characters."
        )

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(
            status_code=409, detail=f"An account for '{email}' already exists."
        )

    user = User(
        email=email,
        hashed_password=hash_password(password),
        role=UserRole.SUPPLIER,
        supplier_id=supplier_id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "id": str(user.id),
        "email": user.email,
        "is_active": user.is_active,
    }


# ── Carrier Team (Users) ─────────────────────────────────────────────────────


@router.get("/users")
def list_carrier_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.CARRIER_ADMIN, UserRole.SYSTEM_ADMIN)
    ),
) -> list[dict]:
    """List all admin and reviewer accounts for the current carrier."""
    users = (
        db.query(User)
        .filter(
            User.carrier_id == current_user.carrier_id,
            User.role.in_([UserRole.CARRIER_ADMIN, UserRole.CARRIER_REVIEWER]),
        )
        .order_by(User.email)
        .all()
    )
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "category_scope": u.category_scope,
            "supplier_scope": u.supplier_scope,
        }
        for u in users
    ]


@router.post("/users", status_code=201)
def create_carrier_user(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.CARRIER_ADMIN, UserRole.SYSTEM_ADMIN)
    ),
) -> dict:
    """
    Create a login account for a carrier admin or reviewer.

    Body: { "email": str, "password": str, "role": "CARRIER_ADMIN" | "CARRIER_REVIEWER" }
    Returns 409 if email already exists.
    """
    from app.routers.auth import hash_password

    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    role = payload.get("role") or UserRole.CARRIER_REVIEWER

    if not email:
        raise HTTPException(status_code=422, detail="Email is required.")
    if len(password) < 8:
        raise HTTPException(
            status_code=422, detail="Password must be at least 8 characters."
        )
    if role not in (UserRole.CARRIER_ADMIN, UserRole.CARRIER_REVIEWER):
        raise HTTPException(
            status_code=422,
            detail="Role must be CARRIER_ADMIN or CARRIER_REVIEWER.",
        )

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(
            status_code=409, detail=f"An account for '{email}' already exists."
        )

    user = User(
        email=email,
        hashed_password=hash_password(password),
        role=role,
        carrier_id=current_user.carrier_id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "id": str(user.id),
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "category_scope": user.category_scope,
        "supplier_scope": user.supplier_scope,
    }


@router.patch("/users/{user_id}/scope", status_code=200)
def update_user_scope(
    user_id: uuid.UUID,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.CARRIER_ADMIN, UserRole.SYSTEM_ADMIN)
    ),
) -> dict:
    """
    Update the auditor scope for a carrier user.

    Body: {
      "category_scope": ["ENG", "LA"] | null,  // null clears → all domains
      "supplier_scope":  ["<uuid>", ...]  | null   // null clears → all suppliers
    }

    Only CARRIER_REVIEWER users need scopes set (admins see everything by default).
    Returns 404 if user not found; 403 if user belongs to a different carrier.
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.carrier_id != current_user.carrier_id:
        raise HTTPException(status_code=403, detail="Access denied")

    if "category_scope" in payload:
        cats = payload["category_scope"]
        user.category_scope = cats if cats else None
    if "supplier_scope" in payload:
        sups = payload["supplier_scope"]
        user.supplier_scope = sups if sups else None

    db.commit()
    db.refresh(user)

    return {
        "id": str(user.id),
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "category_scope": user.category_scope,
        "supplier_scope": user.supplier_scope,
    }


# ── Supplier Audit (AI) ───────────────────────────────────────────────────────


@router.post("/suppliers/{supplier_id}/audit")
def run_supplier_audit(
    supplier_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
) -> dict:
    """
    On-demand AI audit of a supplier's billing history.

    Aggregates invoice counts, exception patterns, and top-billed taxonomy codes,
    then calls Claude to produce a structured audit report with risk rating, findings,
    and actionable recommendations.

    No DB writes — result is returned directly to the caller.
    Returns 503 if ANTHROPIC_API_KEY is not configured.
    """
    from sqlalchemy import func

    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")

    # ── Invoice counts by status ───────────────────────────────────────────────
    invoice_summary_rows = (
        db.query(Invoice.status, func.count(Invoice.id).label("count"))
        .filter(Invoice.supplier_id == supplier_id)
        .group_by(Invoice.status)
        .all()
    )
    invoice_summary = [
        {"status": row.status, "count": row.count} for row in invoice_summary_rows
    ]

    # ── Exception patterns by taxonomy_code + required_action ─────────────────
    from app.models.validation import ExceptionRecord, ValidationResult as VR

    exception_summary_rows = (
        db.query(
            LineItem.taxonomy_code,
            VR.required_action,
            func.count(ExceptionRecord.id).label("count"),
        )
        .join(ExceptionRecord, ExceptionRecord.line_item_id == LineItem.id)
        .join(VR, VR.id == ExceptionRecord.validation_result_id)
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .filter(Invoice.supplier_id == supplier_id)
        .group_by(LineItem.taxonomy_code, VR.required_action)
        .order_by(func.count(ExceptionRecord.id).desc())
        .limit(20)
        .all()
    )
    exception_summary = [
        {
            "taxonomy_code": row.taxonomy_code,
            "required_action": row.required_action,
            "count": row.count,
        }
        for row in exception_summary_rows
    ]

    # ── Top taxonomy codes by total billed ────────────────────────────────────
    top_codes_rows = (
        db.query(
            LineItem.taxonomy_code,
            func.sum(LineItem.raw_amount).label("total_billed"),
            func.count(Invoice.id.distinct()).label("invoice_count"),
        )
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .filter(
            Invoice.supplier_id == supplier_id,
            LineItem.taxonomy_code.isnot(None),
        )
        .group_by(LineItem.taxonomy_code)
        .order_by(func.sum(LineItem.raw_amount).desc())
        .limit(10)
        .all()
    )
    top_codes = [
        {
            "taxonomy_code": row.taxonomy_code,
            "total_billed": float(row.total_billed or 0),
            "invoice_count": row.invoice_count,
        }
        for row in top_codes_rows
    ]

    result = audit_supplier(
        supplier_name=supplier.name,
        invoice_summary=invoice_summary,
        exception_summary=exception_summary,
        top_codes=top_codes,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI audit is not available — ANTHROPIC_API_KEY not configured.",
        )

    return result


# ── Contracts ─────────────────────────────────────────────────────────────────


@router.get("/contracts")
def list_contracts(
    supplier_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
) -> list[dict]:
    """
    List all contracts. Optionally filter by ?supplier_id=<uuid>.
    Returns contract details including rate card count.
    """
    q = db.query(Contract).filter(Contract.carrier_id == current_user.carrier_id)
    if supplier_id:
        q = q.filter(Contract.supplier_id == supplier_id)
    contracts = q.order_by(Contract.effective_from.desc()).all()
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "supplier_id": str(c.supplier_id),
            "supplier_name": c.supplier.name if c.supplier else None,
            "carrier_id": str(c.carrier_id),
            "effective_from": c.effective_from.isoformat(),
            "effective_to": c.effective_to.isoformat() if c.effective_to else None,
            "geography_scope": c.geography_scope,
            "is_active": c.is_active,
            "rate_card_count": len(c.rate_cards),
            "guideline_count": len(c.guidelines),
        }
        for c in contracts
    ]


# ── Contract Detail ───────────────────────────────────────────────────────────


@router.get("/contracts/{contract_id}", response_model=ContractDetail)
def get_contract_detail(
    contract_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
) -> ContractDetail:
    """Full contract detail including rate cards (with taxonomy labels) and guidelines."""
    contract = _get_contract(contract_id, db, current_user)
    return _to_contract_detail(contract, db)


# ── Contract Create ────────────────────────────────────────────────────────────


@router.post(
    "/contracts", response_model=ContractDetail, status_code=status.HTTP_201_CREATED
)
def create_contract(
    payload: ContractCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
) -> ContractDetail:
    """Create a new contract for the current carrier."""
    contract = Contract(
        supplier_id=payload.supplier_id,
        carrier_id=current_user.carrier_id,
        name=payload.name,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        geography_scope=payload.geography_scope,
        state_codes=payload.state_codes,
        notes=payload.notes,
        is_active=True,
    )
    db.add(contract)
    db.commit()
    db.refresh(contract)
    return _to_contract_detail(contract, db)


# ── AI PDF Parse (no DB write) ────────────────────────────────────────────────


@router.post("/contracts/parse-pdf")
async def parse_contract_pdf(
    file: UploadFile = File(...),
    supplier_id: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
) -> dict:
    """
    Upload a contract PDF for AI extraction.
    Returns a ParsedContractResult — does NOT write to DB.
    The client presents the result for review before calling create_contract.
    """
    from app.services.ai_assessment.contract_parser import parse_contract as _parse

    pdf_bytes = await file.read()
    return _parse(pdf_bytes, supplier_id, db)


# ── Rate Cards ────────────────────────────────────────────────────────────────


@router.post(
    "/contracts/{contract_id}/rate-cards",
    response_model=RateCardDetail,
    status_code=status.HTTP_201_CREATED,
)
def add_rate_card(
    contract_id: uuid.UUID,
    payload: RateCardCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
) -> RateCardDetail:
    """Add a rate card to an existing contract."""
    contract = _get_contract(contract_id, db, current_user)
    rc = RateCard(
        contract_id=contract.id,
        taxonomy_code=payload.taxonomy_code,
        contracted_rate=payload.contracted_rate,
        max_units=payload.max_units,
        is_all_inclusive=payload.is_all_inclusive,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
    )
    db.add(rc)
    db.commit()
    db.refresh(rc)
    return _to_rate_card_detail(rc, db)


@router.delete(
    "/contracts/{contract_id}/rate-cards/{rate_card_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_rate_card(
    contract_id: uuid.UUID,
    rate_card_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
) -> None:
    """Delete a rate card from a contract."""
    _get_contract(contract_id, db, current_user)  # 404/403 guard
    rc = db.get(RateCard, rate_card_id)
    if rc is None or rc.contract_id != contract_id:
        raise HTTPException(status_code=404, detail="Rate card not found")
    db.delete(rc)
    db.commit()


# ── Guidelines ────────────────────────────────────────────────────────────────


@router.post(
    "/contracts/{contract_id}/guidelines",
    response_model=GuidelineDetail,
    status_code=status.HTTP_201_CREATED,
)
def add_guideline(
    contract_id: uuid.UUID,
    payload: GuidelineCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
) -> GuidelineDetail:
    """Add a billing guideline to an existing contract."""
    contract = _get_contract(contract_id, db, current_user)
    g = Guideline(
        contract_id=contract.id,
        taxonomy_code=payload.taxonomy_code,
        domain=payload.domain,
        rule_type=payload.rule_type,
        rule_params=payload.rule_params,
        severity=payload.severity,
        narrative_source=payload.narrative_source,
        is_active=True,
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return _to_guideline_detail(g)


@router.put(
    "/contracts/{contract_id}/guidelines/{guideline_id}", response_model=GuidelineDetail
)
def update_guideline(
    contract_id: uuid.UUID,
    guideline_id: uuid.UUID,
    is_active: bool,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
) -> GuidelineDetail:
    """Toggle the is_active flag on a guideline."""
    _get_contract(contract_id, db, current_user)
    g = db.get(Guideline, guideline_id)
    if g is None or g.contract_id != contract_id:
        raise HTTPException(status_code=404, detail="Guideline not found")
    g.is_active = is_active
    db.commit()
    db.refresh(g)
    return _to_guideline_detail(g)


@router.delete(
    "/contracts/{contract_id}/guidelines/{guideline_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_guideline(
    contract_id: uuid.UUID,
    guideline_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
) -> None:
    """Delete a guideline from a contract."""
    _get_contract(contract_id, db, current_user)
    g = db.get(Guideline, guideline_id)
    if g is None or g.contract_id != contract_id:
        raise HTTPException(status_code=404, detail="Guideline not found")
    db.delete(g)
    db.commit()


# ── Test cleanup (staging only) ───────────────────────────────────────────────


@router.delete("/invoices/{invoice_id}", status_code=status.HTTP_200_OK)
def delete_invoice(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.SYSTEM_ADMIN)),
) -> dict:
    """
    Hard-delete an invoice and all related data (lines, validations, exceptions, audit events).
    SYSTEM_ADMIN only. Disabled in production — for test/demo cleanup.
    """
    if settings.is_production:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invoice deletion is not permitted in production.",
        )

    invoice = _get_invoice(invoice_id, db)
    invoice_number = invoice.invoice_number
    db.delete(invoice)
    db.commit()
    return {"message": f"Invoice '{invoice_number}' and all related data deleted."}


# ── Private helpers ───────────────────────────────────────────────────────────


def _get_contract(
    contract_id: uuid.UUID, db: Session, current_user: User | None = None
) -> Contract:
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    if current_user is not None and contract.carrier_id != current_user.carrier_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return contract


def _to_rate_card_detail(rc: RateCard, db: Session) -> RateCardDetail:
    item = db.get(TaxonomyItem, rc.taxonomy_code) if rc.taxonomy_code else None
    return RateCardDetail(
        id=rc.id,
        taxonomy_code=rc.taxonomy_code,
        taxonomy_label=item.label if item else None,
        contracted_rate=rc.contracted_rate,
        max_units=rc.max_units,
        is_all_inclusive=rc.is_all_inclusive,
        effective_from=rc.effective_from,
        effective_to=rc.effective_to,
    )


def _to_guideline_detail(g: Guideline) -> GuidelineDetail:
    return GuidelineDetail(
        id=g.id,
        taxonomy_code=g.taxonomy_code,
        domain=g.domain,
        rule_type=g.rule_type,
        rule_params=g.rule_params or {},
        severity=g.severity,
        narrative_source=g.narrative_source,
        is_active=g.is_active,
    )


def _to_contract_detail(c: Contract, db: Session) -> ContractDetail:
    return ContractDetail(
        id=c.id,
        name=c.name,
        supplier_id=c.supplier_id,
        supplier_name=c.supplier.name if c.supplier else None,
        carrier_id=c.carrier_id,
        effective_from=c.effective_from,
        effective_to=c.effective_to,
        geography_scope=c.geography_scope,
        state_codes=c.state_codes,
        notes=c.notes,
        is_active=c.is_active,
        rate_cards=[_to_rate_card_detail(rc, db) for rc in c.rate_cards],
        guidelines=[_to_guideline_detail(g) for g in c.guidelines],
    )


def _get_invoice(
    invoice_id: uuid.UUID, db: Session, current_user: User | None = None
) -> Invoice:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if current_user is not None:
        contract = db.get(Contract, invoice.contract_id)
        if contract is None or contract.carrier_id != current_user.carrier_id:
            raise HTTPException(status_code=403, detail="Access denied")
    return invoice


def _to_invoice_list_item(invoice: Invoice) -> InvoiceListItem:
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
        supplier_name=invoice.supplier.name if invoice.supplier else None,
        triage_risk_level=invoice.triage_risk_level,
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
            severity=exc.validation_result.severity
            if exc.validation_result
            else "ERROR",
            required_action=exc.validation_result.required_action
            if exc.validation_result
            else "NONE",
            supplier_response=exc.supplier_response,
            resolution_action=exc.resolution_action,
            ai_recommendation=exc.ai_recommendation,
            ai_reasoning=exc.ai_reasoning,
            ai_response_assessment=exc.ai_response_assessment,
            ai_response_reasoning=exc.ai_response_reasoning,
            ai_recommendation_accepted=exc.ai_recommendation_accepted,
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
        ai_description_assessment=li.ai_description_assessment,
        ai_classification_suggestion=li.ai_classification_suggestion,
    )
