"""
Analytics API routes for carrier admins.

Provides aggregated spend and billing operations metrics — all-time by default,
which is the correct baseline for RFP benchmarking and contract negotiation.

  GET /admin/analytics/summary                        → KPI scalars (billed, approved, savings, exceptions)
  GET /admin/analytics/spend-by-domain                → spend grouped by service domain (IME, ENG, etc.)
  GET /admin/analytics/spend-by-supplier              → spend grouped by supplier
  GET /admin/analytics/spend-by-taxonomy              → spend grouped by taxonomy code (+ units, avg rate)
  GET /admin/analytics/exception-breakdown            → exception counts by validation type
  GET /admin/analytics/rate-gaps                      → services billed with no contracted rate card
  GET /admin/analytics/supplier-comparison            → side-by-side spend per supplier × taxonomy code
                                                         ?format=csv returns a downloadable CSV file
  GET /admin/analytics/spend-trend                    → monthly spend trend (last 18 months)
  GET /admin/analytics/contract-health                → per-contract rate card coverage + expiry alerts
  GET /admin/analytics/supplier-scorecard/{id}        → per-supplier performance KPIs
"""

import csv
import io
from datetime import date
from decimal import Decimal

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


# ── Summary ───────────────────────────────────────────────────────────────────


@router.get("/summary")
def get_analytics_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Returns five KPI scalars + invoice status breakdown for the header cards
    and the status distribution chart.
    """

    # Total billed: sum raw_amount across all non-draft/non-processing invoices
    total_billed = (
        db.query(func.sum(LineItem.raw_amount))
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            Contract.carrier_id == current_user.carrier_id,
            Invoice.status.notin_(["DRAFT", "PROCESSING"]),
        )
        .scalar()
        or Decimal(0)
    )

    # Total approved: expected_amount on finalized invoices, excluding denied lines
    total_approved = (
        db.query(func.sum(LineItem.expected_amount))
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            Contract.carrier_id == current_user.carrier_id,
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
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            Contract.carrier_id == current_user.carrier_id,
            Invoice.status.in_(["APPROVED", "EXPORTED"]),
            LineItem.expected_amount.isnot(None),
            LineItem.raw_amount > LineItem.expected_amount,
        )
        .scalar()
        or Decimal(0)
    )

    # Invoice counts by status — scoped to this carrier
    status_rows = (
        db.query(Invoice.status, func.count(Invoice.id))
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(Contract.carrier_id == current_user.carrier_id)
        .group_by(Invoice.status)
        .all()
    )

    # Open exception count (OPEN only) — scoped to this carrier
    open_exceptions = (
        db.query(func.count(ExceptionRecord.id))
        .join(LineItem, LineItem.id == ExceptionRecord.line_item_id)
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            Contract.carrier_id == current_user.carrier_id,
            ExceptionRecord.status == ExceptionStatus.OPEN,
        )
        .scalar()
        or 0
    )

    total_exceptions = (
        db.query(func.count(ExceptionRecord.id))
        .join(LineItem, LineItem.id == ExceptionRecord.line_item_id)
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(Contract.carrier_id == current_user.carrier_id)
        .scalar()
        or 0
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
    }


# ── Spend by Domain ───────────────────────────────────────────────────────────


@router.get("/spend-by-domain")
def get_spend_by_domain(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
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
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            Contract.carrier_id == current_user.carrier_id,
            LineItem.taxonomy_code.isnot(None),
        )
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
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
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
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            Contract.carrier_id == current_user.carrier_id,
            Invoice.status.notin_(["DRAFT", "PROCESSING"]),
        )
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
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Full taxonomy code breakdown — the data foundation for the spend intelligence table.
    Joins to TaxonomyItem for label and domain; left-join to handle any orphaned codes.
    Includes total_quantity (sum of raw_quantity) and avg_billed_rate for sourcing intel.
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
            func.sum(LineItem.raw_quantity).label("total_quantity"),
        )
        .join(TaxonomyItem, LineItem.taxonomy_code == TaxonomyItem.code, isouter=True)
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(
            Contract.carrier_id == current_user.carrier_id,
            LineItem.taxonomy_code.isnot(None),
        )
        .group_by(LineItem.taxonomy_code, TaxonomyItem.label, TaxonomyItem.domain)
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
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
        .join(LineItem, LineItem.id == ExceptionRecord.line_item_id)
        .join(Invoice, Invoice.id == LineItem.invoice_id)
        .join(Contract, Contract.id == Invoice.contract_id)
        .filter(Contract.carrier_id == current_user.carrier_id)
        .group_by(ValidationResult.validation_type)
        .order_by(func.count(ExceptionRecord.id).desc())
        .all()
    )

    return [
        {"validation_type": row.validation_type, "count": row.count} for row in rows
    ]


# ── Rate Card Gaps ─────────────────────────────────────────────────────────────


@router.get("/rate-gaps")
def get_rate_gaps(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Returns services being billed with no contracted rate card.

    Finds ValidationResult rows where required_action=ESTABLISH_CONTRACT_RATE,
    joins to LineItem → Invoice → Contract → Supplier, and groups by taxonomy_code + supplier.
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
        .join(Contract, Contract.id == Invoice.contract_id)
        .join(Supplier, Supplier.id == Invoice.supplier_id)
        .outerjoin(TaxonomyItem, TaxonomyItem.code == LineItem.taxonomy_code)
        .filter(
            Contract.carrier_id == current_user.carrier_id,
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
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
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
        .join(Contract, Contract.id == Invoice.contract_id)
        .join(Supplier, Supplier.id == Invoice.supplier_id)
        .outerjoin(TaxonomyItem, TaxonomyItem.code == LineItem.taxonomy_code)
        .outerjoin(ExceptionRecord, ExceptionRecord.line_item_id == LineItem.id)
        .filter(
            Contract.carrier_id == current_user.carrier_id,
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Spend aggregated by US state (service_state on LineItem).
    Only lines that have a service_state value are included.
    Used to drive the geographic choropleth map.
    """
    rows = (
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
        .group_by(LineItem.service_state)
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
    state: str | None = Query(default=None, description="Filter to a single state code, e.g. CA"),
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_CARRIER_ROLES)),
):
    """
    Monthly (or weekly) spend trend — last 18 months.

    Groups all non-draft invoices by the truncated invoice_date period, returns
    total_billed, total_approved (on approved/exported invoices), and invoice count.
    Ordered oldest → newest for charting left-to-right.
    """
    trunc_expr = func.date_trunc(period, Invoice.invoice_date).label("period")

    rows = (
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
            Invoice.invoice_date >= func.date_trunc(
                period,
                func.cast(
                    func.now() - text("INTERVAL '18 months'"), Invoice.invoice_date.type
                ),
            ),
        )
        .group_by(trunc_expr)
        .order_by(trunc_expr)
        .all()
    )

    return [
        {
            "period": row.period.strftime("%Y-%m") if hasattr(row.period, "strftime") else str(row.period)[:7],
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
        .group_by(Contract.id, Contract.name, Contract.effective_from,
                  Contract.effective_to, Contract.is_active, Supplier.name)
        .order_by(Contract.effective_to.asc().nullslast(), Contract.name)
        .all()
    )

    # Rate card counts per contract (separate query — avoids fan-out)
    rc_counts = dict(
        db.query(RateCard.contract_id, func.count(RateCard.id))
        .filter(
            RateCard.contract_id.in_([r.id for r in rows])
        )
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
        result.append({
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
        })
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

    Returns:
      - Invoice counts by status
      - Exception rate (exceptions / invoices)
      - Auto-approval rate (APPROVED invoices without any exceptions)
      - Total billed and identified savings
      - Top 5 taxonomy codes by billed amount
      - Top 3 exception types by count
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
            func.coalesce(func.sum(LineItem.expected_amount), 0).label("total_expected"),
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
    exception_rate = round(total_exceptions / total_invoices, 4) if total_invoices else 0.0

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
    approved_count = invoice_status_counts.get("APPROVED", 0) + invoice_status_counts.get("EXPORTED", 0)
    clean_approved = max(approved_count - invoices_with_exceptions, 0)
    auto_approval_rate = round(clean_approved / total_invoices, 4) if total_invoices else 0.0

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
        .join(ExceptionRecord, ExceptionRecord.validation_result_id == ValidationResult.id)
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
