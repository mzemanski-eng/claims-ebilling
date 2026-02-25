"""
AuditEvent — the immutable audit log.

CRITICAL DESIGN RULE:
  This table is append-only. No UPDATE or DELETE statements should ever
  be issued against it. SQLAlchemy relationships deliberately omit
  cascade="all, delete-orphan" for this reason.

  The DB-level server_default on created_at (not application code) ensures
  the timestamp is authoritative and cannot be spoofed.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ActorType:
    SYSTEM = "SYSTEM"
    SUPPLIER = "SUPPLIER"
    CARRIER = "CARRIER"


class AuditEvent(Base):
    """
    Immutable record of every meaningful state change in the system.

    entity_type + entity_id: the thing that changed
    event_type: what happened (past-tense verb, e.g. "invoice.submitted")
    actor_*: who caused it
    payload: full JSON snapshot of relevant state — designed so you can
             reconstruct history without joining across versioned tables.

    Note: no UUIDPrimaryKeyMixin (we use a simple server-generated UUID here
    to keep the insert as simple as possible and avoid any application-level
    UUID generation that could fail silently).
    """

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    # ── What changed ─────────────────────────────────────────────────────────
    entity_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="invoice | line_item | mapping_rule | exception | supplier | contract | ...",
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
        comment=(
            "Past-tense dot-namespaced: invoice.submitted, line_item.classified, "
            "mapping_rule.overridden, exception.opened, exception.resolved, ..."
        ),
    )

    # ── Who caused it ────────────────────────────────────────────────────────
    actor_type: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="SYSTEM | SUPPLIER | CARRIER"
    )
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="User.id if human-triggered; NULL for system events",
    )

    # ── State snapshot ────────────────────────────────────────────────────────
    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Full snapshot of relevant entity state at the time of the event",
    )

    # ── Timestamp (server-authoritative — never set by application code) ──────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<AuditEvent event={self.event_type!r} "
            f"entity={self.entity_type}:{self.entity_id} "
            f"actor={self.actor_type}>"
        )
