"""
Carrier admin API routes.

Workflow:
  GET  /admin/invoices                          → queue of invoices pending review
  GET  /admin/invoices/{id}/lines               → line items with taxonomy detail
  POST /admin/invoices/{id}/approve             → approve invoice (or specific lines)
  POST /admin/invoices/bulk-approve             → approve multiple invoices at once
  DELETE /admin/invoices/{id}                   → delete invoice (staging only)
  POST /admin/seed-demo                         → enqueue synthetic data seed job
  GET  /admin/seed-demo/{job_id}                → poll seed job status
  POST /admin/mappings/override                 → override a line's taxonomy mapping
  POST /admin/mappings/batch-override           → batch override multiple lines at once
  GET  /admin/mappings/review-queue             → review low-confidence mapping queue (flat)
  GET  /admin/mappings/review-queue/grouped     → review queue grouped by supplier + taxonomy
  GET  /admin/mappings/insights                 → learning stats + pattern suggestions
  POST /admin/exceptions/{id}/resolve           → carrier resolves an exception
  GET  /admin/invoices/{id}/export              → export approved lines to CSV
  GET  /admin/suppliers                         → list all suppliers
  POST /admin/suppliers                         → create a new supplier
  GET  /admin/suppliers/{id}/users              → list user accounts for a supplier
  POST /admin/suppliers/{id}/users              → create a login for a supplier
  POST /admin/suppliers/{id}/audit              → AI audit report (on-demand, no DB write)
  GET  /admin/carriers/settings                 → get per-carrier processing settings
  PUT  /admin/carriers/settings                 → update per-carrier processing settings
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
from app.models.mapping import ConfirmedBy, MappingRule, MatchType
from app.models.supplier import (
    Carrier,
    Contract,
    DocumentType,
    Guideline,
    OnboardingStatus,
    RateCard,
    Supplier,
    SupplierDocument,
    User,
    UserRole,
)
from app.schemas.carrier_settings import CarrierSettings
from app.schemas.supplier import (
    SupplierDocumentResponse,
    SupplierProfileResponse,
    SupplierProfileUpdate,
    TaxonomyImportResult,
    TaxonomyImportRowResult,
)
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
    BatchOverrideRequest,
    BulkApprovalRequest,
    ExceptionSupplierView,
    InvoiceListItem,
    LineItemCarrierView,
    MappingOverrideRequest,
    ValidationResultSupplierView,
)
from app.services.ai_assessment.supplier_auditor import audit_supplier
from app.services.audit import logger as audit
from app.services.notifications.email import (
    notify_exception_resolved,
    notify_invoice_exported,
)
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
    from app.services.classification.mapping_learner import record_confirmed_mapping

    rule = None
    if payload.scope in ("this_supplier", "global"):
        rule = record_confirmed_mapping(
            db=db,
            line_item=line_item,
            taxonomy_code=payload.taxonomy_code,
            billing_component=payload.billing_component,
            source=ConfirmedBy.CARRIER_OVERRIDE,
            user_id=current_user.id,
            scope=payload.scope,
            notes=payload.notes,
        )
        if rule:
            audit.log_mapping_overridden(db, rule, old_taxonomy, current_user.id)
    rule_id = rule.id if rule else None

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


@router.get("/mappings/review-queue/grouped")
def get_grouped_review_queue(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
) -> list[dict]:
    """
    Returns the mapping review queue grouped by (supplier, AI-suggested taxonomy code).

    Groups with a confirmed AI suggestion appear first (ordered by item_count DESC),
    followed by unclassified groups that need manual triage.

    Each group contains the full list of line items so the frontend can render
    individual items without a second round-trip, plus up to 3 sample descriptions
    for at-a-glance review.
    """
    from sqlalchemy import or_

    q = (
        db.query(LineItem, Invoice.supplier_id, Supplier.name)
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .join(Supplier, Supplier.id == Invoice.supplier_id)
        .filter(
            Contract.carrier_id == current_user.carrier_id,
            (LineItem.mapping_confidence.in_(["LOW", "MEDIUM"]))
            | (LineItem.taxonomy_code.is_(None) & (LineItem.status == "EXCEPTION")),
        )
    )

    # Auditor scope filters (mirror flat queue)
    if current_user.category_scope:
        domain_filters = [
            LineItem.taxonomy_code.like(f"{domain}.%")
            for domain in current_user.category_scope
        ]
        q = q.filter(or_(*domain_filters, LineItem.taxonomy_code.is_(None)))
    if current_user.supplier_scope:
        q = q.filter(Invoice.supplier_id.in_(current_user.supplier_scope))

    rows = q.order_by(LineItem.created_at.desc()).limit(200).all()

    # Group in Python — key: (supplier_id_str, suggested_code or "__unclassified__")
    groups: dict[tuple, dict] = {}
    for li, supplier_id, supplier_name in rows:
        sug = li.ai_classification_suggestion or {}
        suggested_code = sug.get("suggested_code")
        suggested_billing = sug.get("suggested_billing_component")
        confidence = sug.get("confidence")
        key = (str(supplier_id), suggested_code or "__unclassified__")

        if key not in groups:
            groups[key] = {
                "supplier_id": str(supplier_id),
                "supplier_name": supplier_name,
                "suggested_taxonomy_code": suggested_code,
                "suggested_billing_component": suggested_billing,
                "confidence": confidence,
                "item_count": 0,
                "total_amount": 0.0,
                "sample_descriptions": [],
                "line_item_ids": [],
                "items": [],
            }
        g = groups[key]
        g["item_count"] += 1
        g["total_amount"] += float(li.raw_amount or 0)
        g["line_item_ids"].append(str(li.id))
        if (
            len(g["sample_descriptions"]) < 3
            and li.raw_description not in g["sample_descriptions"]
        ):
            g["sample_descriptions"].append(li.raw_description)
        g["items"].append(
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
        )

    result = list(groups.values())
    # Groups with an AI suggestion first (highest item count first), unclassified last
    result.sort(key=lambda g: (g["suggested_taxonomy_code"] is None, -g["item_count"]))
    for g in result:
        g["total_amount"] = str(round(g["total_amount"], 2))
    return result


@router.post("/mappings/batch-override", status_code=status.HTTP_200_OK)
def batch_override_mappings(
    payload: BatchOverrideRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.CARRIER_ADMIN, UserRole.SYSTEM_ADMIN)
    ),
) -> dict:
    """
    Apply the same taxonomy correction to multiple line items in one request.

    Intended for the grouped review queue: carrier confirms or overrides all
    items in a group without clicking through each one individually.

    MappingRule creation is deduplicated: if multiple lines share the same
    raw_description, only one rule is written (not one per line), preventing
    unnecessary version churn in the mapping corpus.

    Returns counts of updated lines, new rules created, and skipped items
    (not found or outside the carrier's scope).
    """
    from app.services.classification.mapping_learner import record_confirmed_mapping

    source = (
        ConfirmedBy.CARRIER_CONFIRMED
        if payload.is_confirm
        else ConfirmedBy.CARRIER_OVERRIDE
    )
    updated = 0
    skipped = 0
    rules_created = 0
    # Track (supplier_id_or_None, raw_description) pairs already written to avoid
    # creating multiple rule versions for lines with identical descriptions.
    seen_patterns: set[tuple] = set()

    for line_item_id in payload.line_item_ids:
        li = db.get(LineItem, line_item_id)
        if li is None:
            skipped += 1
            continue
        inv = db.get(Invoice, li.invoice_id)
        contract = db.get(Contract, inv.contract_id) if inv else None
        if contract is None or contract.carrier_id != current_user.carrier_id:
            skipped += 1
            continue

        old_taxonomy = li.taxonomy_code
        li.taxonomy_code = payload.taxonomy_code
        li.billing_component = payload.billing_component
        li.mapping_confidence = "HIGH"
        li.status = LineItemStatus.OVERRIDE
        updated += 1

        audit.log_event(
            db,
            "line_item",
            li.id,
            "line_item.mapping_overridden",
            payload={
                "old_taxonomy_code": old_taxonomy,
                "new_taxonomy_code": payload.taxonomy_code,
                "billing_component": payload.billing_component,
                "scope": payload.scope,
                "batch": True,
                "is_confirm": payload.is_confirm,
            },
            actor_type=ActorType.CARRIER,
            actor_id=current_user.id,
        )

        if payload.scope in ("this_supplier", "global"):
            supplier_id_for_key = (
                str(inv.supplier_id)
                if inv and payload.scope == "this_supplier"
                else None
            )
            pattern_key = (supplier_id_for_key, li.raw_description)
            if pattern_key not in seen_patterns:
                rule = record_confirmed_mapping(
                    db=db,
                    line_item=li,
                    taxonomy_code=payload.taxonomy_code,
                    billing_component=payload.billing_component,
                    source=source,
                    user_id=current_user.id,
                    scope=payload.scope,
                    notes=payload.notes,
                )
                if rule:
                    audit.log_mapping_overridden(
                        db, rule, old_taxonomy, current_user.id
                    )
                    rules_created += 1
                seen_patterns.add(pattern_key)

    db.commit()
    return {"updated": updated, "rules_created": rules_created, "skipped": skipped}


@router.get("/mappings/insights")
def get_mapping_insights(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
) -> dict:
    """
    Returns fast-query learning stats and pattern suggestions for the carrier.

    Stats:
      - queue_count:       Total items currently in the mapping review queue.
      - rules_learned_30d: MappingRules written in the last 30 days for this carrier's suppliers.

    Suggestions (up to 5):
      - Patterns where the same raw_description appears 3+ times in the current queue
        with a consistent AI-suggested taxonomy code but no active MappingRule yet.
      - One-click "Create Rule" in the UI calls batch-override for all matching line_item_ids.

    No AI calls — all pure SQL.
    """
    from sqlalchemy import func, or_
    from datetime import timedelta
    from app.models.mapping import MappingRule

    cutoff_30d = datetime.now(timezone.utc) - timedelta(days=30)

    # Queue count (same filter as flat queue, no scope restrictions for summary)
    queue_count = (
        db.query(func.count(LineItem.id))
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            Contract.carrier_id == current_user.carrier_id,
            (LineItem.mapping_confidence.in_(["LOW", "MEDIUM"]))
            | (LineItem.taxonomy_code.is_(None) & (LineItem.status == "EXCEPTION")),
        )
        .scalar()
        or 0
    )

    # Rules created in last 30 days — scoped to carrier's supplier IDs + global rules
    carrier_supplier_ids = [
        r[0]
        for r in db.query(Supplier.id)
        .join(Contract, Contract.supplier_id == Supplier.id)
        .filter(Contract.carrier_id == current_user.carrier_id)
        .all()
    ]
    rules_learned_30d = (
        db.query(func.count(MappingRule.id))
        .filter(
            MappingRule.confirmed_at >= cutoff_30d,
            or_(
                MappingRule.supplier_id.in_(carrier_supplier_ids),
                MappingRule.supplier_id.is_(None),
            ),
        )
        .scalar()
        or 0
    )

    # Suggestions: same (description, suggested_code) pair appearing 3+ times in queue
    rows = (
        db.query(LineItem, Invoice.supplier_id, Supplier.name)
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .join(Supplier, Supplier.id == Invoice.supplier_id)
        .filter(
            Contract.carrier_id == current_user.carrier_id,
            (LineItem.mapping_confidence.in_(["LOW", "MEDIUM"]))
            | (LineItem.taxonomy_code.is_(None) & (LineItem.status == "EXCEPTION")),
        )
        .limit(200)
        .all()
    )

    pattern_groups: dict[tuple, dict] = {}
    for li, supplier_id, supplier_name in rows:
        sug = li.ai_classification_suggestion or {}
        code = sug.get("suggested_code")
        billing = sug.get("suggested_billing_component") or ""
        if not code:
            continue
        key = (li.raw_description, code, billing, str(supplier_id))
        if key not in pattern_groups:
            pattern_groups[key] = {
                "count": 0,
                "line_item_ids": [],
                "supplier_name": supplier_name,
            }
        pattern_groups[key]["count"] += 1
        pattern_groups[key]["line_item_ids"].append(str(li.id))

    suggestions = [
        {
            "id": f"{key[1]}:{key[0][:40]}",
            "type": "create_rule",
            "message": f'"{key[0][:60]}" appears {v["count"]}× — save as a rule for {v["supplier_name"]}?',
            "taxonomy_code": key[1],
            "billing_component": key[2],
            "supplier_id": key[3],
            "supplier_name": v["supplier_name"],
            "line_item_ids": v["line_item_ids"],
            "count": v["count"],
        }
        for key, v in pattern_groups.items()
        if v["count"] >= 3
    ]
    suggestions.sort(key=lambda s: s["count"], reverse=True)

    return {
        "stats": {"queue_count": queue_count, "rules_learned_30d": rules_learned_30d},
        "suggestions": suggestions[:5],
    }


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
        if (
            _bulk_contract is None
            or _bulk_contract.carrier_id != current_user.carrier_id
        ):
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


# ── Accept AI Recommendations (bulk resolve) ──────────────────────────────────


@router.post("/invoices/{invoice_id}/accept-ai-recommendations", status_code=200)
def accept_ai_recommendations(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.CARRIER_ADMIN, UserRole.SYSTEM_ADMIN)
    ),
) -> dict:
    """
    Bulk-resolve all open billing exceptions using their ai_recommendation.

    For each open billing exception that has an ai_recommendation set:
    - Sets resolution_action = ai_recommendation
    - Sets ai_recommendation_accepted = True
    - Promotes the line to APPROVED (for accepting actions) or DENIED

    Exceptions without an ai_recommendation are skipped.
    Invoice auto-advances when all billing exceptions are resolved.
    """
    invoice = _get_invoice(invoice_id, db, current_user)
    if invoice.status not in (
        SubmissionStatus.REVIEW_REQUIRED,
        SubmissionStatus.PENDING_CARRIER_REVIEW,
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invoice is {invoice.status}. Only REVIEW_REQUIRED or "
                "PENDING_CARRIER_REVIEW invoices can be bulk-resolved."
            ),
        )

    _ACCEPTING = {
        ResolutionAction.WAIVED,
        ResolutionAction.HELD_CONTRACT_RATE,
        ResolutionAction.RECLASSIFIED,
        ResolutionAction.ACCEPTED_REDUCTION,
    }
    _ACTIVE_STATUSES = {
        ExceptionStatus.OPEN,
        ExceptionStatus.SUPPLIER_RESPONDED,
        ExceptionStatus.CARRIER_REVIEWING,
    }

    accepted = 0
    skipped = 0

    for li in invoice.line_items:
        for exc in li.exceptions:
            # Only open billing exceptions — skip classification queue items
            if exc.status not in _ACTIVE_STATUSES:
                continue
            if exc.validation_result.required_action == "REQUEST_RECLASSIFICATION":
                continue
            if exc.ai_recommendation is None:
                skipped += 1
                continue

            action = exc.ai_recommendation
            exc.resolution_action = action
            exc.resolution_notes = "Accepted AI recommendation"
            exc.resolved_at = datetime.now(timezone.utc)
            exc.resolved_by_user_id = current_user.id
            exc.ai_recommendation_accepted = True
            exc.status = ExceptionStatus.RESOLVED

            if action == ResolutionAction.DENIED:
                li.status = LineItemStatus.DENIED
            elif action in _ACCEPTING:
                # Promote line if no other active exceptions remain on it
                other_active = [
                    e
                    for e in li.exceptions
                    if e.id != exc.id and e.status in _ACTIVE_STATUSES
                ]
                if not other_active:
                    li.status = LineItemStatus.APPROVED

            accepted += 1

    db.flush()

    # Auto-advance invoice when all billing exceptions are resolved
    remaining_open = [
        e
        for li in invoice.line_items
        for e in li.exceptions
        if (
            e.status in _ACTIVE_STATUSES
            and e.validation_result.required_action != "REQUEST_RECLASSIFICATION"
        )
    ]
    if not remaining_open:
        old_status = invoice.status
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
            db,
            invoice,
            from_status=old_status,
            to_status=invoice.status,
        )

    db.commit()
    db.refresh(invoice)

    return {
        "accepted": accepted,
        "skipped": skipped,
        "invoice_status": invoice.status,
        "message": (
            f"Accepted {accepted} AI recommendation(s)."
            + (
                f" {skipped} exception(s) skipped (no AI recommendation)."
                if skipped
                else ""
            )
        ),
    }


# ── Export ────────────────────────────────────────────────────────────────────


@router.get("/invoices/{invoice_id}/file")
def download_original_invoice_file(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
) -> Response:
    """
    Stream the original uploaded invoice file (CSV or PDF) back to the caller.
    PDFs are served inline so the browser can open them in a new tab.
    CSVs are served as an attachment download.
    """
    from app.services.storage.base import get_storage

    invoice = _get_invoice(invoice_id, db, current_user)

    if not invoice.raw_file_path:
        raise HTTPException(
            status_code=404, detail="No original file found for this invoice."
        )

    storage = get_storage()
    if not storage.exists(invoice.raw_file_path):
        raise HTTPException(
            status_code=404, detail="Original file not found in storage."
        )

    file_bytes = storage.load(invoice.raw_file_path)
    fmt = (invoice.file_format or "").lower()

    if fmt == "pdf":
        media_type = "application/pdf"
        disposition = f'inline; filename="{invoice.invoice_number}.pdf"'
    else:
        media_type = "text/csv"
        disposition = f'attachment; filename="{invoice.invoice_number}_original.csv"'

    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={"Content-Disposition": disposition},
    )


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

    # Notify supplier users that payment has been exported (non-blocking)
    notify_invoice_exported(db, invoice)

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
            "onboarding_status": s.onboarding_status,
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
        is_active=False,
        onboarding_status=OnboardingStatus.DRAFT,
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    return {
        "id": str(supplier.id),
        "name": supplier.name,
        "tax_id": supplier.tax_id,
        "is_active": supplier.is_active,
        "onboarding_status": supplier.onboarding_status,
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


# ── Supplier Profile & Onboarding ─────────────────────────────────────────────


@router.get("/suppliers/{supplier_id}/profile", response_model=SupplierProfileResponse)
def get_supplier_profile(
    supplier_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
) -> SupplierProfileResponse:
    """
    Return full supplier profile including onboarding status and contact details.
    Scoped to the current carrier via Contract.
    """
    supplier = _get_supplier_for_carrier(supplier_id, db, current_user)
    return _to_supplier_profile_response(supplier, db)


@router.patch(
    "/suppliers/{supplier_id}/profile", response_model=SupplierProfileResponse
)
def update_supplier_profile(
    supplier_id: uuid.UUID,
    payload: SupplierProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.CARRIER_ADMIN, UserRole.SYSTEM_ADMIN)
    ),
) -> SupplierProfileResponse:
    """
    Update supplier profile fields. Partial update — only provided fields are changed.
    Does not change onboarding_status.
    """
    supplier = _get_supplier_for_carrier(supplier_id, db, current_user)

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(supplier, field, value)

    db.commit()
    db.refresh(supplier)
    return _to_supplier_profile_response(supplier, db)


@router.post("/suppliers/{supplier_id}/submit", status_code=200)
def submit_supplier_for_review(
    supplier_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.CARRIER_ADMIN, UserRole.SYSTEM_ADMIN)
    ),
) -> dict:
    """DRAFT → PENDING_REVIEW. Submit supplier profile for carrier review."""
    supplier = _get_supplier_for_carrier(supplier_id, db, current_user)
    _assert_onboarding_status(supplier, OnboardingStatus.DRAFT, "submit")
    supplier.onboarding_status = OnboardingStatus.PENDING_REVIEW
    supplier.submitted_at = datetime.now(timezone.utc)
    supplier.is_active = False
    db.commit()
    return {
        "message": f"Supplier '{supplier.name}' submitted for review.",
        "status": supplier.onboarding_status,
    }


@router.post("/suppliers/{supplier_id}/approve", status_code=200)
def approve_supplier(
    supplier_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.CARRIER_ADMIN, UserRole.SYSTEM_ADMIN)
    ),
) -> dict:
    """PENDING_REVIEW → ACTIVE. Approve the supplier; sets is_active=True."""
    supplier = _get_supplier_for_carrier(supplier_id, db, current_user)
    _assert_onboarding_status(supplier, OnboardingStatus.PENDING_REVIEW, "approve")
    supplier.onboarding_status = OnboardingStatus.ACTIVE
    supplier.is_active = True
    supplier.approved_at = datetime.now(timezone.utc)
    supplier.approved_by_id = current_user.id
    db.commit()
    return {
        "message": f"Supplier '{supplier.name}' approved.",
        "status": supplier.onboarding_status,
    }


@router.post("/suppliers/{supplier_id}/reject", status_code=200)
def reject_supplier(
    supplier_id: uuid.UUID,
    notes: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.CARRIER_ADMIN, UserRole.SYSTEM_ADMIN)
    ),
) -> dict:
    """PENDING_REVIEW → DRAFT. Send supplier back to draft with optional rejection notes."""
    supplier = _get_supplier_for_carrier(supplier_id, db, current_user)
    _assert_onboarding_status(supplier, OnboardingStatus.PENDING_REVIEW, "reject")
    supplier.onboarding_status = OnboardingStatus.DRAFT
    supplier.is_active = False
    if notes:
        supplier.notes = notes
    db.commit()
    return {
        "message": f"Supplier '{supplier.name}' sent back to DRAFT.",
        "status": supplier.onboarding_status,
    }


@router.post("/suppliers/{supplier_id}/suspend", status_code=200)
def suspend_supplier(
    supplier_id: uuid.UUID,
    notes: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.CARRIER_ADMIN, UserRole.SYSTEM_ADMIN)
    ),
) -> dict:
    """ACTIVE → SUSPENDED. Suspend supplier; sets is_active=False."""
    supplier = _get_supplier_for_carrier(supplier_id, db, current_user)
    _assert_onboarding_status(supplier, OnboardingStatus.ACTIVE, "suspend")
    supplier.onboarding_status = OnboardingStatus.SUSPENDED
    supplier.is_active = False
    if notes:
        supplier.notes = notes
    db.commit()
    return {
        "message": f"Supplier '{supplier.name}' suspended.",
        "status": supplier.onboarding_status,
    }


@router.post("/suppliers/{supplier_id}/reinstate", status_code=200)
def reinstate_supplier(
    supplier_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.CARRIER_ADMIN, UserRole.SYSTEM_ADMIN)
    ),
) -> dict:
    """SUSPENDED → ACTIVE. Reinstate suspended supplier."""
    supplier = _get_supplier_for_carrier(supplier_id, db, current_user)
    _assert_onboarding_status(supplier, OnboardingStatus.SUSPENDED, "reinstate")
    supplier.onboarding_status = OnboardingStatus.ACTIVE
    supplier.is_active = True
    supplier.approved_at = datetime.now(timezone.utc)
    supplier.approved_by_id = current_user.id
    db.commit()
    return {
        "message": f"Supplier '{supplier.name}' reinstated.",
        "status": supplier.onboarding_status,
    }


# ── Supplier Documents ────────────────────────────────────────────────────────


@router.get(
    "/suppliers/{supplier_id}/documents",
    response_model=list[SupplierDocumentResponse],
)
def list_supplier_documents(
    supplier_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
) -> list[SupplierDocumentResponse]:
    """List all compliance documents for a supplier."""
    _get_supplier_for_carrier(supplier_id, db, current_user)
    docs = (
        db.query(SupplierDocument)
        .filter(SupplierDocument.supplier_id == supplier_id)
        .order_by(SupplierDocument.uploaded_at.desc())
        .all()
    )
    return docs


@router.post(
    "/suppliers/{supplier_id}/documents",
    response_model=SupplierDocumentResponse,
    status_code=201,
)
async def upload_supplier_document(
    supplier_id: uuid.UUID,
    document_type: str = Form(...),
    expires_at: str | None = Form(default=None),
    notes: str | None = Form(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.CARRIER_ADMIN, UserRole.SYSTEM_ADMIN)
    ),
) -> SupplierDocumentResponse:
    """
    Upload a compliance document for a supplier.
    Accepted document_type values: W9 | COI | MSA | OTHER
    Storage path: supplier_docs/{supplier_id}/{document_type}/{filename}
    """
    from app.services.storage.base import get_storage

    _get_supplier_for_carrier(supplier_id, db, current_user)

    valid_doc_types = {
        DocumentType.W9,
        DocumentType.COI,
        DocumentType.MSA,
        DocumentType.OTHER,
    }
    doc_type_upper = (document_type or "").upper()
    if doc_type_upper not in valid_doc_types:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid document_type. Must be one of: {sorted(valid_doc_types)}",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")

    storage = get_storage()
    subfolder = f"supplier_docs/{supplier_id}/{doc_type_upper}"
    storage_path = storage.save(
        data=file_bytes,
        filename=file.filename,
        subfolder=subfolder,
    )

    expires_date = None
    if expires_at:
        try:
            expires_date = date_type.fromisoformat(expires_at)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail="expires_at must be a valid ISO date (YYYY-MM-DD).",
            )

    doc = SupplierDocument(
        supplier_id=supplier_id,
        document_type=doc_type_upper,
        filename=file.filename,
        storage_path=storage_path,
        file_size_bytes=len(file_bytes),
        uploaded_by_id=current_user.id,
        uploaded_at=datetime.now(timezone.utc),
        expires_at=expires_date,
        notes=notes or None,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


# ── Bulk Taxonomy Import ───────────────────────────────────────────────────────


@router.post(
    "/suppliers/{supplier_id}/taxonomy-import",
    response_model=TaxonomyImportResult,
    status_code=200,
)
async def bulk_taxonomy_import(
    supplier_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.CARRIER_ADMIN, UserRole.SYSTEM_ADMIN)
    ),
) -> TaxonomyImportResult:
    """
    Upload a CSV of supplier billing codes for AI taxonomy matching.

    CSV format (with header row):
        supplier_code,description

    Processing:
    - Each row is sent to Claude (claude-haiku-4-5) with the full active taxonomy list.
    - Creates MappingRule entries (match_type=KEYWORD_SET, confirmed_by=SYSTEM).
    - Skips rows where an active rule already exists for this supplier + description.
    - Max 200 rows per import.

    Returns: { processed, mapped, skipped, unmapped, results: [...] }
    """
    from app.services.ai_assessment.taxonomy_mapper import (
        match_supplier_code,
        confidence_to_weight,
    )

    _get_supplier_for_carrier(supplier_id, db, current_user)

    # ── Parse CSV ──────────────────────────────────────────────────────────────
    raw_bytes = await file.read()
    try:
        content = raw_bytes.decode("utf-8-sig")  # handles BOM from Excel exports
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="File must be UTF-8 encoded.")

    reader = csv.DictReader(io.StringIO(content))
    fieldnames = set(reader.fieldnames or [])
    if not {"supplier_code", "description"}.issubset(fieldnames):
        raise HTTPException(
            status_code=422,
            detail="CSV must have columns: supplier_code, description",
        )

    rows = list(reader)
    if len(rows) > 200:
        raise HTTPException(
            status_code=422,
            detail=f"CSV exceeds 200-row limit ({len(rows)} rows). Split into multiple uploads.",
        )

    # ── Pre-fetch all active taxonomy items (avoid N+1 on every AI call) ──────
    taxonomy_items = [
        {
            "code": t.code,
            "label": t.label,
            "domain": t.domain,
            "description": t.description or "",
        }
        for t in db.query(TaxonomyItem).filter(TaxonomyItem.is_active.is_(True)).all()
    ]

    # ── Pre-fetch existing active KEYWORD_SET rules for this supplier ─────────
    existing_patterns = {
        r.match_pattern
        for r in db.query(MappingRule)
        .filter(
            MappingRule.supplier_id == supplier_id,
            MappingRule.match_type == MatchType.KEYWORD_SET,
            MappingRule.effective_to.is_(None),
        )
        .all()
    }

    # ── Process rows ──────────────────────────────────────────────────────────
    now = datetime.now(timezone.utc)
    results: list[TaxonomyImportRowResult] = []
    processed = 0
    mapped = 0
    skipped = 0
    unmapped = 0

    for row_idx, row in enumerate(rows, start=2):  # row 1 = header
        supplier_code = (row.get("supplier_code") or "").strip()
        description = (row.get("description") or "").strip()
        processed += 1

        if not supplier_code or not description:
            results.append(
                TaxonomyImportRowResult(
                    row=row_idx,
                    supplier_code=supplier_code,
                    description=description,
                    matched_taxonomy_code=None,
                    confidence=None,
                    skipped=False,
                    error="supplier_code and description are both required",
                )
            )
            unmapped += 1
            continue

        # Skip if an active KEYWORD_SET rule already covers this description
        if description in existing_patterns:
            results.append(
                TaxonomyImportRowResult(
                    row=row_idx,
                    supplier_code=supplier_code,
                    description=description,
                    matched_taxonomy_code=None,
                    confidence=None,
                    skipped=True,
                    error=None,
                )
            )
            skipped += 1
            continue

        # AI match
        match = match_supplier_code(supplier_code, description, taxonomy_items)

        if match is None or match.get("taxonomy_code") is None:
            error_msg = (
                "No AI match found" if match is not None else "AI service unavailable"
            )
            results.append(
                TaxonomyImportRowResult(
                    row=row_idx,
                    supplier_code=supplier_code,
                    description=description,
                    matched_taxonomy_code=None,
                    confidence=None,
                    skipped=False,
                    error=error_msg,
                )
            )
            unmapped += 1
            continue

        taxonomy_code = match["taxonomy_code"]
        confidence = match["confidence"]

        # Derive billing_component from the last segment of the taxonomy code
        billing_component = taxonomy_code.rsplit(".", 1)[-1] if taxonomy_code else ""

        rule = MappingRule(
            supplier_id=supplier_id,
            match_type=MatchType.KEYWORD_SET,
            match_pattern=description,
            taxonomy_code=taxonomy_code,
            billing_component=billing_component,
            confidence_weight=confidence_to_weight(confidence),
            confidence_label=confidence or "LOW",
            confirmed_by=ConfirmedBy.SYSTEM,
            confirmed_by_user_id=None,
            confirmed_at=now,
            effective_from=now,
            version=1,
        )
        db.add(rule)
        existing_patterns.add(description)  # prevent same-import duplicates

        results.append(
            TaxonomyImportRowResult(
                row=row_idx,
                supplier_code=supplier_code,
                description=description,
                matched_taxonomy_code=taxonomy_code,
                confidence=confidence,
                skipped=False,
                error=None,
            )
        )
        mapped += 1

    db.commit()

    return TaxonomyImportResult(
        processed=processed,
        mapped=mapped,
        skipped=skipped,
        unmapped=unmapped,
        results=results,
    )


# ── Verticals ─────────────────────────────────────────────────────────────────


@router.get("/verticals")
def list_verticals(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
) -> list[dict]:
    """
    List all active line-of-business verticals.
    Used to populate the vertical dropdown on the contract creation form.
    """
    from app.models.taxonomy import Vertical

    rows = (
        db.query(Vertical)
        .filter(Vertical.is_active.is_(True))
        .order_by(Vertical.name)
        .all()
    )
    return [{"id": str(v.id), "slug": v.slug, "name": v.name} for v in rows]


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
            "vertical_id": str(c.vertical_id) if c.vertical_id else None,
            "vertical_slug": c.vertical.slug if c.vertical else None,
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
        vertical_id=payload.vertical_id,
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

    # ── Validate taxonomy code exists in the registry ─────────────────────────
    # The DB FK would catch this as an IntegrityError, but we want a clear 422
    # with an actionable message rather than a raw constraint violation.
    tax_item = db.get(TaxonomyItem, payload.taxonomy_code)
    if tax_item is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown taxonomy code '{payload.taxonomy_code}'. "
                "Add it to app/taxonomy/constants.py and frontend/lib/taxonomy.ts, "
                "then redeploy to register it before creating a rate card."
            ),
        )
    if not tax_item.is_active:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Taxonomy code '{payload.taxonomy_code}' ({tax_item.label}) is inactive "
                "and cannot be used on new rate cards. "
                "Re-activate it in the taxonomy registry first."
            ),
        )

    rc = RateCard(
        contract_id=contract.id,
        taxonomy_code=payload.taxonomy_code,
        rate_type=payload.rate_type,
        contracted_rate=payload.contracted_rate,
        rate_tiers=[t.model_dump() for t in payload.rate_tiers]
        if payload.rate_tiers
        else None,
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

    # ── Validate taxonomy code if provided (domain-wide guidelines use None) ──
    if payload.taxonomy_code is not None:
        tax_item = db.get(TaxonomyItem, payload.taxonomy_code)
        if tax_item is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Unknown taxonomy code '{payload.taxonomy_code}'. "
                    "Add it to app/taxonomy/constants.py and redeploy to register it first."
                ),
            )
        if not tax_item.is_active:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Taxonomy code '{payload.taxonomy_code}' ({tax_item.label}) is inactive. "
                    "Re-activate it before creating guidelines that reference it."
                ),
            )

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


# ── Seed Demo ─────────────────────────────────────────────────────────────────


@router.post("/seed-demo")
def trigger_seed_demo(
    clean: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CARRIER_ADMIN)),
) -> dict:
    """
    Enqueue the synthetic data seeder as a background RQ job.

    Generates 6 suppliers, 12 contracts, 120 invoices, and ~640 line items
    across all 11 P&C ALAE taxonomy domains using Claude (haiku).

    Args:
        clean: If true, deletes all existing SEED-* data before generating.

    Returns job_id for polling via GET /admin/seed-demo/{job_id}.

    CARRIER_ADMIN only. Blocked in production.
    """
    if settings.is_production:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seed demo is not permitted in production environments.",
        )
    from app.workers.queue import enqueue_seed_demo

    job_id = enqueue_seed_demo(
        carrier_id=str(current_user.carrier_id),
        clean=clean,
    )
    return {"job_id": job_id, "status": "queued"}


@router.get("/seed-demo/{job_id}")
def get_seed_demo_status(
    job_id: str,
    current_user: User = Depends(require_role(UserRole.CARRIER_ADMIN)),
) -> dict:
    """
    Poll the status of a seed demo background job.

    Returns status: queued | started | finished | failed
    When finished, includes a result summary with counts.
    """
    from rq.job import Job, NoSuchJobError
    from app.workers.queue import get_redis

    try:
        job = Job.fetch(job_id, connection=get_redis())
        raw_status = job.get_status()
        # rq ≥ 1.16 returns a JobStatus enum; older returns a string
        status_str = (
            raw_status.value if hasattr(raw_status, "value") else str(raw_status)
        )
        payload: dict = {"job_id": job_id, "status": status_str}
        if status_str == "finished":
            payload["result"] = job.result
        elif status_str == "failed":
            payload["error"] = str(job.exc_info) if job.exc_info else "Unknown error"
        return payload
    except NoSuchJobError:
        raise HTTPException(status_code=404, detail="Seed job not found")


# ── Queue / Dead-Letter Queue management ──────────────────────────────────────


@router.get("/queue/failed")
def list_failed_jobs(
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
) -> list[dict]:
    """
    Return all jobs currently in the dead-letter queue (FailedJobRegistry).

    Includes failed invoice processing jobs across all three priority queues
    (high / default / low). Each entry includes the invoice_id, the error
    summary, and the number of retries already attempted.

    Carrier roles only.
    """
    from app.workers.queue import get_failed_jobs

    return get_failed_jobs(limit=100)


@router.post("/queue/failed/{job_id}/retry", status_code=200)
def retry_failed_job_endpoint(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
) -> dict:
    """
    Re-enqueue a failed job from the dead-letter queue.

    The job is re-created on the same priority queue with a fresh retry budget.
    The corresponding Invoice row's job_id is updated to the new job ID so
    subsequent DLQ lookups stay consistent.

    Returns the new job ID and 'requeued' status.
    """
    from datetime import datetime, timezone

    from app.models.invoice import Invoice
    from app.workers.queue import retry_failed_job

    try:
        new_job_id = retry_failed_job(job_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Could not retry job '{job_id}': {exc}",
        )

    # Update the invoice's job_id so DLQ tracking stays in sync
    invoice = db.query(Invoice).filter(Invoice.job_id == job_id).first()
    if invoice:
        invoice.job_id = new_job_id
        invoice.job_queued_at = datetime.now(timezone.utc)
        db.commit()

    return {"job_id": new_job_id, "previous_job_id": job_id, "status": "requeued"}


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


# ── Carrier Settings ──────────────────────────────────────────────────────────


@router.get("/carriers/settings", response_model=CarrierSettings)
def get_carrier_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CARRIER_ADMIN)),
) -> CarrierSettings:
    """
    Return the current per-carrier pipeline and processing settings.

    Omitted / null fields in the response inherit the platform default.
    CARRIER_ADMIN only.
    """
    carrier = db.get(Carrier, current_user.carrier_id)
    if carrier is None:
        raise HTTPException(status_code=404, detail="Carrier not found")
    return CarrierSettings.model_validate(carrier.settings or {})


@router.put("/carriers/settings", response_model=CarrierSettings)
def update_carrier_settings(
    payload: CarrierSettings,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CARRIER_ADMIN)),
) -> CarrierSettings:
    """
    Update per-carrier pipeline and processing settings.

    Performs a full replace of the settings object — send all fields you want
    to preserve, not just the changed ones.  To reset a field to the platform
    default, set it to null.

    CARRIER_ADMIN only.
    """
    carrier = db.get(Carrier, current_user.carrier_id)
    if carrier is None:
        raise HTTPException(status_code=404, detail="Carrier not found")
    carrier.settings = payload.model_dump(exclude_none=False)
    db.commit()
    db.refresh(carrier)
    return CarrierSettings.model_validate(carrier.settings or {})


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
        rate_type=rc.rate_type,
        contracted_rate=rc.contracted_rate,
        rate_tiers=rc.rate_tiers,  # JSONB list[dict] → Pydantic coerces to list[RateTier]
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
        vertical_id=c.vertical_id,
        vertical_slug=c.vertical.slug if c.vertical else None,
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
    # Count only *spend* exceptions (exclude REQUEST_RECLASSIFICATION which are
    # classification issues handled in the mapping queue, not in this list).
    # This keeps the list count consistent with the "Spend Exceptions" breakdown
    # shown on the invoice detail page.
    exc_count = sum(
        1
        for li in invoice.line_items
        if any(
            exc.status == ExceptionStatus.OPEN
            and exc.validation_result.required_action != "REQUEST_RECLASSIFICATION"
            for exc in li.exceptions
        )
    )
    # Count open billing exceptions that already have an AI recommendation set.
    # Used by the queue to show "AI Ready" vs "needs triage" indicators.
    ai_recs_ready = sum(
        1
        for li in invoice.line_items
        for exc in li.exceptions
        if (
            exc.status == ExceptionStatus.OPEN
            and exc.validation_result.required_action != "REQUEST_RECLASSIFICATION"
            and exc.ai_recommendation is not None
        )
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
        ai_recommendations_ready=ai_recs_ready,
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
            validation_type=exc.validation_result.validation_type
            if exc.validation_result
            else "RATE",
            supplier_response=exc.supplier_response,
            resolution_action=exc.resolution_action,
            resolution_notes=exc.resolution_notes,
            ai_recommendation=exc.ai_recommendation,
            ai_reasoning=exc.ai_reasoning,
            ai_response_assessment=exc.ai_response_assessment,
            ai_response_reasoning=exc.ai_response_reasoning,
            ai_recommendation_accepted=exc.ai_recommendation_accepted,
            created_at=exc.created_at,
            resolved_at=exc.resolved_at,
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


# ── Supplier helper functions ─────────────────────────────────────────────────


def _get_supplier_for_carrier(
    supplier_id: uuid.UUID,
    db: Session,
    current_user: User,
) -> Supplier:
    """
    Load a supplier and verify it belongs to the current carrier.

    Raises:
        404 if supplier not found
        403 if supplier has no contract with current_user's carrier
    """
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")

    # Multi-tenant guard: supplier must have at least one contract with this carrier
    contract_exists = (
        db.query(Contract)
        .filter(
            Contract.supplier_id == supplier_id,
            Contract.carrier_id == current_user.carrier_id,
        )
        .first()
    )
    if contract_exists is None:
        raise HTTPException(status_code=403, detail="Access denied")

    return supplier


def _assert_onboarding_status(
    supplier: Supplier, required_status: str, action: str
) -> None:
    """Raise 409 Conflict if supplier is not in the required onboarding status."""
    if supplier.onboarding_status != required_status:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot {action} supplier in status '{supplier.onboarding_status}'. "
                f"Required: '{required_status}'."
            ),
        )


def _to_supplier_profile_response(
    supplier: Supplier, db: Session
) -> SupplierProfileResponse:
    """Build a SupplierProfileResponse with computed count fields."""
    return SupplierProfileResponse(
        id=supplier.id,
        name=supplier.name,
        tax_id=supplier.tax_id,
        onboarding_status=supplier.onboarding_status,
        is_active=supplier.is_active,
        primary_contact_name=supplier.primary_contact_name,
        primary_contact_email=supplier.primary_contact_email,
        primary_contact_phone=supplier.primary_contact_phone,
        address_line1=supplier.address_line1,
        address_line2=supplier.address_line2,
        city=supplier.city,
        state_code=supplier.state_code,
        zip_code=supplier.zip_code,
        website=supplier.website,
        notes=supplier.notes,
        submitted_at=supplier.submitted_at,
        approved_at=supplier.approved_at,
        approved_by_id=supplier.approved_by_id,
        contract_count=len(supplier.contracts),
        invoice_count=len(supplier.invoices),
        user_count=sum(
            1 for u in supplier.users if u.role == UserRole.SUPPLIER and u.is_active
        ),
    )
