"""
Analytics API routes for carrier admins.

Provides aggregated spend and billing operations metrics.  All endpoints accept
optional filter query params (date_from, date_to, supplier_id, domain) so the
frontend global filter bar cascades across every section.

  GET /admin/analytics/summary                        → KPI scalars (billed, approved, savings, exceptions)
  GET /admin/analytics/spend-by-domain                → spend grouped by service domain (IA, ENG, CR, etc.)
  GET /admin/analytics/spend-by-supplier              → spend grouped by supplier
  GET /admin/analytics/spend-by-taxonomy              → spend grouped by taxonomy code (+ units, avg rate)
  GET /admin/analytics/exception-breakdown            → exception counts by validation type
  GET /admin/analytics/rate-gaps                      → services billed with no contracted rate card
  GET /admin/analytics/supplier-comparison            → side-by-side spend per supplier × taxonomy code
                                                         ?format=csv returns a downloadable CSV file
  GET /admin/analytics/spend-trend                    → monthly spend trend (last 18 months)
  GET /admin/analytics/contract-health                → per-contract rate card coverage + expiry alerts
  GET /admin/analytics/supplier-scorecard/{id}        → per-supplier performance KPIs
  GET /admin/analytics/savings-realization            → identified vs recovered savings + recovery rate
  GET /admin/analytics/utilization                    → units/frequency analysis per taxonomy × supplier
  GET /admin/analytics/claim-stacking                 → same-claim multi-vendor or repeat service billing
  GET /admin/analytics/rate-benchmarks                → intra-panel avg rate comparison per taxonomy code
"""

import csv
import io
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func, text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.invoice import Invoice, LineItem
from app.models.supplier import Contract, RateCard, Supplier, User, UserRole
from app.models.taxonomy import TaxonomyItem
from app.models.validation import (
    ExceptionRecord,
    ExceptionStatus,
    RequiredAction,
    ValidationResult,
)
from app.routers.auth import require_role

router = APIRouter(prefix="/admin/analytics", tags=["analytics"])

_CARRIER_ROLES = (
    UserRole.CARRIER_ADMIN,
    UserRole.CARRIER_REVIEWER,
    UserRole.SYSTEM_ADMIN,
)


# ── Filter helpers ─────────────────────────────────────────────────────────────


def _apply_standard_filters(
    q,
    date_from: Optional[date],
    date_to: Optional[date],
    supplier_id: Optional[str],
    domain: Optional[str],
):
    """
    Apply the four standard analytics filter params to any query that already
    joins Invoice, Contract, and LineItem (for the domain split_part).
    """
    if date_from:
        q = q.filter(Invoice.invoice_date >= date_from)
    if date_to:
        q = q.filter(Invoice.invoice_date <= date_to)
    if supplier_id:
        q = q.filter(Invoice.supplier_id == supplier_id)
    if domain:
        q = q.filter(func.split_part(LineItem.taxonomy_code, ".", 1) == domain)
    return q


# ── Summary ───────────────────────────────────────────────────────────────────


@router.get("/summary")
def get_analytics_summary(
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    supplier_id: Optional[str] = Query(default=None),
    domain: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Returns five KPI scalars + invoice status breakdown for the header cards
    and the status distribution chart.
    """
    carrier_filter = Contract.carrier_id == current_user.carrier_id

    # ── helper that adds the optional filters to any sub-query ────────────────
    def _f(q):
        return _apply_standard_filters(q, date_from, date_to, supplier_id, domain)

    # Total billed: sum raw_amount across all non-draft/non-processing invoices
    total_billed = _f(
        db.query(func.sum(LineItem.raw_amount))
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            carrier_filter,
            Invoice.status.notin_(["DRAFT", "PROCESSING"]),
        )
    ).scalar() or Decimal(0)

    # Total approved: expected_amount on finalized invoices, excluding denied lines
    total_approved = _f(
        db.query(func.sum(LineItem.expected_amount))
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            carrier_filter,
            Invoice.status.in_(["APPROVED", "EXPORTED"]),
            LineItem.status != "DENIED",
            LineItem.expected_amount.isnot(None),
        )
    ).scalar() or Decimal(0)

    # Identified savings: lines where billed exceeded contract rate (approved < billed)
    total_savings = _f(
        db.query(func.sum(LineItem.raw_amount - LineItem.expected_amount))
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            carrier_filter,
            Invoice.status.in_(["APPROVED", "EXPORTED"]),
            LineItem.expected_amount.isnot(None),
            LineItem.raw_amount > LineItem.expected_amount,
        )
    ).scalar() or Decimal(0)

    # Invoice counts by status — scoped to this carrier
    status_q = (
        db.query(Invoice.status, func.count(Invoice.id))
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(carrier_filter)
    )
    if date_from:
        status_q = status_q.filter(Invoice.invoice_date >= date_from)
    if date_to:
        status_q = status_q.filter(Invoice.invoice_date <= date_to)
    if supplier_id:
        status_q = status_q.filter(Invoice.supplier_id == supplier_id)
    status_rows = status_q.group_by(Invoice.status).all()

    # Open exception count (OPEN only) — scoped to this carrier
    exc_base = (
        db.query(func.count(ExceptionRecord.id))
        .join(LineItem, LineItem.id == ExceptionRecord.line_item_id)
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(carrier_filter)
    )
    if date_from:
        exc_base = exc_base.filter(Invoice.invoice_date >= date_from)
    if date_to:
        exc_base = exc_base.filter(Invoice.invoice_date <= date_to)
    if supplier_id:
        exc_base = exc_base.filter(Invoice.supplier_id == supplier_id)

    open_exceptions = (
        exc_base.filter(ExceptionRecord.status == ExceptionStatus.OPEN).scalar() or 0
    )
    total_exceptions = exc_base.scalar() or 0

    # Identified savings (ALL statuses, not just approved) — needed for recovery_rate
    identified_savings = _f(
        db.query(func.sum(LineItem.raw_amount - LineItem.expected_amount))
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .join(ExceptionRecord, ExceptionRecord.line_item_id == LineItem.id)
        .filter(
            carrier_filter,
            LineItem.expected_amount.isnot(None),
            LineItem.raw_amount > LineItem.expected_amount,
        )
    ).scalar() or Decimal(0)
    recovery_rate = (
        round(float(total_savings) / float(identified_savings), 4)
        if identified_savings > 0
        else 0.0
    )

    # Auto-classification rate: HIGH-confidence classified lines / all classified lines
    def _line_base(extra_filters: list) -> int:
        return (
            _f(
                db.query(func.count(LineItem.id))
                .join(Invoice, Invoice.id == LineItem.invoice_id)
                .join(Contract, Contract.id == Invoice.contract_id)
                .filter(
                    carrier_filter, LineItem.taxonomy_code.isnot(None), *extra_filters
                )
            ).scalar()
            or 0
        )

    total_classified = _line_base([])
    auto_classified = _line_base([LineItem.mapping_confidence == "HIGH"])
    auto_classification_rate = (
        round(auto_classified / total_classified, 4) if total_classified > 0 else 0.0
    )

    return {
        "total_billed": str(total_billed),
        "total_approved": str(total_approved),
        "total_savings": str(total_savings),
        "open_exceptions": open_exceptions,
        "total_exceptions": total_exceptions,
        "invoice_status_counts": [
            {"status": row[0], "count": row[1]} for row in status_rows
        ],
        "recovery_rate": recovery_rate,
        "auto_classification_rate": auto_classification_rate,
    }


# ── Spend by Domain ───────────────────────────────────────────────────────────


@router.get("/spend-by-domain")
def get_spend_by_domain(
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    supplier_id: Optional[str] = Query(default=None),
    domain: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Groups classified line items by the first segment of their taxonomy code
    (the service domain: IA, ENG, REC, LA, INSP, VIRT, CR, INV, DRNE, APPR, XDOMAIN).
    Only classified lines are included.
    """
    domain_expr = func.split_part(LineItem.taxonomy_code, ".", 1).label("domain")

    q = (
        db.query(
            domain_expr,
            func.count(LineItem.id).label("line_count"),
            func.sum(LineItem.raw_amount).label("total_billed"),
            func.coalesce(func.sum(LineItem.expected_amount), 0).label(
                "total_approved"
            ),
        )
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            Contract.carrier_id == current_user.carrier_id,
            LineItem.taxonomy_code.isnot(None),
        )
    )
    q = _apply_standard_filters(q, date_from, date_to, supplier_id, domain)

    rows = q.group_by(domain_expr).order_by(func.sum(LineItem.raw_amount).desc()).all()

    return [
        {
            "domain": row.domain,
            "line_count": row.line_count,
            "total_billed": str(row.total_billed),
            "total_approved": str(row.total_approved),
        }
        for row in rows
    ]


# ── Spend by Supplier ─────────────────────────────────────────────────────────


@router.get("/spend-by-supplier")
def get_spend_by_supplier(
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    supplier_id: Optional[str] = Query(default=None),
    domain: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Supplier-level spend rollup for RFP benchmarking.
    Excludes DRAFT and PROCESSING invoices (not yet actionable).
    """
    q = (
        db.query(
            Supplier.id,
            Supplier.name,
            func.count(func.distinct(Invoice.id)).label("invoice_count"),
            func.sum(LineItem.raw_amount).label("total_billed"),
            func.coalesce(func.sum(LineItem.expected_amount), 0).label(
                "total_approved"
            ),
        )
        .join(Invoice, Invoice.supplier_id == Supplier.id)
        .join(LineItem, LineItem.invoice_id == Invoice.id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            Contract.carrier_id == current_user.carrier_id,
            Invoice.status.notin_(["DRAFT", "PROCESSING"]),
        )
    )
    q = _apply_standard_filters(q, date_from, date_to, supplier_id, domain)

    rows = (
        q.group_by(Supplier.id, Supplier.name)
        .order_by(func.sum(LineItem.raw_amount).desc())
        .all()
    )

    return [
        {
            "supplier_id": str(row.id),
            "supplier_name": row.name,
            "invoice_count": row.invoice_count,
            "total_billed": str(row.total_billed),
            "total_approved": str(row.total_approved),
        }
        for row in rows
    ]


# ── Spend by Taxonomy ─────────────────────────────────────────────────────────


@router.get("/spend-by-taxonomy")
def get_spend_by_taxonomy(
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    supplier_id: Optional[str] = Query(default=None),
    domain: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Full taxonomy code breakdown — the data foundation for the spend intelligence table.
    Joins to TaxonomyItem for label and domain; left-join to handle any orphaned codes.
    Includes total_quantity (sum of raw_quantity) and avg_billed_rate for sourcing intel.
    """
    q = (
        db.query(
            LineItem.taxonomy_code,
            TaxonomyItem.label,
            TaxonomyItem.domain,
            func.count(LineItem.id).label("line_count"),
            func.sum(LineItem.raw_amount).label("total_billed"),
            func.coalesce(func.sum(LineItem.expected_amount), 0).label(
                "total_approved"
            ),
            func.sum(LineItem.raw_quantity).label("total_quantity"),
        )
        .join(TaxonomyItem, LineItem.taxonomy_code == TaxonomyItem.code, isouter=True)
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            Contract.carrier_id == current_user.carrier_id,
            LineItem.taxonomy_code.isnot(None),
        )
    )
    q = _apply_standard_filters(q, date_from, date_to, supplier_id, domain)

    rows = (
        q.group_by(LineItem.taxonomy_code, TaxonomyItem.label, TaxonomyItem.domain)
        .order_by(func.sum(LineItem.raw_amount).desc())
        .all()
    )

    def _avg_rate(total_billed, total_quantity) -> str | None:
        billed = Decimal(str(total_billed or 0))
        qty = Decimal(str(total_quantity or 0))
        if qty == 0:
            return None
        return str(round(billed / qty, 2))

    return [
        {
            "taxonomy_code": row.taxonomy_code,
            "label": row.label,
            "domain": row.domain,
            "line_count": row.line_count,
            "total_billed": str(row.total_billed),
            "total_approved": str(row.total_approved),
            "total_quantity": str(row.total_quantity or 0),
            "avg_billed_rate": _avg_rate(row.total_billed, row.total_quantity),
        }
        for row in rows
    ]


# ── Exception Breakdown ───────────────────────────────────────────────────────


@router.get("/exception-breakdown")
def get_exception_breakdown(
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    supplier_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Groups exceptions by their source validation type (RATE / GUIDELINE / CLASSIFICATION)
    to show where billing issues originate.
    """
    q = (
        db.query(
            ValidationResult.validation_type,
            func.count(ExceptionRecord.id).label("count"),
        )
        .join(
            ExceptionRecord,
            ExceptionRecord.validation_result_id == ValidationResult.id,
        )
        .join(LineItem, LineItem.id == ExceptionRecord.line_item_id)
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(Contract.carrier_id == current_user.carrier_id)
    )
    if date_from:
        q = q.filter(Invoice.invoice_date >= date_from)
    if date_to:
        q = q.filter(Invoice.invoice_date <= date_to)
    if supplier_id:
        q = q.filter(Invoice.supplier_id == supplier_id)

    rows = (
        q.group_by(ValidationResult.validation_type)
        .order_by(func.count(ExceptionRecord.id).desc())
        .all()
    )

    return [
        {"validation_type": row.validation_type, "count": row.count} for row in rows
    ]


# ── Rate Card Gaps ─────────────────────────────────────────────────────────────


@router.get("/rate-gaps")
def get_rate_gaps(
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    supplier_id: Optional[str] = Query(default=None),
    domain: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Returns services being billed with no contracted rate card.

    Finds ValidationResult rows where required_action=ESTABLISH_CONTRACT_RATE,
    joins to LineItem → Invoice → Contract → Supplier, and groups by taxonomy_code + supplier.
    Ordered by total billed descending so the highest-exposure gaps are first.
    """
    q = (
        db.query(
            LineItem.taxonomy_code,
            TaxonomyItem.label.label("taxonomy_label"),
            Supplier.id.label("supplier_id"),
            Supplier.name.label("supplier_name"),
            func.count(ValidationResult.id.distinct()).label("open_count"),
            func.sum(LineItem.raw_amount).label("total_billed"),
        )
        .join(ValidationResult, ValidationResult.line_item_id == LineItem.id)
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .join(Supplier, Supplier.id == Invoice.supplier_id)
        .outerjoin(TaxonomyItem, TaxonomyItem.code == LineItem.taxonomy_code)
        .filter(
            Contract.carrier_id == current_user.carrier_id,
            ValidationResult.required_action == RequiredAction.ESTABLISH_CONTRACT_RATE,
        )
    )
    q = _apply_standard_filters(q, date_from, date_to, supplier_id, domain)

    rows = (
        q.group_by(
            LineItem.taxonomy_code,
            TaxonomyItem.label,
            Supplier.id,
            Supplier.name,
        )
        .order_by(func.sum(LineItem.raw_amount).desc())
        .all()
    )

    return [
        {
            "taxonomy_code": row.taxonomy_code,
            "taxonomy_label": row.taxonomy_label,
            "supplier_id": str(row.supplier_id),
            "supplier_name": row.supplier_name,
            "open_count": row.open_count,
            "total_billed": str(row.total_billed or 0),
        }
        for row in rows
    ]


# ── Supplier Comparison ───────────────────────────────────────────────────────


@router.get("/supplier-comparison")
def get_supplier_comparison(
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    supplier_id: Optional[str] = Query(default=None),
    domain: Optional[str] = Query(default=None),
    format: str = Query(default="json", pattern="^(json|csv)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Side-by-side spend analysis per supplier × taxonomy code.
    ?format=csv returns a downloadable CSV file instead of JSON.
    """
    q = (
        db.query(
            LineItem.taxonomy_code,
            TaxonomyItem.label.label("taxonomy_label"),
            Supplier.id.label("supplier_id"),
            Supplier.name.label("supplier_name"),
            func.count(LineItem.id.distinct()).label("invoice_count"),
            func.sum(LineItem.raw_amount).label("total_billed"),
            func.sum(LineItem.expected_amount).label("total_expected"),
            func.count(ExceptionRecord.id.distinct()).label("exception_count"),
        )
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .join(Supplier, Supplier.id == Invoice.supplier_id)
        .outerjoin(TaxonomyItem, TaxonomyItem.code == LineItem.taxonomy_code)
        .outerjoin(ExceptionRecord, ExceptionRecord.line_item_id == LineItem.id)
        .filter(
            Contract.carrier_id == current_user.carrier_id,
            LineItem.taxonomy_code.isnot(None),
        )
    )
    q = _apply_standard_filters(q, date_from, date_to, supplier_id, domain)

    rows = (
        q.group_by(
            LineItem.taxonomy_code,
            TaxonomyItem.label,
            Supplier.id,
            Supplier.name,
        )
        .order_by(Supplier.name, LineItem.taxonomy_code)
        .all()
    )

    def _savings(billed, expected) -> Decimal:
        b = Decimal(str(billed or 0))
        e = Decimal(str(expected or 0))
        diff = b - e
        return diff if diff > 0 else Decimal("0")

    def _exception_rate(exception_count, invoice_count) -> str:
        if not invoice_count:
            return "0.0"
        return f"{round(exception_count / invoice_count * 100, 1)}"

    records = [
        {
            "taxonomy_code": row.taxonomy_code,
            "taxonomy_label": row.taxonomy_label,
            "supplier_id": str(row.supplier_id),
            "supplier_name": row.supplier_name,
            "invoice_count": row.invoice_count,
            "total_billed": str(row.total_billed or 0),
            "total_expected": str(row.total_expected or 0),
            "total_savings": str(_savings(row.total_billed, row.total_expected)),
            "exception_rate": _exception_rate(row.exception_count, row.invoice_count),
        }
        for row in rows
    ]

    if format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "supplier_name",
                "taxonomy_code",
                "taxonomy_label",
                "invoice_count",
                "total_billed",
                "total_expected",
                "total_savings",
                "exception_rate",
            ],
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(records)
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=supplier-comparison.csv"
            },
        )

    return records


# ── AI Accuracy ────────────────────────────────────────────────────────────────


@router.get("/ai-accuracy")
def get_ai_accuracy(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
):
    """
    AI recommendation accuracy stats.

    For every exception where the exception_resolver made a recommendation,
    returns overall acceptance rate and a per-action breakdown showing which
    actions the AI gets right most often.

    Only counts exceptions that have been resolved (ai_recommendation_accepted
    IS NOT NULL) for the rate calculation — unresolved exceptions are counted
    in the "pending" total but excluded from rates so the metric stays honest.
    """
    rows = (
        db.query(
            ExceptionRecord.ai_recommendation,
            func.count(ExceptionRecord.id).label("total"),
            func.sum(
                case(
                    (ExceptionRecord.ai_recommendation_accepted.isnot(None), 1), else_=0
                )
            ).label("resolved"),
            func.sum(
                case((ExceptionRecord.ai_recommendation_accepted == True, 1), else_=0)  # noqa: E712
            ).label("accepted"),
        )
        .join(LineItem, LineItem.id == ExceptionRecord.line_item_id)
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            Contract.carrier_id == current_user.carrier_id,
            ExceptionRecord.ai_recommendation.isnot(None),
        )
        .group_by(ExceptionRecord.ai_recommendation)
        .order_by(func.count(ExceptionRecord.id).desc())
        .all()
    )

    # Aggregate totals across all actions
    total_with_rec = sum(r.total for r in rows)
    total_resolved = sum(r.resolved for r in rows)
    total_accepted = sum(r.accepted for r in rows)
    overall_rate = round(total_accepted / total_resolved, 4) if total_resolved else None

    by_action = [
        {
            "action": r.ai_recommendation,
            "recommended": r.total,
            "resolved": r.resolved,
            "accepted": r.accepted,
            "acceptance_rate": round(r.accepted / r.resolved, 4)
            if r.resolved
            else None,
        }
        for r in rows
    ]

    return {
        "total_with_recommendation": total_with_rec,
        "total_resolved": total_resolved,
        "total_accepted": total_accepted,
        "acceptance_rate": overall_rate,
        "by_recommended_action": by_action,
    }


# ── Geographic spend ───────────────────────────────────────────────────────────


@router.get("/spend-by-state")
def get_spend_by_state(
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    supplier_id: Optional[str] = Query(default=None),
    domain: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Spend aggregated by US state (service_state on LineItem).
    Only lines that have a service_state value are included.
    Used to drive the geographic choropleth map.
    """
    q = (
        db.query(
            LineItem.service_state,
            func.count(LineItem.id).label("line_count"),
            func.sum(LineItem.raw_amount).label("total_billed"),
            func.sum(
                func.coalesce(LineItem.expected_amount, LineItem.raw_amount)
            ).label("total_approved"),
        )
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            Contract.carrier_id == current_user.carrier_id,
            LineItem.service_state.isnot(None),
            LineItem.service_state != "",
        )
    )
    q = _apply_standard_filters(q, date_from, date_to, supplier_id, domain)

    rows = (
        q.group_by(LineItem.service_state)
        .order_by(func.sum(LineItem.raw_amount).desc())
        .all()
    )
    return [
        {
            "state": row.service_state.upper(),
            "line_count": row.line_count,
            "total_billed": str(row.total_billed or 0),
            "total_approved": str(row.total_approved or 0),
        }
        for row in rows
    ]


@router.get("/spend-by-zip")
def get_spend_by_zip(
    state: str | None = Query(
        default=None, description="Filter to a single state code, e.g. CA"
    ),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    supplier_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Spend aggregated by ZIP code (top 50 by billed amount).
    Optionally filtered to a single state for drill-down.
    """
    q = (
        db.query(
            LineItem.service_zip,
            LineItem.service_state,
            func.count(LineItem.id).label("line_count"),
            func.sum(LineItem.raw_amount).label("total_billed"),
        )
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            Contract.carrier_id == current_user.carrier_id,
            LineItem.service_zip.isnot(None),
            LineItem.service_zip != "",
        )
    )
    if state:
        q = q.filter(LineItem.service_state == state.upper())
    if date_from:
        q = q.filter(Invoice.invoice_date >= date_from)
    if date_to:
        q = q.filter(Invoice.invoice_date <= date_to)
    if supplier_id:
        q = q.filter(Invoice.supplier_id == supplier_id)

    rows = (
        q.group_by(LineItem.service_zip, LineItem.service_state)
        .order_by(func.sum(LineItem.raw_amount).desc())
        .limit(50)
        .all()
    )
    return [
        {
            "zip": row.service_zip,
            "state": row.service_state,
            "line_count": row.line_count,
            "total_billed": str(row.total_billed or 0),
        }
        for row in rows
    ]


# ── Spend Trend ────────────────────────────────────────────────────────────────


@router.get("/spend-trend")
def get_spend_trend(
    period: str = Query(default="month", pattern="^(month|week)$"),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    supplier_id: Optional[str] = Query(default=None),
    domain: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Monthly (or weekly) spend trend — last 18 months by default, or within the
    date_from/date_to window if supplied.

    Groups all non-draft invoices by the truncated invoice_date period, returns
    total_billed, total_approved (on approved/exported invoices), and invoice count.
    Ordered oldest → newest for charting left-to-right.
    """
    trunc_expr = func.date_trunc(period, Invoice.invoice_date).label("period")

    q = (
        db.query(
            trunc_expr,
            func.count(Invoice.id.distinct()).label("invoice_count"),
            func.sum(LineItem.raw_amount).label("total_billed"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            Invoice.status.in_(["APPROVED", "EXPORTED"]),
                            LineItem.expected_amount,
                        ),
                        else_=None,
                    )
                ),
                0,
            ).label("total_approved"),
        )
        .join(LineItem, LineItem.invoice_id == Invoice.id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            Contract.carrier_id == current_user.carrier_id,
            Invoice.status.notin_(["DRAFT", "PROCESSING"]),
        )
    )

    # If no date_from supplied, default to last 18 months
    if not date_from:
        q = q.filter(
            Invoice.invoice_date
            >= func.date_trunc(
                period,
                func.cast(
                    func.now() - text("INTERVAL '18 months'"), Invoice.invoice_date.type
                ),
            )
        )

    q = _apply_standard_filters(q, date_from, date_to, supplier_id, domain)

    rows = q.group_by(trunc_expr).order_by(trunc_expr).all()

    return [
        {
            "period": row.period.strftime("%Y-%m")
            if hasattr(row.period, "strftime")
            else str(row.period)[:7],
            "invoice_count": row.invoice_count,
            "total_billed": str(row.total_billed or 0),
            "total_approved": str(row.total_approved or 0),
        }
        for row in rows
    ]


# ── Contract Health ────────────────────────────────────────────────────────────


@router.get("/contract-health")
def get_contract_health(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Per-contract health summary for the contract renewal dashboard.

    For each active contract, returns:
      - rate_card_count  — number of rate cards on file
      - invoice_count    — total invoices processed under the contract
      - exception_count  — total exceptions raised
      - exception_rate   — exception_count / invoice_count (0 if no invoices)
      - expiry_status    — ACTIVE | EXPIRING_SOON (≤60 days) | EXPIRED
      - days_to_expiry   — positive = days remaining; negative = days past expiry; null = no end date
    """
    today = date.today()

    # One row per contract with invoice and exception counts
    rows = (
        db.query(
            Contract.id,
            Contract.name,
            Contract.effective_from,
            Contract.effective_to,
            Contract.is_active,
            Supplier.name.label("supplier_name"),
            func.count(func.distinct(Invoice.id)).label("invoice_count"),
            func.count(func.distinct(ExceptionRecord.id)).label("exception_count"),
        )
        .join(Supplier, Supplier.id == Contract.supplier_id)
        .outerjoin(Invoice, Invoice.contract_id == Contract.id)
        .outerjoin(LineItem, LineItem.invoice_id == Invoice.id)
        .outerjoin(ExceptionRecord, ExceptionRecord.line_item_id == LineItem.id)
        .filter(Contract.carrier_id == current_user.carrier_id)
        .group_by(
            Contract.id,
            Contract.name,
            Contract.effective_from,
            Contract.effective_to,
            Contract.is_active,
            Supplier.name,
        )
        .order_by(Contract.effective_to.asc().nullslast(), Contract.name)
        .all()
    )

    # Rate card counts per contract (separate query — avoids fan-out)
    rc_counts = dict(
        db.query(RateCard.contract_id, func.count(RateCard.id))
        .filter(RateCard.contract_id.in_([r.id for r in rows]))
        .group_by(RateCard.contract_id)
        .all()
    )

    def _expiry(effective_to):
        if effective_to is None:
            return "ACTIVE", None
        delta = (effective_to - today).days
        if delta < 0:
            return "EXPIRED", delta
        if delta <= 60:
            return "EXPIRING_SOON", delta
        return "ACTIVE", delta

    result = []
    for row in rows:
        status, days = _expiry(row.effective_to)
        inv_count = row.invoice_count or 0
        exc_count = row.exception_count or 0
        exc_rate = round(exc_count / inv_count, 4) if inv_count else 0.0
        result.append(
            {
                "contract_id": str(row.id),
                "contract_name": row.name,
                "supplier_name": row.supplier_name,
                "effective_from": str(row.effective_from),
                "effective_to": str(row.effective_to) if row.effective_to else None,
                "is_active": row.is_active,
                "rate_card_count": rc_counts.get(row.id, 0),
                "invoice_count": inv_count,
                "exception_count": exc_count,
                "exception_rate": exc_rate,
                "expiry_status": status,
                "days_to_expiry": days,
            }
        )
    return result


# ── Supplier Scorecard ─────────────────────────────────────────────────────────


@router.get("/supplier-scorecard/{supplier_id}")
def get_supplier_scorecard(
    supplier_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Per-supplier performance scorecard for QBR and vendor management.
    """
    # Verify supplier belongs to this carrier (via at least one contract)
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    # Check carrier scope
    contract_exists = (
        db.query(Contract.id)
        .filter(
            Contract.supplier_id == supplier_id,
            Contract.carrier_id == current_user.carrier_id,
        )
        .first()
    )
    if not contract_exists and current_user.role != UserRole.SYSTEM_ADMIN:
        raise HTTPException(status_code=403, detail="Not authorised for this supplier")

    # Invoice status counts
    status_rows = (
        db.query(Invoice.status, func.count(Invoice.id))
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            Invoice.supplier_id == supplier_id,
            Contract.carrier_id == current_user.carrier_id,
        )
        .group_by(Invoice.status)
        .all()
    )
    invoice_status_counts = {row[0]: row[1] for row in status_rows}
    total_invoices = sum(invoice_status_counts.values())

    # Total billed + savings
    financials = (
        db.query(
            func.sum(LineItem.raw_amount).label("total_billed"),
            func.coalesce(func.sum(LineItem.expected_amount), 0).label(
                "total_expected"
            ),
        )
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            Invoice.supplier_id == supplier_id,
            Contract.carrier_id == current_user.carrier_id,
            Invoice.status.notin_(["DRAFT", "PROCESSING"]),
        )
        .first()
    )
    total_billed = Decimal(str(financials.total_billed or 0))
    total_expected = Decimal(str(financials.total_expected or 0))
    total_savings = max(total_billed - total_expected, Decimal(0))

    # Exception count
    total_exceptions = (
        db.query(func.count(ExceptionRecord.id))
        .join(LineItem, LineItem.id == ExceptionRecord.line_item_id)
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            Invoice.supplier_id == supplier_id,
            Contract.carrier_id == current_user.carrier_id,
        )
        .scalar()
        or 0
    )
    exception_rate = (
        round(total_exceptions / total_invoices, 4) if total_invoices else 0.0
    )

    # Auto-approval rate: invoices with status APPROVED and zero exceptions
    invoices_with_exceptions = (
        db.query(func.count(func.distinct(Invoice.id)))
        .join(LineItem, LineItem.invoice_id == Invoice.id)
        .join(ExceptionRecord, ExceptionRecord.line_item_id == LineItem.id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            Invoice.supplier_id == supplier_id,
            Contract.carrier_id == current_user.carrier_id,
        )
        .scalar()
        or 0
    )
    approved_count = invoice_status_counts.get(
        "APPROVED", 0
    ) + invoice_status_counts.get("EXPORTED", 0)
    clean_approved = max(approved_count - invoices_with_exceptions, 0)
    auto_approval_rate = (
        round(clean_approved / total_invoices, 4) if total_invoices else 0.0
    )

    # Top 5 taxonomy codes by billed amount
    top_codes = (
        db.query(
            LineItem.taxonomy_code,
            TaxonomyItem.label,
            func.sum(LineItem.raw_amount).label("total_billed"),
            func.count(LineItem.id).label("line_count"),
        )
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .outerjoin(TaxonomyItem, TaxonomyItem.code == LineItem.taxonomy_code)
        .filter(
            Invoice.supplier_id == supplier_id,
            Contract.carrier_id == current_user.carrier_id,
            LineItem.taxonomy_code.isnot(None),
        )
        .group_by(LineItem.taxonomy_code, TaxonomyItem.label)
        .order_by(func.sum(LineItem.raw_amount).desc())
        .limit(5)
        .all()
    )

    # Top exception types
    top_exceptions = (
        db.query(
            ValidationResult.validation_type,
            func.count(ExceptionRecord.id).label("count"),
        )
        .join(
            ExceptionRecord, ExceptionRecord.validation_result_id == ValidationResult.id
        )
        .join(LineItem, LineItem.id == ExceptionRecord.line_item_id)
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            Invoice.supplier_id == supplier_id,
            Contract.carrier_id == current_user.carrier_id,
        )
        .group_by(ValidationResult.validation_type)
        .order_by(func.count(ExceptionRecord.id).desc())
        .limit(3)
        .all()
    )

    return {
        "supplier_id": str(supplier.id),
        "supplier_name": supplier.name,
        "total_invoices": total_invoices,
        "invoice_status_counts": invoice_status_counts,
        "total_billed": str(total_billed),
        "total_expected": str(total_expected),
        "total_savings": str(total_savings),
        "total_exceptions": total_exceptions,
        "exception_rate": exception_rate,
        "auto_approval_rate": auto_approval_rate,
        "top_taxonomy_codes": [
            {
                "taxonomy_code": r.taxonomy_code,
                "label": r.label,
                "total_billed": str(r.total_billed or 0),
                "line_count": r.line_count,
            }
            for r in top_codes
        ],
        "top_exception_types": [
            {"validation_type": r.validation_type, "count": r.count}
            for r in top_exceptions
        ],
    }


# ── Savings Realization ────────────────────────────────────────────────────────


@router.get("/savings-realization")
def get_savings_realization(
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    supplier_id: Optional[str] = Query(default=None),
    domain: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Identified vs recovered savings split — the ROI story for the tool.

    Identified savings: all line items with an ExceptionRecord where raw_amount
    exceeds expected_amount, regardless of invoice status (includes in-review,
    disputed, etc.).

    Recovered savings: the same population but restricted to APPROVED/EXPORTED
    invoices — savings that were actually applied to the final approved amount.

    Recovery rate = recovered / identified.
    """
    carrier_filter = Contract.carrier_id == current_user.carrier_id

    def _f(q):
        return _apply_standard_filters(q, date_from, date_to, supplier_id, domain)

    # Identified savings — exceptions raised on lines where billed > expected
    identified_savings = _f(
        db.query(func.sum(LineItem.raw_amount - LineItem.expected_amount))
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .join(ExceptionRecord, ExceptionRecord.line_item_id == LineItem.id)
        .filter(
            carrier_filter,
            LineItem.expected_amount.isnot(None),
            LineItem.raw_amount > LineItem.expected_amount,
        )
    ).scalar() or Decimal(0)

    # Recovered savings — same but only on finalized invoices
    recovered_savings = _f(
        db.query(func.sum(LineItem.raw_amount - LineItem.expected_amount))
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .join(ExceptionRecord, ExceptionRecord.line_item_id == LineItem.id)
        .filter(
            carrier_filter,
            LineItem.expected_amount.isnot(None),
            LineItem.raw_amount > LineItem.expected_amount,
            Invoice.status.in_(["APPROVED", "EXPORTED"]),
        )
    ).scalar() or Decimal(0)

    pending_savings = max(identified_savings - recovered_savings, Decimal(0))

    # Invoices with at least one recovered exception
    invoices_with_recovery = (
        _f(
            db.query(func.count(func.distinct(Invoice.id)))
            .join(LineItem, LineItem.invoice_id == Invoice.id)
            .join(Contract, Contract.id == Invoice.contract_id)
            .join(ExceptionRecord, ExceptionRecord.line_item_id == LineItem.id)
            .filter(
                carrier_filter,
                Invoice.status.in_(["APPROVED", "EXPORTED"]),
                LineItem.expected_amount.isnot(None),
                LineItem.raw_amount > LineItem.expected_amount,
            )
        ).scalar()
        or 0
    )

    # Total invoices with any exception
    total_with_exceptions = (
        _f(
            db.query(func.count(func.distinct(Invoice.id)))
            .join(LineItem, LineItem.invoice_id == Invoice.id)
            .join(Contract, Contract.id == Invoice.contract_id)
            .join(ExceptionRecord, ExceptionRecord.line_item_id == LineItem.id)
            .filter(carrier_filter)
        ).scalar()
        or 0
    )

    recovery_rate = (
        round(float(recovered_savings) / float(identified_savings), 4)
        if identified_savings > 0
        else 0.0
    )

    return {
        "identified_savings": str(identified_savings),
        "recovered_savings": str(recovered_savings),
        "pending_savings": str(pending_savings),
        "recovery_rate": recovery_rate,
        "invoices_with_recovery": invoices_with_recovery,
        "total_invoices_with_exceptions": total_with_exceptions,
    }


# ── Utilization / Frequency ────────────────────────────────────────────────────


@router.get("/utilization")
def get_utilization(
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    supplier_id: Optional[str] = Query(default=None),
    domain: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Units/frequency analysis per taxonomy code × supplier.

    Uses a two-level aggregation:
      1. Inner subquery: total units billed per (taxonomy_code, supplier, invoice)
      2. Outer query: avg/sum across invoices for that (taxonomy_code, supplier) pair

    Also fetches RateCard.max_units to compute a cap utilization percentage,
    flagging codes where average billing approaches the contracted cap.
    """
    # Inner: per (taxonomy_code, supplier_id, invoice_id) total units
    inner_q = (
        db.query(
            LineItem.taxonomy_code,
            Invoice.supplier_id,
            Invoice.id.label("invoice_id"),
            func.sum(LineItem.raw_quantity).label("invoice_units"),
        )
        .join(Invoice, LineItem.invoice_id == Invoice.id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            Contract.carrier_id == current_user.carrier_id,
            LineItem.taxonomy_code.isnot(None),
            Invoice.status.notin_(["DRAFT", "PROCESSING"]),
        )
    )
    inner_q = _apply_standard_filters(inner_q, date_from, date_to, supplier_id, domain)
    inner = inner_q.group_by(
        LineItem.taxonomy_code, Invoice.supplier_id, Invoice.id
    ).subquery()

    # Outer: aggregate per (taxonomy_code, supplier_id)
    rows = (
        db.query(
            inner.c.taxonomy_code,
            inner.c.supplier_id,
            Supplier.name.label("supplier_name"),
            TaxonomyItem.label.label("taxonomy_label"),
            TaxonomyItem.domain,
            func.count(inner.c.invoice_id).label("total_invoices"),
            func.sum(inner.c.invoice_units).label("total_units"),
            func.avg(inner.c.invoice_units).label("avg_units_per_invoice"),
            func.max(inner.c.invoice_units).label("max_single_invoice"),
        )
        .join(Supplier, Supplier.id == inner.c.supplier_id)
        .outerjoin(TaxonomyItem, TaxonomyItem.code == inner.c.taxonomy_code)
        .group_by(
            inner.c.taxonomy_code,
            inner.c.supplier_id,
            Supplier.name,
            TaxonomyItem.label,
            TaxonomyItem.domain,
        )
        .order_by(func.avg(inner.c.invoice_units).desc())
        .limit(100)
        .all()
    )

    # Rate card max_units — separate query to avoid fan-out
    rc_rows = (
        db.query(
            RateCard.taxonomy_code,
            Contract.supplier_id,
            func.max(RateCard.max_units).label("max_units"),
        )
        .join(Contract, Contract.id == RateCard.contract_id)
        .filter(
            Contract.carrier_id == current_user.carrier_id,
            RateCard.max_units.isnot(None),
        )
        .group_by(RateCard.taxonomy_code, Contract.supplier_id)
        .all()
    )
    max_units_lookup = {
        (rc.taxonomy_code, str(rc.supplier_id)): rc.max_units for rc in rc_rows
    }

    def _pct(avg_units, cap) -> str | None:
        if not cap or not avg_units:
            return None
        return str(round(Decimal(str(avg_units)) / Decimal(str(cap)) * 100, 1))

    return [
        {
            "taxonomy_code": r.taxonomy_code,
            "taxonomy_label": r.taxonomy_label,
            "domain": r.domain,
            "supplier_id": str(r.supplier_id),
            "supplier_name": r.supplier_name,
            "total_invoices": r.total_invoices,
            "total_units": str(round(Decimal(str(r.total_units or 0)), 2)),
            "avg_units_per_invoice": str(
                round(Decimal(str(r.avg_units_per_invoice or 0)), 2)
            ),
            "max_single_invoice": str(
                round(Decimal(str(r.max_single_invoice or 0)), 2)
            ),
            "max_units_cap": str(
                max_units_lookup[(r.taxonomy_code, str(r.supplier_id))]
            )
            if (r.taxonomy_code, str(r.supplier_id)) in max_units_lookup
            else None,
            "cap_utilization_pct": _pct(
                r.avg_units_per_invoice,
                max_units_lookup.get((r.taxonomy_code, str(r.supplier_id))),
            ),
        }
        for r in rows
    ]


# ── Claim Stacking / Vendor Overlap ───────────────────────────────────────────


@router.get("/claim-stacking")
def get_claim_stacking(
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    supplier_id: Optional[str] = Query(default=None),
    domain: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Detects same-claim service stacking and multi-vendor overlap.

    Returns (claim_number, taxonomy_code) pairs where either:
      - Multiple distinct suppliers billed the same code on the same claim, OR
      - The same code was billed more than twice on the same claim

    Ordered by total billed descending — highest exposure first.
    """
    q = (
        db.query(
            LineItem.claim_number,
            LineItem.taxonomy_code,
            TaxonomyItem.label.label("taxonomy_label"),
            TaxonomyItem.domain,
            func.count(func.distinct(Invoice.supplier_id)).label("supplier_count"),
            func.count(LineItem.id).label("line_item_count"),
            func.sum(LineItem.raw_amount).label("total_billed"),
            func.array_agg(func.distinct(Supplier.name)).label("supplier_names"),
        )
        .join(Invoice, LineItem.invoice_id == Invoice.id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .join(Supplier, Supplier.id == Invoice.supplier_id)
        .outerjoin(TaxonomyItem, TaxonomyItem.code == LineItem.taxonomy_code)
        .filter(
            Contract.carrier_id == current_user.carrier_id,
            LineItem.claim_number.isnot(None),
            LineItem.claim_number != "",
            LineItem.taxonomy_code.isnot(None),
            Invoice.status.notin_(["DRAFT", "PROCESSING"]),
        )
    )
    q = _apply_standard_filters(q, date_from, date_to, supplier_id, domain)

    rows = (
        q.group_by(
            LineItem.claim_number,
            LineItem.taxonomy_code,
            TaxonomyItem.label,
            TaxonomyItem.domain,
        )
        .having(
            (func.count(func.distinct(Invoice.supplier_id)) > 1)
            | (func.count(LineItem.id) > 2)
        )
        .order_by(func.sum(LineItem.raw_amount).desc())
        .limit(100)
        .all()
    )

    return [
        {
            "claim_number": r.claim_number,
            "taxonomy_code": r.taxonomy_code,
            "taxonomy_label": r.taxonomy_label,
            "domain": r.domain,
            "supplier_count": r.supplier_count,
            "line_item_count": r.line_item_count,
            "total_billed": str(r.total_billed or 0),
            "supplier_names": list(r.supplier_names) if r.supplier_names else [],
        }
        for r in rows
    ]


# ── Rate Benchmarks ────────────────────────────────────────────────────────────


@router.get("/rate-benchmarks")
def get_rate_benchmarks(
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    supplier_id: Optional[str] = Query(default=None),
    domain: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Intra-panel rate benchmarking per taxonomy code.

    For each taxonomy code with ≥2 line items, computes each supplier's average
    effective billed rate (raw_amount / raw_quantity) and the panel average across
    all suppliers.  Returns pct_vs_panel so the UI can immediately flag outliers.
    """
    rate_expr = case(
        (LineItem.raw_quantity > 0, LineItem.raw_amount / LineItem.raw_quantity),
        else_=None,
    )

    q = (
        db.query(
            LineItem.taxonomy_code,
            TaxonomyItem.label.label("taxonomy_label"),
            TaxonomyItem.domain,
            Supplier.id.label("supplier_id"),
            Supplier.name.label("supplier_name"),
            func.avg(rate_expr).label("avg_rate"),
            func.count(LineItem.id).label("line_count"),
        )
        .join(Invoice, LineItem.invoice_id == Invoice.id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .join(Supplier, Supplier.id == Invoice.supplier_id)
        .outerjoin(TaxonomyItem, TaxonomyItem.code == LineItem.taxonomy_code)
        .filter(
            Contract.carrier_id == current_user.carrier_id,
            LineItem.taxonomy_code.isnot(None),
            LineItem.raw_quantity > 0,
            Invoice.status.notin_(["DRAFT", "PROCESSING"]),
        )
    )
    q = _apply_standard_filters(q, date_from, date_to, supplier_id, domain)

    rows = (
        q.group_by(
            LineItem.taxonomy_code,
            TaxonomyItem.label,
            TaxonomyItem.domain,
            Supplier.id,
            Supplier.name,
        )
        .having(func.count(LineItem.id) >= 2)
        .order_by(LineItem.taxonomy_code, func.avg(rate_expr).desc())
        .all()
    )

    # Group by taxonomy in Python, compute panel avg, pct_vs_panel per supplier
    tc_groups: dict = defaultdict(list)
    for r in rows:
        tc_groups[r.taxonomy_code].append(r)

    result = []
    for tc, tc_rows in tc_groups.items():
        rates = [Decimal(str(r.avg_rate)) for r in tc_rows if r.avg_rate is not None]
        if not rates:
            continue
        panel_avg = sum(rates) / len(rates)

        supplier_rates = []
        for r in tc_rows:
            if r.avg_rate is None:
                continue
            sup_rate = Decimal(str(r.avg_rate))
            pct = (
                round((sup_rate - panel_avg) / panel_avg * 100, 1) if panel_avg else 0.0
            )
            supplier_rates.append(
                {
                    "supplier_id": str(r.supplier_id),
                    "supplier_name": r.supplier_name,
                    "avg_rate": str(round(sup_rate, 2)),
                    "line_count": r.line_count,
                    "pct_vs_panel": str(pct),
                }
            )

        result.append(
            {
                "taxonomy_code": tc,
                "taxonomy_label": tc_rows[0].taxonomy_label,
                "domain": tc_rows[0].domain,
                "panel_avg_rate": str(round(panel_avg, 2)),
                "supplier_count": len(supplier_rates),
                "supplier_rates": sorted(
                    supplier_rates, key=lambda x: float(x["avg_rate"]), reverse=True
                ),
            }
        )

    result.sort(key=lambda x: float(x["panel_avg_rate"]), reverse=True)
    return result


# ── Value Summary (executive performance report) ────────────────────────────


@router.get("/value-summary")
def get_value_summary(
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Single aggregated endpoint powering the executive Performance tab.

    Returns totals, efficiency stats, per-exception-type savings breakdown,
    a 12-month savings trend, and top suppliers by exception rate — all in
    one round-trip so the tab loads instantly.
    """
    carrier_filter = Contract.carrier_id == current_user.carrier_id

    def _date_filter(q):
        if date_from:
            q = q.filter(Invoice.invoice_date >= date_from)
        if date_to:
            q = q.filter(Invoice.invoice_date <= date_to)
        return q

    # ── Totals ────────────────────────────────────────────────────────────────

    invoices_processed = (
        _date_filter(
            db.query(func.count(func.distinct(Invoice.id)))
            .join(Contract, Contract.id == Invoice.contract_id)
            .filter(carrier_filter, Invoice.status.notin_(["DRAFT", "PROCESSING"]))
        ).scalar()
        or 0
    )

    total_billed = _date_filter(
        db.query(func.sum(LineItem.raw_amount))
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(carrier_filter, Invoice.status.notin_(["DRAFT", "PROCESSING"]))
    ).scalar() or Decimal(0)

    identified_savings = _date_filter(
        db.query(func.sum(LineItem.raw_amount - LineItem.expected_amount))
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .join(ExceptionRecord, ExceptionRecord.line_item_id == LineItem.id)
        .filter(
            carrier_filter,
            LineItem.expected_amount.isnot(None),
            LineItem.raw_amount > LineItem.expected_amount,
        )
    ).scalar() or Decimal(0)

    recovered_savings = _date_filter(
        db.query(func.sum(LineItem.raw_amount - LineItem.expected_amount))
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .join(ExceptionRecord, ExceptionRecord.line_item_id == LineItem.id)
        .filter(
            carrier_filter,
            Invoice.status.in_(["APPROVED", "EXPORTED"]),
            LineItem.expected_amount.isnot(None),
            LineItem.raw_amount > LineItem.expected_amount,
        )
    ).scalar() or Decimal(0)

    pending_savings = max(identified_savings - recovered_savings, Decimal(0))
    recovery_rate = (
        round(float(recovered_savings) / float(identified_savings), 4)
        if identified_savings > 0
        else 0.0
    )

    # ── Efficiency ────────────────────────────────────────────────────────────

    total_lines = (
        _date_filter(
            db.query(func.count(LineItem.id))
            .join(Invoice, Invoice.id == LineItem.invoice_id)
            .join(Contract, Contract.id == Invoice.contract_id)
            .filter(carrier_filter, LineItem.taxonomy_code.isnot(None))
        ).scalar()
        or 0
    )

    auto_classified_lines = (
        _date_filter(
            db.query(func.count(LineItem.id))
            .join(Invoice, Invoice.id == LineItem.invoice_id)
            .join(Contract, Contract.id == Invoice.contract_id)
            .filter(
                carrier_filter,
                LineItem.taxonomy_code.isnot(None),
                LineItem.mapping_confidence == "HIGH",
            )
        ).scalar()
        or 0
    )

    auto_classification_rate = (
        round(auto_classified_lines / total_lines, 4) if total_lines > 0 else 0.0
    )
    estimated_hours_saved = round(auto_classified_lines * (5 / 60), 1)

    # Average exception resolution time (days)
    avg_resolution_days_row = (
        db.query(
            func.avg(
                func.extract(
                    "epoch",
                    ExceptionRecord.resolved_at - ExceptionRecord.created_at,
                )
                / 86400
            )
        )
        .join(LineItem, LineItem.id == ExceptionRecord.line_item_id)
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            carrier_filter,
            ExceptionRecord.resolved_at.isnot(None),
        )
        .scalar()
    )
    avg_resolution_days = (
        round(float(avg_resolution_days_row), 1) if avg_resolution_days_row else 0.0
    )

    # AI recommendation acceptance rate
    ai_rows = (
        db.query(
            func.count(ExceptionRecord.id).label("resolved"),
            func.sum(
                case((ExceptionRecord.ai_recommendation_accepted == True, 1), else_=0)  # noqa: E712
            ).label("accepted"),
        )
        .join(LineItem, LineItem.id == ExceptionRecord.line_item_id)
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            carrier_filter,
            ExceptionRecord.ai_recommendation.isnot(None),
            ExceptionRecord.ai_recommendation_accepted.isnot(None),
        )
        .one()
    )
    ai_recommendation_acceptance_rate = (
        round(int(ai_rows.accepted or 0) / int(ai_rows.resolved), 4)
        if ai_rows.resolved
        else 0.0
    )

    # ── Savings by exception type ─────────────────────────────────────────────

    by_type: dict = {
        "RATE": {
            "flagged": 0,
            "resolved": 0,
            "identified_savings": Decimal(0),
            "recovered_savings": Decimal(0),
            "recovery_rate": 0.0,
        },
        "GUIDELINE": {
            "flagged": 0,
            "resolved": 0,
            "identified_savings": Decimal(0),
            "recovered_savings": Decimal(0),
            "recovery_rate": 0.0,
        },
        "CLASSIFICATION": {
            "flagged": 0,
            "resolved": 0,
            "identified_savings": Decimal(0),
            "recovered_savings": Decimal(0),
            "recovery_rate": 0.0,
        },
    }

    type_rows = (
        _date_filter(
            db.query(
                ValidationResult.validation_type,
                func.count(ExceptionRecord.id).label("flagged"),
                func.sum(
                    case(
                        (ExceptionRecord.status.in_(["RESOLVED", "WAIVED"]), 1),
                        else_=0,
                    )
                ).label("resolved"),
                func.sum(
                    case(
                        (
                            (LineItem.raw_amount > LineItem.expected_amount)
                            & LineItem.expected_amount.isnot(None),
                            LineItem.raw_amount - LineItem.expected_amount,
                        ),
                        else_=Decimal(0),
                    )
                ).label("identified"),
                func.sum(
                    case(
                        (
                            (LineItem.raw_amount > LineItem.expected_amount)
                            & LineItem.expected_amount.isnot(None)
                            & Invoice.status.in_(["APPROVED", "EXPORTED"]),
                            LineItem.raw_amount - LineItem.expected_amount,
                        ),
                        else_=Decimal(0),
                    )
                ).label("recovered"),
            )
            .join(
                ExceptionRecord,
                ExceptionRecord.validation_result_id == ValidationResult.id,
            )
            .join(LineItem, LineItem.id == ExceptionRecord.line_item_id)
            .join(Invoice, Invoice.id == LineItem.invoice_id)
            .join(Contract, Contract.id == Invoice.contract_id)
            .filter(carrier_filter)
        )
        .group_by(ValidationResult.validation_type)
        .all()
    )

    for row in type_rows:
        vtype = row.validation_type
        if vtype not in by_type:
            continue
        ident = row.identified or Decimal(0)
        recov = row.recovered or Decimal(0)
        by_type[vtype] = {
            "flagged": row.flagged,
            "resolved": row.resolved,
            "identified_savings": str(ident),
            "recovered_savings": str(recov),
            "recovery_rate": round(float(recov) / float(ident), 4)
            if ident > 0
            else 0.0,
        }
    # Ensure string format for any untouched types
    for vtype, d in by_type.items():
        if isinstance(d["identified_savings"], Decimal):
            d["identified_savings"] = str(d["identified_savings"])
            d["recovered_savings"] = str(d["recovered_savings"])

    # ── Savings trend (last 12 months, monthly) ────────────────────────────────

    trend_from = date_from or (date.today().replace(day=1) - timedelta(days=365))

    trend_identified_rows = (
        db.query(
            func.date_trunc("month", Invoice.invoice_date).label("period"),
            func.sum(LineItem.raw_amount - LineItem.expected_amount).label(
                "identified"
            ),
        )
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .join(ExceptionRecord, ExceptionRecord.line_item_id == LineItem.id)
        .filter(
            carrier_filter,
            LineItem.expected_amount.isnot(None),
            LineItem.raw_amount > LineItem.expected_amount,
            Invoice.invoice_date >= trend_from,
        )
        .group_by(func.date_trunc("month", Invoice.invoice_date))
        .order_by(func.date_trunc("month", Invoice.invoice_date))
        .all()
    )

    trend_recovered_rows = (
        db.query(
            func.date_trunc("month", Invoice.invoice_date).label("period"),
            func.sum(LineItem.raw_amount - LineItem.expected_amount).label("recovered"),
        )
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .join(ExceptionRecord, ExceptionRecord.line_item_id == LineItem.id)
        .filter(
            carrier_filter,
            Invoice.status.in_(["APPROVED", "EXPORTED"]),
            LineItem.expected_amount.isnot(None),
            LineItem.raw_amount > LineItem.expected_amount,
            Invoice.invoice_date >= trend_from,
        )
        .group_by(func.date_trunc("month", Invoice.invoice_date))
        .order_by(func.date_trunc("month", Invoice.invoice_date))
        .all()
    )

    identified_by_period = {
        str(r.period)[:7]: float(r.identified or 0) for r in trend_identified_rows
    }
    recovered_by_period = {
        str(r.period)[:7]: float(r.recovered or 0) for r in trend_recovered_rows
    }
    all_periods = sorted(set(identified_by_period) | set(recovered_by_period))
    savings_trend = [
        {
            "period": p,
            "identified": identified_by_period.get(p, 0.0),
            "recovered": recovered_by_period.get(p, 0.0),
        }
        for p in all_periods
    ]

    # ── Top suppliers by exception rate ───────────────────────────────────────

    supplier_stats_rows = (
        _date_filter(
            db.query(
                Supplier.name.label("supplier_name"),
                func.count(LineItem.id).label("total_lines"),
                func.sum(case((ExceptionRecord.id.isnot(None), 1), else_=0)).label(
                    "exception_lines"
                ),
                func.sum(
                    case(
                        (
                            (LineItem.raw_amount > LineItem.expected_amount)
                            & LineItem.expected_amount.isnot(None),
                            LineItem.raw_amount - LineItem.expected_amount,
                        ),
                        else_=Decimal(0),
                    )
                ).label("identified_savings"),
            )
            .join(Invoice, Invoice.id == LineItem.invoice_id)
            .join(Contract, Contract.id == Invoice.contract_id)
            .join(Supplier, Supplier.id == Invoice.supplier_id)
            .outerjoin(ExceptionRecord, ExceptionRecord.line_item_id == LineItem.id)
            .filter(carrier_filter, Invoice.status.notin_(["DRAFT", "PROCESSING"]))
        )
        .group_by(Supplier.name)
        .order_by(func.count(LineItem.id).desc())
        .limit(20)
        .all()
    )

    top_suppliers = []
    for row in supplier_stats_rows:
        total = row.total_lines or 0
        exc = int(row.exception_lines or 0)
        if total == 0:
            continue
        top_suppliers.append(
            {
                "supplier_name": row.supplier_name,
                "total_lines": total,
                "exception_lines": exc,
                "exception_rate": round(exc / total, 4),
                "identified_savings": round(float(row.identified_savings or 0), 2),
            }
        )
    top_suppliers.sort(key=lambda x: x["exception_rate"], reverse=True)
    top_suppliers = top_suppliers[:6]

    # ── Assemble response ─────────────────────────────────────────────────────

    effective_from = date_from or trend_from
    effective_to = date_to or date.today()
    period_days = (effective_to - effective_from).days + 1

    return {
        "period": {
            "from": str(effective_from),
            "to": str(effective_to),
            "days": period_days,
        },
        "totals": {
            "invoices_processed": invoices_processed,
            "total_billed": str(total_billed),
            "identified_savings": str(identified_savings),
            "recovered_savings": str(recovered_savings),
            "pending_savings": str(pending_savings),
            "recovery_rate": recovery_rate,
        },
        "efficiency": {
            "total_lines": total_lines,
            "auto_classified_lines": auto_classified_lines,
            "auto_classification_rate": auto_classification_rate,
            "avg_exception_resolution_days": avg_resolution_days,
            "ai_recommendation_acceptance_rate": ai_recommendation_acceptance_rate,
            "estimated_hours_saved": estimated_hours_saved,
        },
        "by_type": by_type,
        "savings_trend": savings_trend,
        "top_suppliers_by_exception_rate": top_suppliers,
    }
