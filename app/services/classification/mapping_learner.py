"""
mapping_learner — write confirmed classifications back into the MappingRule corpus.

Every time the pipeline auto-resolves a classification exception (HIGH/MEDIUM AI
confidence) or a carrier explicitly corrects a mapping, this module creates (or
versions) a MappingRule so the classifier can use it on the next invoice without
hitting the AI call again.

The corpus is the `mapping_rules` table itself — `confirmed_by = SYSTEM` rows are
written here; `confirmed_by = CARRIER_OVERRIDE` rows come from the manual override
endpoint. The Classifier already queries MappingRule first (before the 390 built-in
rules), so every row added here is immediately live.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy.orm import Session

from app.models.invoice import Invoice, LineItem
from app.models.mapping import MatchType, MappingRule

logger = logging.getLogger(__name__)


def record_confirmed_mapping(
    db: Session,
    line_item: LineItem,
    taxonomy_code: str,
    billing_component: str,
    source: str,
    user_id: Optional[uuid.UUID] = None,
    scope: str = "this_supplier",
    notes: Optional[str] = None,
) -> Optional[MappingRule]:
    """
    Upsert a MappingRule from a confirmed classification.

    Args:
        db:               Active SQLAlchemy session.
        line_item:        The classified line item (provides raw_description + invoice FK).
        taxonomy_code:    Confirmed taxonomy code to map to.
        billing_component: Confirmed billing component.
        source:           ConfirmedBy constant — SYSTEM, CARRIER_CONFIRMED, or CARRIER_OVERRIDE.
        user_id:          UUID of the carrier user who confirmed, or None for system actions.
        scope:            "this_supplier" (supplier-specific rule) or "global" (all suppliers).
        notes:            Optional free-text note stored on the rule.

    Returns:
        The newly created MappingRule, or None if skipped/failed.

    Notes:
        - Always non-blocking: any exception is logged as a warning, not re-raised.
        - If an active rule already exists for the same pattern + scope, it is expired
          (effective_to = now()) and the new rule supersedes it (versioning chain).
        - Uses KEYWORD_SET match type with the raw_description as the pattern, matching
          the existing carrier-override convention in override_mapping().
    """
    try:
        if not taxonomy_code or not billing_component:
            logger.warning(
                "mapping_learner: skipping write-back for line %s — "
                "taxonomy_code or billing_component is empty",
                line_item.id,
            )
            return None

        # Resolve supplier_id based on scope
        supplier_id: Optional[uuid.UUID] = None
        if scope == "this_supplier":
            invoice = db.get(Invoice, line_item.invoice_id)
            supplier_id = invoice.supplier_id if invoice else None

        now = datetime.now(timezone.utc)

        # Expire any existing active rule for this pattern + scope
        existing = (
            db.query(MappingRule)
            .filter(
                MappingRule.match_pattern == line_item.raw_description,
                MappingRule.match_type == MatchType.KEYWORD_SET,
                MappingRule.effective_to.is_(None),
                MappingRule.supplier_id == supplier_id,
            )
            .first()
        )
        if existing:
            existing.effective_to = now
            db.flush()

        new_rule = MappingRule(
            supplier_id=supplier_id,
            match_type=MatchType.KEYWORD_SET,
            match_pattern=line_item.raw_description,
            taxonomy_code=taxonomy_code,
            billing_component=billing_component,
            confidence_weight=1.0,
            confidence_label="HIGH",
            confirmed_by=source,
            confirmed_by_user_id=user_id,
            confirmed_at=now,
            effective_from=now,
            supersedes_rule_id=existing.id if existing else None,
            version=(existing.version + 1) if existing else 1,
            notes=notes,
        )
        db.add(new_rule)
        db.flush()

        logger.info(
            "mapping_learner: wrote %s rule for '%s' → %s (v%d, source=%s)",
            scope,
            line_item.raw_description[:60],
            taxonomy_code,
            new_rule.version,
            source,
        )
        return new_rule

    except Exception as exc:
        logger.warning(
            "mapping_learner: failed to write MappingRule for line %s: %s",
            line_item.id,
            exc,
        )
        return None
