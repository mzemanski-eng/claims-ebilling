"""
MappingRule — persisted rules that translate supplier line descriptions/codes
into taxonomy codes. Created by the system and refined by carrier overrides.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.supplier import Supplier, User


class MatchType:
    EXACT_CODE = "exact_code"  # raw_code == match_pattern (case-insensitive)
    REGEX_PATTERN = "regex_pattern"  # re.search(match_pattern, raw_description)
    KEYWORD_SET = "keyword_set"  # all keywords in match_pattern present in description


class ConfirmedBy:
    SYSTEM = "SYSTEM"  # auto-generated from keyword heuristics
    CARRIER_CONFIRMED = (
        "CARRIER_CONFIRMED"  # carrier reviewed and accepted system mapping
    )
    CARRIER_OVERRIDE = "CARRIER_OVERRIDE"  # carrier corrected a wrong system mapping


class MappingRule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    A single mapping rule: pattern → taxonomy code.

    Rules are evaluated in priority order:
      1. EXACT_CODE rules (highest specificity)
      2. REGEX_PATTERN rules (ordered by confidence_weight DESC)
      3. KEYWORD_SET rules (ordered by confidence_weight DESC)

    Scope:
      supplier_id = NULL  →  global (applies to all suppliers)
      supplier_id = X     →  supplier-specific (takes priority over global)

    Versioning:
      When a carrier overrides a rule, the old rule gets effective_to = now()
      and a new rule is created with supersedes_rule_id pointing to the old one.
      This creates an immutable audit trail of how mappings evolved.
    """

    __tablename__ = "mapping_rules"

    # ── Scope ─────────────────────────────────────────────────────────────────
    supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="NULL = global rule; set = supplier-specific (higher priority)",
    )

    # ── Match criteria ────────────────────────────────────────────────────────
    match_type: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="exact_code | regex_pattern | keyword_set"
    )
    match_pattern: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment=(
            "For exact_code: the supplier code string. "
            "For regex_pattern: a Python regex. "
            "For keyword_set: comma-separated keywords (all must be present)."
        ),
    )

    # ── Classification output ─────────────────────────────────────────────────
    taxonomy_code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("taxonomy_items.code", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    billing_component: Mapped[str] = mapped_column(String(32), nullable=False)

    # ── Confidence ────────────────────────────────────────────────────────────
    confidence_weight: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.5,
        comment="0.0–1.0; used to rank competing rules. Carrier-confirmed = 1.0",
    )
    confidence_label: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default="MEDIUM",
        comment="HIGH | MEDIUM | LOW — derived from confirmed_by + match_type",
    )

    # ── Provenance ────────────────────────────────────────────────────────────
    confirmed_by: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ConfirmedBy.SYSTEM,
        comment="SYSTEM | CARRIER_CONFIRMED | CARRIER_OVERRIDE",
    )
    confirmed_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Versioning ────────────────────────────────────────────────────────────
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    effective_to: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="NULL = currently active; set when superseded",
    )
    supersedes_rule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mapping_rules.id", ondelete="SET NULL"),
        nullable=True,
        comment="Points to the previous version of this rule (linked-list chain)",
    )

    # ── Optional context ──────────────────────────────────────────────────────
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    supplier: Mapped[Optional["Supplier"]] = relationship(
        "Supplier", back_populates="mapping_rules"
    )
    confirmed_by_user: Mapped[Optional["User"]] = relationship("User")
    superseded_rule: Mapped[Optional["MappingRule"]] = relationship(
        "MappingRule",
        remote_side="MappingRule.id",
        foreign_keys=[supersedes_rule_id],
    )

    def __repr__(self) -> str:
        return (
            f"<MappingRule match_type={self.match_type!r} "
            f"pattern={self.match_pattern!r} → {self.taxonomy_code!r}>"
        )
