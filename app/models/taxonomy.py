"""
TaxonomyItem — the Claims UTMSB taxonomy table.

Codes follow the pattern: {DOMAIN}.{SERVICE_ITEM}.{COMPONENT}
e.g.  IME.PHY_EXAM.PROF_FEE

This table is seeded from app/taxonomy/seed.py and treated as
configuration-level data (rarely changes; changes are versioned).
"""

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TaxonomyItem(Base, TimestampMixin):
    __tablename__ = "taxonomy_items"

    # Natural key — human-readable, stable, used as FK target everywhere
    code: Mapped[str] = mapped_column(String(64), primary_key=True)

    # ── Hierarchy ───────────────────────────────────────────────────────────
    domain: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        index=True,
        comment="Top-level domain: IME | ENG | IA | INV | REC | XDOMAIN",
    )
    service_item: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="e.g. PHY_EXAM, CAUSE_ORIGIN, FIELD_ASSIGN"
    )
    billing_component: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="e.g. PROF_FEE, MILEAGE, TRAVEL_LODGING"
    )

    # ── Unit model ──────────────────────────────────────────────────────────
    unit_model: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment=(
            "per_report | per_hour | per_mile | per_page | flat_fee | "
            "per_diem | actual | per_night | per_request | per_file | "
            "per_occurrence"
        ),
    )

    # ── Display ─────────────────────────────────────────────────────────────
    label: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Short human-readable label shown in carrier UI",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=True,
        comment="Longer description for guideline authoring / contract mapping",
    )

    # ── Lifecycle ───────────────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    def __repr__(self) -> str:
        return f"<TaxonomyItem code={self.code!r} label={self.label!r}>"
