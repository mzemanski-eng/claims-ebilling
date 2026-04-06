"""
TaxonomyItem — the Veridian ALAE taxonomy table.
Vertical — line-of-business grouping for Phase 2+.

Codes follow the pattern: {DOMAIN}.{SERVICE_ITEM}.{COMPONENT}
e.g.  IA.FIELD_ASSIGN.PROF_FEE

This table is seeded from app/taxonomy/seed.py and treated as
configuration-level data (rarely changes; changes are versioned).
"""

import uuid
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Vertical(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Line-of-business vertical (e.g. ALE, Restoration, Legal).
    Seeds: ale | restoration | legal
    Used in Phase 3 for per-vertical AI prompt routing and taxonomy scoping.
    """

    __tablename__ = "verticals"

    slug: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
        comment="URL-safe identifier, e.g. 'ale', 'restoration'",
    )
    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Display name, e.g. 'ALE', 'Restoration'",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # Relationships
    taxonomy_items: Mapped[list["TaxonomyItem"]] = relationship(
        "TaxonomyItem", back_populates="vertical"
    )

    def __repr__(self) -> str:
        return f"<Vertical slug={self.slug!r} name={self.name!r}>"


class TaxonomyItem(Base, TimestampMixin):
    __tablename__ = "taxonomy_items"

    # Natural key — human-readable, stable, used as FK target everywhere
    code: Mapped[str] = mapped_column(String(64), primary_key=True)

    # ── Vertical (Phase 2: nullable; Phase 3: populated for vertical routing) ─
    vertical_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("verticals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Line-of-business vertical. NULL = not yet assigned.",
    )

    # ── Hierarchy ───────────────────────────────────────────────────────────
    domain: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        index=True,
        comment="Top-level domain: IA | ENG | REC | LA | INSP | VIRT | CR | INV | DRNE | APPR | XDOMAIN",
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

    # Relationships
    vertical: Mapped[Optional["Vertical"]] = relationship(
        "Vertical", back_populates="taxonomy_items"
    )

    def __repr__(self) -> str:
        return f"<TaxonomyItem code={self.code!r} label={self.label!r}>"
