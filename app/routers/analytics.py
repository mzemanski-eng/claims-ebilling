"""
Analytics API routes for carrier admins.

Provides aggregated spend and billing operations metrics — all-time by default,
which is the correct baseline for RFP benchmarking and contract negotiation.

  GET /admin/analytics/summary               → KPI scalars (billed, approved, savings, exceptions)
  GET /admin/analytics/spend-by-domain       → spend grouped by service domain (IME, ENG, etc.)
  GET /admin/analytics/spend-by-supplier     → spend grouped by supplier
  GET /admin/analytics/spend-by-taxonomy     → spend grouped by taxonomy code
  GET /admin/analytics/exception-breakdown   → exception counts by validation type
  GET /admin/analytics/rate-gaps             → services billed with no contracted rate card
  GET /admin/analytics/supplier-comparison   → side-by-side spend per supplier × taxonomy code
                                               ?format=csv returns a downloadable CSV file
"""

import csv
import io
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.invoice import Invoice, LineItem
from app.models.supplier import Supplier, UserRole
from app.models.taxonomy import TaxonomyItem
from app.models.validation import ExceptionRecord, ExceptionStatus, RequiredAction, ValidationResult
from app.routers.auth import require_role

router = APIRouter(prefix="/admin/analytics", tags=["analytics"])

_CARRIER_ROLES = (
    UserRole.CARRIER_ADMIN,
    UserRole.CARRIER_REVIEWER,
    UserRole.SYSTEM_ADMIN,
)


# ── Summary ───────────────────────────────────────────────────────────────────


@router.get("/summary")
def get_analytics_summary(
    db: Session = Depends(get_db),
    current_user=Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Returns five KPI scalars + invoice status breakdown for the header cards
    and the status distribution chart.
    """

    # Total billed: sum raw_amount across all non-draft/non-processing invoices
    total_billed = (
        db.query(func.sum(LineItem.raw_amount))
        .join(Invoice)
        .filter(Invoice.status.notin_(["DRAFT", "PROCESSING"]))
        .scalar()
        or Decimal(0)
    )

    # Total approved: expected_amount on finalized invoices, excluding denied lines
    total_approved = (
        db.query(func.sum(LineItem.expected_amount))
        .join(Invoice)
        .filter(
            Invoice.status.in_(["APPROVED", "EXPORTED"]),
            LineItem.status != "DENIED",
            LineItem.expected_amount.isnot(None),
        )
        .scalar()
        or Decimal(0)
    )

    # Identified savings: lines where billed exceeded contract rate (approved < billed)
    total_savings = (
        db.query(func.sum(LineItem.raw_amount - LineItem.expected_amount))
        .join(Invoice)
        .filter(
            Invoice.status.in_(["APPROVED", "EXPORTED"]),
            LineItem.expected_amount.isnot(None),
            LineItem.raw_amount > LineItem.expected_amount,
        )
        .scalar()
        or Decimal(0)
    )

    # Invoice counts by status (all statuses — let the frontend filter)
    status_rows = (
        db.query(Invoice.status, func.count(Invoice.id))
        .group_by(Invoice.status)
        .all()
    )

    # Open exception count (OPEN only)
    open_exceptions = (
        db.query(func.count(ExceptionRecord.id))
        .filter(ExceptionRecord.status == ExceptionStatus.OPEN)
        .scalar()
        or 0
    )

    total_exceptions = db.query(func.count(ExceptionRecord.id)).scalar() or 0

    return {
        "total_billed": str(total_billed),
        "total_approved": str(total_approved),
        "total_savings": str(total_savings),
        "open_exceptions": open_exceptions,
        "total_exceptions": total_exceptions,
        "invoice_status_counts": [
            {"status": row[0], "count": row[1]} for row in status_rows
        ],
    }


# ── Spend by Domain ───────────────────────────────────────────────────────────


@router.get("/spend-by-domain")
def get_spend_by_domain(
    db: Session = Depends(get_db),
    current_user=Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Groups classified line items by the first segment of their taxonomy code
    (the service domain: IME, ENG, IA, INV, REC, XDOMAIN).
    Only classified lines are included.
    """
    domain_expr = func.split_part(LineItem.taxonomy_code, ".", 1).label("domain")

    rows = (
        db.query(
            domain_expr,
            func.count(LineItem.id).label("line_count"),
            func.sum(LineItem.raw_amount).label("total_billed"),
            func.coalesce(func.sum(LineItem.expected_amount), 0).label(
                "total_approved"
            ),
        )
        .filter(LineItem.taxonomy_code.isnot(None))
        .group_by(domain_expr)
        .order_by(func.sum(LineItem.raw_amount).desc())
        .all()
    )

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
    db: Session = Depends(get_db),
    current_user=Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Supplier-level spend rollup for RFP benchmarking.
    Excludes DRAFT and PROCESSING invoices (not yet actionable).
    """
    rows = (
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
        .filter(Invoice.status.notin_(["DRAFT", "PROCESSING"]))
        .group_by(Supplier.id, Supplier.name)
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
    db: Session = Depends(get_db),
    current_user=Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Full taxonomy code breakdown — the data foundation for the spend intelligence table.
    Joins to TaxonomyItem for label and domain; left-join to handle any orphaned codes.
    """
    rows = (
        db.query(
            LineItem.taxonomy_code,
            TaxonomyItem.label,
            TaxonomyItem.domain,
            func.count(LineItem.id).label("line_count"),
            func.sum(LineItem.raw_amount).label("total_billed"),
            func.coalesce(func.sum(LineItem.expected_amount), 0).label(
                "total_approved"
            ),
        )
        .join(
            TaxonomyItem, LineItem.taxonomy_code == TaxonomyItem.code, isouter=True
        )
        .filter(LineItem.taxonomy_code.isnot(None))
        .group_by(LineItem.taxonomy_code, TaxonomyItem.label, TaxonomyItem.domain)
        .order_by(func.sum(LineItem.raw_amount).desc())
        .all()
    )

    return [
        {
            "taxonomy_code": row.taxonomy_code,
            "label": row.label,
            "domain": row.domain,
            "line_count": row.line_count,
            "total_billed": str(row.total_billed),
            "total_approved": str(row.total_approved),
        }
        for row in rows
    ]


# ── Exception Breakdown ───────────────────────────────────────────────────────


@router.get("/exception-breakdown")
def get_exception_breakdown(
    db: Session = Depends(get_db),
    current_user=Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Groups exceptions by their source validation type (RATE / GUIDELINE / CLASSIFICATION)
    to show where billing issues originate.
    """
    rows = (
        db.query(
            ValidationResult.validation_type,
            func.count(ExceptionRecord.id).label("count"),
        )
        .join(
            ExceptionRecord,
            ExceptionRecord.validation_result_id == ValidationResult.id,
        )
        .group_by(ValidationResult.validation_type)
        .order_by(func.count(ExceptionRecord.id).desc())
        .all()
    )

    return [
        {"validation_type": row.validation_type, "count": row.count}
        for row in rows
    ]


# ── Rate Card Gaps ─────────────────────────────────────────────────────────────


@router.get("/rate-gaps")
def get_rate_gaps(
    db: Session = Depends(get_db),
    current_user=Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Returns services being billed with no contracted rate card.

    Finds ValidationResult rows where required_action=ESTABLISH_CONTRACT_RATE,
    joins to LineItem → Invoice → Supplier, and groups by taxonomy_code + supplier.
    Ordered by total billed descending so the highest-exposure gaps are first.

    This gives carriers a clear action list: go to the Contracts admin and add
    the missing rate card for each row.
    """
    rows = (
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
        .join(Supplier, Supplier.id == Invoice.supplier_id)
        .outerjoin(TaxonomyItem, TaxonomyItem.code == LineItem.taxonomy_code)
        .filter(
            Invoice.carrier_id == current_user.carrier_id,
            ValidationResult.required_action == RequiredAction.ESTABLISH_CONTRACT_RATE,
        )
        .group_by(
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
    db: Session = Depends(get_db),
    current_user=Depends(require_role(*_CARRIER_ROLES)),
    format: str = Query(default="json", pattern="^(json|csv)$"),
):
    """
    Side-by-side spend analysis per supplier × taxonomy code.

    Returns every (supplier, taxonomy_code) pair that has at least one
    processed invoice line, with billed vs. expected amounts and the
    number of exceptions raised.

    Query params:
      ?format=csv  — returns a downloadable CSV file instead of JSON
    """
    rows = (
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
        .join(Supplier, Supplier.id == Invoice.supplier_id)
        .outerjoin(TaxonomyItem, TaxonomyItem.code == LineItem.taxonomy_code)
        .outerjoin(ExceptionRecord, ExceptionRecord.line_item_id == LineItem.id)
        .filter(
            Invoice.carrier_id == current_user.carrier_id,
            LineItem.taxonomy_code.isnot(None),
        )
        .group_by(
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
            headers={"Content-Disposition": "attachment; filename=supplier-comparison.csv"},
        )

    return records


# ── AI Accuracy ────────────────────────────────────────────────────────────────


@router.get("/ai-accuracy")
def get_ai_accuracy(
    db: Session = Depends(get_db),
    current_user=Depends(require_role(*_CARRIER_ROLES)),
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
                case((ExceptionRecord.ai_recommendation_accepted.isnot(None), 1), else_=0)
            ).label("resolved"),
            func.sum(
                case((ExceptionRecord.ai_recommendation_accepted == True, 1), else_=0)  # noqa: E712
            ).label("accepted"),
        )
        .join(LineItem, LineItem.id == ExceptionRecord.line_item_id)
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .filter(
            Invoice.carrier_id == current_user.carrier_id,
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
            "acceptance_rate": round(r.accepted / r.resolved, 4) if r.resolved else None,
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
