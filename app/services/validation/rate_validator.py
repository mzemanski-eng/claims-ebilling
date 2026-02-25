"""
Rate Validation Engine — deterministic, fully testable.

For each LineItem, looks up the applicable RateCard and checks:
  1. Expected amount = quantity × contracted_rate
  2. Billed amount vs expected amount (with configurable tolerance)
  3. Max units per rate card (if set)
  4. Bundled charges violation (if rate card is_all_inclusive)

Returns a list of ValidationResult-shaped dicts (not ORM objects —
the worker persists these after all checks are complete).

Design principle: pure function, no DB writes. Accepts all inputs;
caller (worker) handles persistence. This makes it trivially testable.
"""

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from app.models.supplier import RateCard, Contract
from app.models.invoice import LineItem
from app.models.validation import (
    ValidationType,
    ValidationStatus,
    ValidationSeverity,
    RequiredAction,
)

logger = logging.getLogger(__name__)

# Tolerance for floating-point rounding (e.g. mileage × rate)
AMOUNT_TOLERANCE = Decimal("0.02")  # $0.02


@dataclass
class RateValidationResult:
    """
    Rate validation result — one per check per line item.
    Maps directly to ValidationResult model fields.
    """

    validation_type: str = ValidationType.RATE
    rate_card_id: Optional[str] = None
    guideline_id: Optional[str] = None
    status: str = ValidationStatus.PASS
    severity: str = ValidationSeverity.ERROR
    message: str = ""
    expected_value: Optional[str] = None
    actual_value: Optional[str] = None
    required_action: str = RequiredAction.NONE


class RateValidator:
    """
    Validates a line item's billed amount against the applicable rate card.

    Usage:
        validator = RateValidator(db)
        results = validator.validate(line_item, contract)
    """

    def __init__(self, db):
        self.db = db

    def validate(
        self, line_item: LineItem, contract: Contract
    ) -> list[RateValidationResult]:
        """
        Run all rate checks for a single line item.
        Returns a list of results (typically 1, but may be multiple for complex checks).
        """
        results: list[RateValidationResult] = []

        if line_item.taxonomy_code is None:
            # No taxonomy code — classification failed; rate validation cannot proceed
            results.append(
                RateValidationResult(
                    status=ValidationStatus.FAIL,
                    severity=ValidationSeverity.ERROR,
                    message=(
                        "Line item could not be classified to a taxonomy code. "
                        "Rate validation requires a valid service classification. "
                        "Please clarify the service description or request reclassification."
                    ),
                    required_action=RequiredAction.REQUEST_RECLASSIFICATION,
                )
            )
            return results

        # ── Look up applicable rate card ──────────────────────────────────────
        rate_card = self._find_rate_card(line_item, contract)

        if rate_card is None:
            results.append(
                RateValidationResult(
                    status=ValidationStatus.FAIL,
                    severity=ValidationSeverity.ERROR,
                    message=(
                        f"No contracted rate found for service "
                        f"'{line_item.taxonomy_code}' under contract '{contract.name}'. "
                        f"This service may not be covered or may require carrier pre-approval."
                    ),
                    required_action=RequiredAction.REQUEST_RECLASSIFICATION,
                )
            )
            return results

        # ── Check 1: Amount vs expected ───────────────────────────────────────
        amount_result = self._check_amount(line_item, rate_card)
        results.append(amount_result)

        # ── Check 2: Max units ────────────────────────────────────────────────
        if rate_card.max_units is not None:
            units_result = self._check_max_units(line_item, rate_card)
            results.append(units_result)

        # ── Check 3: Bundling prohibition ─────────────────────────────────────
        if rate_card.is_all_inclusive:
            bundling_result = self._check_bundling(line_item, rate_card)
            if bundling_result:
                results.append(bundling_result)

        return results

    # ── Private check methods ─────────────────────────────────────────────────

    def _find_rate_card(
        self, line_item: LineItem, contract: Contract
    ) -> Optional[RateCard]:
        """
        Find the most specific applicable rate card for a line item.
        Priority: state-specific > national, most-recent effective date.
        """
        service_date = line_item.service_date or date.today()

        candidates = (
            self.db.query(RateCard)
            .filter(
                RateCard.contract_id == contract.id,
                RateCard.taxonomy_code == line_item.taxonomy_code,
                RateCard.effective_from <= service_date,
                (RateCard.effective_to.is_(None))
                | (RateCard.effective_to >= service_date),
            )
            .order_by(RateCard.effective_from.desc())
            .all()
        )

        if not candidates:
            return None

        # Return the most recently effective rate card
        return candidates[0]

    def _check_amount(
        self, line_item: LineItem, rate_card: RateCard
    ) -> RateValidationResult:
        """Check billed amount against quantity × contracted rate."""
        expected = (line_item.raw_quantity * rate_card.contracted_rate).quantize(
            Decimal("0.01")
        )
        billed = line_item.raw_amount
        diff = billed - expected

        if abs(diff) <= AMOUNT_TOLERANCE:
            return RateValidationResult(
                rate_card_id=str(rate_card.id),
                status=ValidationStatus.PASS,
                severity=ValidationSeverity.INFO,
                message=(
                    f"Amount validated: billed ${billed} matches contracted rate "
                    f"${rate_card.contracted_rate} × {line_item.raw_quantity} units = ${expected}."
                ),
                expected_value=f"${expected}",
                actual_value=f"${billed}",
                required_action=RequiredAction.NONE,
            )
        elif diff > AMOUNT_TOLERANCE:
            # Overbilled
            overage = diff
            return RateValidationResult(
                rate_card_id=str(rate_card.id),
                status=ValidationStatus.FAIL,
                severity=ValidationSeverity.ERROR,
                message=(
                    f"Billed amount ${billed} exceeds contracted rate. "
                    f"Contracted rate: ${rate_card.contracted_rate} × "
                    f"{line_item.raw_quantity} {line_item.raw_unit or 'units'} = ${expected}. "
                    f"Overage: ${overage}. "
                    f"Payment will be limited to ${expected}."
                ),
                expected_value=f"${expected}",
                actual_value=f"${billed}",
                required_action=RequiredAction.ACCEPT_REDUCTION,
            )
        else:
            # Underbilled (unusual but not an error — warn for carrier visibility)
            return RateValidationResult(
                rate_card_id=str(rate_card.id),
                status=ValidationStatus.WARNING,
                severity=ValidationSeverity.WARNING,
                message=(
                    f"Billed amount ${billed} is less than contracted rate "
                    f"(${rate_card.contracted_rate} × {line_item.raw_quantity} = ${expected}). "
                    f"Amount will be paid as billed."
                ),
                expected_value=f"${expected}",
                actual_value=f"${billed}",
                required_action=RequiredAction.NONE,
            )

    def _check_max_units(
        self, line_item: LineItem, rate_card: RateCard
    ) -> RateValidationResult:
        """Check that billed quantity does not exceed the rate card max."""
        if line_item.raw_quantity > rate_card.max_units:
            return RateValidationResult(
                rate_card_id=str(rate_card.id),
                status=ValidationStatus.FAIL,
                severity=ValidationSeverity.ERROR,
                message=(
                    f"Quantity {line_item.raw_quantity} {line_item.raw_unit or 'units'} "
                    f"exceeds contract maximum of {rate_card.max_units} "
                    f"for {line_item.taxonomy_code}. "
                    f"Payment will be limited to {rate_card.max_units} units × "
                    f"${rate_card.contracted_rate}."
                ),
                expected_value=f"max {rate_card.max_units} units",
                actual_value=f"{line_item.raw_quantity} units",
                required_action=RequiredAction.ACCEPT_REDUCTION,
            )
        return RateValidationResult(
            rate_card_id=str(rate_card.id),
            status=ValidationStatus.PASS,
            severity=ValidationSeverity.INFO,
            message=f"Quantity {line_item.raw_quantity} within contract maximum of {rate_card.max_units}.",
            required_action=RequiredAction.NONE,
        )

    def _check_bundling(
        self, line_item: LineItem, rate_card: RateCard
    ) -> Optional[RateValidationResult]:
        """
        If rate card is all-inclusive, flag travel/mileage/expense components
        that should not be billed separately.
        """
        travel_components = {
            "TRAVEL_TRANSPORT",
            "TRAVEL_LODGING",
            "TRAVEL_MEALS",
            "MILEAGE",
        }
        if line_item.billing_component in travel_components:
            return RateValidationResult(
                rate_card_id=str(rate_card.id),
                status=ValidationStatus.FAIL,
                severity=ValidationSeverity.ERROR,
                message=(
                    f"The contracted rate for {line_item.taxonomy_code.split('.')[0]} services "
                    f"is all-inclusive (rate card: {rate_card.contracted_rate}). "
                    f"Travel and expense charges ({line_item.billing_component}) "
                    f"must not be billed separately. "
                    f"This line will not be approved."
                ),
                expected_value="Not separately billable (all-inclusive rate)",
                actual_value=f"${line_item.raw_amount} ({line_item.billing_component})",
                required_action=RequiredAction.REUPLOAD,
            )
        return None
