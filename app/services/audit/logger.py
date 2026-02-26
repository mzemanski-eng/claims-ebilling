"""
Audit Logger — the only way to write AuditEvent rows.

Design rules enforced here:
  - created_at is always server-set (DB default) — never passed by application
  - Payload is always serialized to a plain dict (no ORM objects)
  - All writes go through log_event() — no direct AuditEvent instantiation elsewhere
  - This module never raises — audit failures are logged but do not block the main flow
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.audit import AuditEvent, ActorType

logger = logging.getLogger(__name__)


def log_event(
    db: Session,
    entity_type: str,
    entity_id: uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
    actor_type: str = ActorType.SYSTEM,
    actor_id: Optional[uuid.UUID] = None,
    flush: bool = True,
) -> None:
    """
    Write an immutable audit event to the database.

    Args:
        db:          SQLAlchemy session (caller manages transaction)
        entity_type: The type of entity that changed (e.g. "invoice", "line_item")
        entity_id:   UUID of the entity
        event_type:  Past-tense event name (e.g. "invoice.submitted", "mapping_rule.overridden")
        payload:     Dict snapshot of relevant state — JSON-serializable
        actor_type:  SYSTEM | SUPPLIER | CARRIER
        actor_id:    User.id if human-triggered; None for system events
        flush:       If True, flush to DB immediately (within the caller's transaction)

    Does not raise — exceptions are caught and logged as warnings.
    """
    try:
        event = AuditEvent(
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            payload=_safe_payload(payload),
            # created_at is intentionally NOT set here — let DB set it via server_default
        )
        db.add(event)
        if flush:
            db.flush()  # Assigns ID without committing the outer transaction
    except Exception as exc:
        logger.warning(
            "Failed to write audit event %r for %s:%s — %s",
            event_type,
            entity_type,
            entity_id,
            exc,
        )


def _safe_payload(payload: dict) -> dict:
    """
    Ensure payload is JSON-serializable.
    Converts common non-serializable types (UUID, datetime, Decimal) to strings.
    """
    import json
    from decimal import Decimal

    def default(obj: Any) -> Any:
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return str(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    # Round-trip through JSON to strip any non-serializable types
    return json.loads(json.dumps(payload, default=default))


# ── Convenience wrappers for common events ────────────────────────────────────


def log_invoice_submitted(
    db: Session, invoice, actor_id: Optional[uuid.UUID] = None
) -> None:
    log_event(
        db,
        "invoice",
        invoice.id,
        "invoice.submitted",
        payload={
            "invoice_number": invoice.invoice_number,
            "supplier_id": str(invoice.supplier_id),
            "contract_id": str(invoice.contract_id),
            "status": invoice.status,
            "version": invoice.current_version,
        },
        actor_type=ActorType.SUPPLIER,
        actor_id=actor_id,
    )


def log_invoice_status_changed(
    db: Session,
    invoice,
    from_status: str,
    to_status: str,
    actor_type: str = ActorType.SYSTEM,
    actor_id: Optional[uuid.UUID] = None,
) -> None:
    log_event(
        db,
        "invoice",
        invoice.id,
        "invoice.status_changed",
        payload={
            "from_status": from_status,
            "to_status": to_status,
            "invoice_number": invoice.invoice_number,
        },
        actor_type=actor_type,
        actor_id=actor_id,
    )


def log_line_item_classified(db: Session, line_item, classification_result) -> None:
    log_event(
        db,
        "line_item",
        line_item.id,
        "line_item.classified",
        payload={
            "taxonomy_code": line_item.taxonomy_code,
            "billing_component": line_item.billing_component,
            "mapping_confidence": line_item.mapping_confidence,
            "match_type": classification_result.match_type,
            "match_explanation": classification_result.match_explanation,
        },
        actor_type=ActorType.SYSTEM,
    )


def log_line_item_exception_opened(db: Session, line_item, validation_result) -> None:
    log_event(
        db,
        "line_item",
        line_item.id,
        "exception.opened",
        payload={
            "validation_type": validation_result.validation_type,
            "status": validation_result.status,
            "severity": validation_result.severity,
            "message": validation_result.message,
            "required_action": validation_result.required_action,
        },
        actor_type=ActorType.SYSTEM,
    )


def log_mapping_overridden(
    db: Session,
    mapping_rule,
    old_taxonomy_code: Optional[str],
    actor_id: uuid.UUID,
) -> None:
    log_event(
        db,
        "mapping_rule",
        mapping_rule.id,
        "mapping_rule.overridden",
        payload={
            "old_taxonomy_code": old_taxonomy_code,
            "new_taxonomy_code": mapping_rule.taxonomy_code,
            "match_pattern": mapping_rule.match_pattern,
            "match_type": mapping_rule.match_type,
            "scope": "supplier" if mapping_rule.supplier_id else "global",
        },
        actor_type=ActorType.CARRIER,
        actor_id=actor_id,
    )


def log_exception_resolved(
    db: Session,
    exception_record,
    actor_id: uuid.UUID,
    actor_type: str = ActorType.CARRIER,
) -> None:
    log_event(
        db,
        "exception",
        exception_record.id,
        "exception.resolved",
        payload={
            "line_item_id": str(exception_record.line_item_id),
            "resolution_action": exception_record.resolution_action,
            "resolution_notes": exception_record.resolution_notes,
        },
        actor_type=actor_type,
        actor_id=actor_id,
    )


def log_invoice_changes_requested(
    db: Session,
    invoice,
    carrier_notes: str,
    actor_id: uuid.UUID,
) -> None:
    """
    Carrier returns an invoice to the supplier with required changes.
    Carrier notes are stored in the immutable audit event payload only —
    no schema change is required and the notes are always recoverable.
    """
    log_event(
        db,
        "invoice",
        invoice.id,
        "invoice.changes_requested",
        payload={
            "invoice_number": invoice.invoice_number,
            "to_status": "REVIEW_REQUIRED",
            "carrier_notes": carrier_notes,
        },
        actor_type=ActorType.CARRIER,
        actor_id=actor_id,
    )
