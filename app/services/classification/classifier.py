"""
Classifier orchestrator.

Resolution order:
  1. Supplier-specific DB MappingRule (exact_code > regex > keyword)
  2. Global DB MappingRule (exact_code > regex > keyword)
  3. Built-in rule heuristics (rule_engine.py)
  4. UNRECOGNIZED

DB rules always beat built-in rules.
Supplier-specific DB rules always beat global DB rules.
Within each tier, rules are ranked by confidence_weight DESC.

ML hook (v2): insert between step 3 and 4.
  result = ml_model.classify(raw_description)
  if result.confidence_weight > threshold: return result
"""

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.mapping import MappingRule, MatchType, ConfirmedBy
from app.services.classification.rule_engine import (
    ClassificationResult,
    classify_with_builtin_rules,
)

logger = logging.getLogger(__name__)


class Classifier:
    def __init__(self, db: Session):
        self.db = db

    def classify(
        self,
        raw_description: str,
        raw_code: Optional[str] = None,
        supplier_id: Optional[uuid.UUID] = None,
    ) -> ClassificationResult:
        """
        Classify a raw line item.  Returns a ClassificationResult.
        Never raises — returns UNRECOGNIZED on total failure.
        """
        desc_lower = raw_description.lower().strip()
        code_lower = (raw_code or "").lower().strip()

        # ── Step 1 & 2: DB MappingRules ──────────────────────────────────────
        db_result = self._classify_from_db(desc_lower, code_lower, supplier_id)
        if db_result is not None:
            return db_result

        # ── Step 3: Built-in heuristics ───────────────────────────────────────
        return classify_with_builtin_rules(raw_description, raw_code)

    def _classify_from_db(
        self,
        desc_lower: str,
        code_lower: str,
        supplier_id: Optional[uuid.UUID],
    ) -> Optional[ClassificationResult]:
        """
        Query active MappingRules from DB and attempt to match.
        Returns the best match or None.
        """
        now = datetime.now(timezone.utc)

        # Load candidate rules: supplier-specific first, then global
        rules = (
            self.db.query(MappingRule)
            .filter(
                MappingRule.effective_to.is_(None) | (MappingRule.effective_to > now),
                MappingRule.supplier_id.in_(
                    [supplier_id, None] if supplier_id else [None]
                ),
            )
            .order_by(
                # Supplier-specific rules first
                MappingRule.supplier_id.is_(None).asc(),
                # Then by confidence weight desc
                MappingRule.confidence_weight.desc(),
            )
            .all()
        )

        best_weight = -1.0
        best_result: Optional[ClassificationResult] = None

        for rule in rules:
            matched, explanation = self._rule_matches(rule, desc_lower, code_lower)
            if matched and rule.confidence_weight > best_weight:
                best_weight = rule.confidence_weight
                best_result = ClassificationResult(
                    taxonomy_code=rule.taxonomy_code,
                    billing_component=rule.billing_component,
                    confidence=rule.confidence_label,
                    confidence_weight=rule.confidence_weight,
                    match_type=rule.match_type,
                    matched_rule_id=str(rule.id),
                    match_explanation=explanation,
                )

        return best_result

    def _rule_matches(
        self,
        rule: MappingRule,
        desc_lower: str,
        code_lower: str,
    ) -> tuple[bool, str]:
        """
        Test a MappingRule against the description/code.
        Returns (matched, explanation).
        """
        pattern = rule.match_pattern.lower().strip()

        if rule.match_type == MatchType.EXACT_CODE:
            if code_lower and code_lower == pattern:
                return True, f"Exact code match: {rule.match_pattern!r}"
            return False, ""

        elif rule.match_type == MatchType.REGEX_PATTERN:
            try:
                if re.search(pattern, desc_lower, re.IGNORECASE):
                    return True, f"Regex match: {rule.match_pattern!r}"
            except re.error:
                logger.warning("Invalid regex in MappingRule %s: %r", rule.id, pattern)
            return False, ""

        elif rule.match_type == MatchType.KEYWORD_SET:
            keywords = [k.strip() for k in pattern.split(",")]
            if all(kw in desc_lower for kw in keywords if kw):
                return True, f"Keyword set match: {rule.match_pattern!r}"
            return False, ""

        else:
            logger.warning("Unknown match_type %r in MappingRule %s", rule.match_type, rule.id)
            return False, ""
