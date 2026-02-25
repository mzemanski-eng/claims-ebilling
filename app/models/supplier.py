"""
Supplier-side entities: User, Carrier, Supplier, Contract, RateCard, Guideline.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.invoice import Invoice
    from app.models.taxonomy import TaxonomyItem
    from app.models.mapping import MappingRule


# ── Enums (stored as strings for readability + migration safety) ────────────


class UserRole:
    SUPPLIER = "SUPPLIER"
    CARRIER_ADMIN = "CARRIER_ADMIN"
    CARRIER_REVIEWER = "CARRIER_REVIEWER"
    SYSTEM_ADMIN = "SYSTEM_ADMIN"


class GeographyScope:
    NATIONAL = "national"
    STATE = "state"
    REGIONAL = "regional"


# ── Models ──────────────────────────────────────────────────────────────────


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(256), nullable=False, unique=True, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)

    # Optional FK — set for SUPPLIER role; null for CARRIER_* roles
    supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    carrier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("carriers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # Relationships
    supplier: Mapped[Optional["Supplier"]] = relationship(
        "Supplier", back_populates="users", foreign_keys=[supplier_id]
    )
    carrier: Mapped[Optional["Carrier"]] = relationship(
        "Carrier", back_populates="users", foreign_keys=[carrier_id]
    )

    def __repr__(self) -> str:
        return f"<User email={self.email!r} role={self.role!r}>"


class Carrier(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An insurance carrier / client of the platform."""

    __tablename__ = "carriers"

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    short_code: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        unique=True,
        comment="e.g. ACME — used in UI and exports",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # Relationships
    users: Mapped[list["User"]] = relationship(
        "User", back_populates="carrier", foreign_keys="User.carrier_id"
    )
    contracts: Mapped[list["Contract"]] = relationship(
        "Contract", back_populates="carrier"
    )

    def __repr__(self) -> str:
        return f"<Carrier name={self.name!r}>"


class Supplier(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A vendor/supplier who submits invoices."""

    __tablename__ = "suppliers"

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    tax_id: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, comment="EIN or SSN (masked in UI)"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # Relationships
    users: Mapped[list["User"]] = relationship(
        "User", back_populates="supplier", foreign_keys="User.supplier_id"
    )
    contracts: Mapped[list["Contract"]] = relationship(
        "Contract", back_populates="supplier"
    )
    invoices: Mapped[list["Invoice"]] = relationship(
        "Invoice", back_populates="supplier"
    )
    mapping_rules: Mapped[list["MappingRule"]] = relationship(
        "MappingRule", back_populates="supplier"
    )

    def __repr__(self) -> str:
        return f"<Supplier name={self.name!r}>"


class Contract(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    A contract between a carrier and a supplier.
    Has child RateCard rows and Guideline rows.
    """

    __tablename__ = "contracts"
    __table_args__ = (
        UniqueConstraint(
            "supplier_id", "carrier_id", "effective_from", name="uq_contract_effective"
        ),
    )

    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    carrier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("carriers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="e.g. 'ACME IME Services Agreement 2024'"
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True, comment="NULL = still active"
    )

    geography_scope: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=GeographyScope.NATIONAL,
        comment="national | state | regional",
    )
    # JSONB array of state codes, e.g. ["CA", "NY", "FL"]; NULL = all states
    state_codes: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # Relationships
    supplier: Mapped["Supplier"] = relationship("Supplier", back_populates="contracts")
    carrier: Mapped["Carrier"] = relationship("Carrier", back_populates="contracts")
    rate_cards: Mapped[list["RateCard"]] = relationship(
        "RateCard", back_populates="contract", cascade="all, delete-orphan"
    )
    guidelines: Mapped[list["Guideline"]] = relationship(
        "Guideline", back_populates="contract", cascade="all, delete-orphan"
    )
    invoices: Mapped[list["Invoice"]] = relationship(
        "Invoice", back_populates="contract"
    )

    def __repr__(self) -> str:
        return f"<Contract name={self.name!r} effective_from={self.effective_from}>"


class RateCard(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    A single rate entry within a contract.
    The rate validator uses this to check: billed_amount vs quantity × contracted_rate.
    """

    __tablename__ = "rate_cards"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    taxonomy_code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("taxonomy_items.code", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Contracted rate per unit (DECIMAL for financial precision — never float)
    contracted_rate: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    # NULL = no per-invoice unit cap; set to cap maximum payable units
    max_units: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)

    # True if this rate is all-inclusive (travel/mileage bundled in)
    is_all_inclusive: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="If true, separate travel/mileage charges are prohibited",
    )

    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    contract: Mapped["Contract"] = relationship("Contract", back_populates="rate_cards")
    taxonomy_item: Mapped["TaxonomyItem"] = relationship("TaxonomyItem")

    def __repr__(self) -> str:
        return f"<RateCard taxonomy={self.taxonomy_code!r} rate={self.contracted_rate}>"


class Guideline(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    A structured rule derived from narrative contract language.
    Authored by carrier admins via the guideline authoring UI.

    rule_type options and expected rule_params shapes:
      max_units:            {"max": 8, "period": "per_claim"}
      requires_auth:        {"required": true, "auth_field": "auth_number"}
      billing_increment:    {"min_increment": 0.25, "unit": "hour"}
      bundling_prohibition: {"prohibited_components": ["TRAVEL_TRANSPORT", "MILEAGE"]}
      cap_amount:           {"max_amount": 500.00}
    """

    __tablename__ = "guidelines"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Scope: NULL taxonomy_code = applies to full domain
    taxonomy_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("taxonomy_items.code", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    domain: Mapped[Optional[str]] = mapped_column(
        String(16),
        nullable=True,
        comment="If taxonomy_code is NULL, applies to this domain (e.g. IME)",
    )

    rule_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="max_units | requires_auth | billing_increment | bundling_prohibition | cap_amount",
    )
    rule_params: Mapped[dict] = mapped_column(JSONB, nullable=False)
    severity: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ERROR", comment="ERROR | WARNING | INFO"
    )

    # Original contract language — surfaced in exception messages for auditability
    narrative_source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # Relationships
    contract: Mapped["Contract"] = relationship("Contract", back_populates="guidelines")

    def __repr__(self) -> str:
        return (
            f"<Guideline rule_type={self.rule_type!r} taxonomy={self.taxonomy_code!r}>"
        )
