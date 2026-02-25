"""
Guideline Validation Engine.

Evaluates structured rules derived from contract narrative language.
Each Guideline has a rule_type and rule_params (JSONB).

Supported rule types (v1):
  max_units           — quantity must not exceed a maximum
  requires_auth       — line must have an auth number attached (stub in v1)
  billing_increment   — quantity must be in allowed increments (e.g. 0.25 hr)
  bundling_prohibition — listed components must not appear on the same invoice
  cap_amount          — billed amount must not exceed a dollar cap

Narrative source text is surfaced in every exception message for auditability.

Design note: This engine is deterministic and has no side effects.
ML-assisted rule extraction (v2) would generate Guideline rows that this
engine would then evaluate — no changes to this file needed.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional

from app.models.supplier import Guideline
from app.models.invoice import LineItem
from app.models.validation import (
    ValidationType,
    ValidationStatus,
    ValidationSeverity,
    RequiredAction,
)

logger = logging.getLogger(__name__)


@dataclass
class GuidelineValidationResult:
    """Maps to ValidationResult model fields."""

    validation_type: str = ValidationType.GUIDELINE
    rate_card_id: Optional[str] = None
    guideline_id: Optional[str] = None
    status: str = ValidationStatus.PASS
    severity: str = ValidationSeverity.ERROR
    message: str = ""
    expected_value: Optional[str] = None
    actual_value: Optional[str] = None
    required_action: str = RequiredAction.NONE


class GuidelineValidator:
    """
    Evaluates all applicable guidelines for a single line item.

    Usage:
        validator = GuidelineValidator()
        results = validator.validate(line_item, guidelines)
    """

    def validate(
        self, line_item: LineItem, guidelines: list[Guideline]
    ) -> list[GuidelineValidationResult]:
        """
        Run all applicable guideline checks for a line item.
        Returns a list of results (one per applicable guideline).
        """
        results: list[GuidelineValidationResult] = []

        for guideline in guidelines:
            if not self._applies_to(guideline, line_item):
                continue
            result = self._evaluate(guideline, line_item)
            if result is not None:
                results.append(result)

        return results

    # ── Applicability filter ──────────────────────────────────────────────────

    def _applies_to(self, guideline: Guideline, line_item: LineItem) -> bool:
        """
        Return True if this guideline applies to the given line item.
        Matching logic: taxonomy_code match (most specific) OR domain match.
        """
        if guideline.taxonomy_code is not None:
            return guideline.taxonomy_code == line_item.taxonomy_code
        if guideline.domain is not None and line_item.taxonomy_code:
            item_domain = line_item.taxonomy_code.split(".")[0]
            return guideline.domain == item_domain
        # Global guideline (no taxonomy_code, no domain) — applies to all
        return True

    # ── Rule evaluation dispatch ──────────────────────────────────────────────

    def _evaluate(
        self, guideline: Guideline, line_item: LineItem
    ) -> Optional[GuidelineValidationResult]:
        """Dispatch to the correct rule handler. Returns None if PASS."""
        rule_type = guideline.rule_type
        params = guideline.rule_params or {}

        try:
            if rule_type == "max_units":
                return self._check_max_units(guideline, line_item, params)
            elif rule_type == "requires_auth":
                return self._check_requires_auth(guideline, line_item, params)
            elif rule_type == "billing_increment":
                return self._check_billing_increment(guideline, line_item, params)
            elif rule_type == "bundling_prohibition":
                return self._check_bundling_prohibition(guideline, line_item, params)
            elif rule_type == "cap_amount":
                return self._check_cap_amount(guideline, line_item, params)
            else:
                logger.warning(
                    "Unknown guideline rule_type %r for guideline %s",
                    rule_type,
                    guideline.id,
                )
                return None
        except Exception as exc:
            logger.error(
                "Error evaluating guideline %s (type=%r): %s",
                guideline.id,
                rule_type,
                exc,
                exc_info=True,
            )
            return GuidelineValidationResult(
                guideline_id=str(guideline.id),
                status=ValidationStatus.WARNING,
                severity=ValidationSeverity.WARNING,
                message=f"Guideline check could not be evaluated (rule_type={rule_type!r}). "
                f"Carrier review required.",
                required_action=RequiredAction.NONE,
            )

    # ── Rule handlers ─────────────────────────────────────────────────────────

    def _check_max_units(
        self, guideline: Guideline, line_item: LineItem, params: dict
    ) -> Optional[GuidelineValidationResult]:
        """
        params: {"max": <number>, "period": "per_claim" | "per_invoice" | "per_day"}
        """
        try:
            max_units = Decimal(str(params["max"]))
        except (KeyError, InvalidOperation):
            logger.warning(
                "Guideline %s: invalid max_units params: %s", guideline.id, params
            )
            return None

        period = params.get("period", "per_claim")

        if line_item.raw_quantity > max_units:
            narrative = self._narrative_cite(guideline)
            return GuidelineValidationResult(
                guideline_id=str(guideline.id),
                status=ValidationStatus.FAIL,
                severity=guideline.severity,
                message=(
                    f"Quantity {line_item.raw_quantity} {line_item.raw_unit or 'units'} "
                    f"exceeds contract guideline maximum of {max_units} {period}. "
                    f"{narrative}"
                ),
                expected_value=f"max {max_units} ({period})",
                actual_value=str(line_item.raw_quantity),
                required_action=RequiredAction.ACCEPT_REDUCTION
                if guideline.severity == ValidationSeverity.ERROR
                else RequiredAction.NONE,
            )
        return None  # PASS

    def _check_requires_auth(
        self, guideline: Guideline, line_item: LineItem, params: dict
    ) -> Optional[GuidelineValidationResult]:
        """
        params: {"required": true, "auth_field": "auth_number"}

        v1: We don't have an auth number field on LineItem yet.
        Flag as WARNING for carrier review rather than hard ERROR.
        A supporting document upload satisfies this requirement.

        v2: Add auth_number to LineItem; change to ERROR when field exists.
        """
        if not params.get("required", True):
            return None

        narrative = self._narrative_cite(guideline)
        return GuidelineValidationResult(
            guideline_id=str(guideline.id),
            status=ValidationStatus.WARNING,
            severity=ValidationSeverity.WARNING,
            message=(
                f"This service may require prior authorization per contract guidelines. "
                f"Please attach authorization documentation if applicable. "
                f"{narrative}"
            ),
            required_action=RequiredAction.ATTACH_DOC,
        )

    def _check_billing_increment(
        self, guideline: Guideline, line_item: LineItem, params: dict
    ) -> Optional[GuidelineValidationResult]:
        """
        params: {"min_increment": 0.25, "unit": "hour"}
        Quantity must be a multiple of min_increment.
        e.g. 1.3 hours is invalid if billing increment is 0.25; 1.25 is valid.
        """
        try:
            min_increment = Decimal(str(params["min_increment"]))
        except (KeyError, InvalidOperation):
            return None

        qty = line_item.raw_quantity
        remainder = qty % min_increment

        if remainder > Decimal("0.001"):  # floating point tolerance
            unit_label = params.get("unit", line_item.raw_unit or "units")
            narrative = self._narrative_cite(guideline)
            return GuidelineValidationResult(
                guideline_id=str(guideline.id),
                status=ValidationStatus.FAIL,
                severity=guideline.severity,
                message=(
                    f"Quantity {qty} {unit_label} is not a valid billing increment. "
                    f"Contract requires billing in increments of {min_increment} {unit_label}. "
                    f"Please round to the nearest {min_increment} {unit_label}. "
                    f"{narrative}"
                ),
                expected_value=f"multiple of {min_increment} {unit_label}",
                actual_value=f"{qty} {unit_label}",
                required_action=RequiredAction.REUPLOAD,
            )
        return None  # PASS

    def _check_bundling_prohibition(
        self, guideline: Guideline, line_item: LineItem, params: dict
    ) -> Optional[GuidelineValidationResult]:
        """
        params: {"prohibited_components": ["TRAVEL_TRANSPORT", "MILEAGE"]}
        If this line item's billing_component is in the prohibited list, flag it.
        """
        prohibited = params.get("prohibited_components", [])
        if line_item.billing_component in prohibited:
            narrative = self._narrative_cite(guideline)
            return GuidelineValidationResult(
                guideline_id=str(guideline.id),
                status=ValidationStatus.FAIL,
                severity=guideline.severity,
                message=(
                    f"Billing component '{line_item.billing_component}' is not separately "
                    f"billable under this contract. "
                    f"Prohibited components: {', '.join(prohibited)}. "
                    f"{narrative}"
                ),
                expected_value="Not separately billable",
                actual_value=line_item.billing_component,
                required_action=RequiredAction.REUPLOAD,
            )
        return None  # PASS

    def _check_cap_amount(
        self, guideline: Guideline, line_item: LineItem, params: dict
    ) -> Optional[GuidelineValidationResult]:
        """
        params: {"max_amount": 500.00}
        Line billed amount must not exceed the cap.
        """
        try:
            max_amount = Decimal(str(params["max_amount"]))
        except (KeyError, InvalidOperation):
            return None

        if line_item.raw_amount > max_amount:
            narrative = self._narrative_cite(guideline)
            return GuidelineValidationResult(
                guideline_id=str(guideline.id),
                status=ValidationStatus.FAIL,
                severity=guideline.severity,
                message=(
                    f"Billed amount ${line_item.raw_amount} exceeds contract cap of ${max_amount}. "
                    f"Payment will be limited to ${max_amount}. "
                    f"{narrative}"
                ),
                expected_value=f"max ${max_amount}",
                actual_value=f"${line_item.raw_amount}",
                required_action=RequiredAction.ACCEPT_REDUCTION,
            )
        return None  # PASS

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _narrative_cite(guideline: Guideline) -> str:
        """Format the contract narrative source as an inline citation."""
        if guideline.narrative_source:
            return f'Contract reference: "{guideline.narrative_source}"'
        return ""
