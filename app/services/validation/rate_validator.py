"""
Rate Validation Engine — deterministic, fully testable.

For each LineItem, looks up the applicable RateCard and checks:
  1. Contract is active and currently effective (checked once in the pipeline)
  2. Taxonomy code domain is within the contract's contracted scope
     — inferred from the domains of all rate cards on the contract.
     If a contract has only ENG rate cards, an LA line is OUT_OF_SCOPE.
  3. Expected amount = quantity × contracted_rate  (flat)
                    OR tiered band calculation      (tiered)
  4. Billed amount vs expected amount (with configurable tolerance)
  5. Max units per rate card (if set)
  6. Bundled charges violation (if rate card is_all_inclusive)

Tiered rate calculation:
  Bands are applied sequentially from lowest from_unit to highest.
  to_unit: null means "all remaining units at this rate".
  Example: [{from_unit:1, to_unit:20, rate:"0.85"},
            {from_unit:21, to_unit:null, rate:"0.55"}]
  For 50 units → (20 × $0.85) + (30 × $0.55) = $17.00 + $16.50 = $33.50

Missing rate card decision tree:
  • No taxonomy code               → REQUEST_RECLASSIFICATION (supplier action)
  • Domain not in contract scope   → OUT_OF_SCOPE (carrier investigates/denies)
  • Domain OK, no rate for code    → ESTABLISH_CONTRACT_RATE (carrier adds rate)

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

        # ── Check: taxonomy domain within contracted scope ────────────────────
        # Infer contracted domains from the taxonomy codes of all rate cards on
        # this contract. A domain is the first segment of a taxonomy code
        # (e.g. "ENG" from "ENG.STRUCT.L1", "LA" from "LA.ROOF_INSPECT.PROF_FEE").
        # If the contract has rate cards but none match the line item's domain,
        # the supplier is billing outside their contracted scope.
        line_domain = line_item.taxonomy_code.split(".")[0]
        contracted_domains = {
            rc.taxonomy_code.split(".")[0]
            for rc in contract.rate_cards
            if rc.taxonomy_code
        }

        if contracted_domains and line_domain not in contracted_domains:
            results.append(
                RateValidationResult(
                    status=ValidationStatus.FAIL,
                    severity=ValidationSeverity.ERROR,
                    message=(
                        f"Service '{line_item.taxonomy_code}' (domain: {line_domain}) "
                        f"is not within the contracted scope of '{contract.name}'. "
                        f"This contract covers: {', '.join(sorted(contracted_domains))}. "
                        f"Supplier should only bill for services within their executed contract."
                    ),
                    required_action=RequiredAction.OUT_OF_SCOPE,
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
                        f"No contracted rate found for '{line_item.taxonomy_code}' "
                        f"under contract '{contract.name}'. "
                        f"This service domain ({line_domain}) is within scope — "
                        f"add a rate card for this specific code in the Contracts admin."
                    ),
                    required_action=RequiredAction.ESTABLISH_CONTRACT_RATE,
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

    def _calculate_tiered(self, tiers: list, quantity: Decimal) -> Decimal:
        """
        Apply tiered band rates to a quantity.
        Bands must be contiguous but can have gaps — remaining units past the
        last defined band are billed at the last band's rate (open-ended tier).
        """
        total = Decimal("0")
        remaining = quantity
        sorted_tiers = sorted(tiers, key=lambda t: t["from_unit"])

        for i, tier in enumerate(sorted_tiers):
            if remaining <= 0:
                break
            from_u = Decimal(str(tier["from_unit"]))
            to_u = (
                Decimal(str(tier["to_unit"]))
                if tier.get("to_unit") is not None
                else None
            )
            tier_rate = Decimal(str(tier["rate"]))

            if to_u is not None:
                band_size = to_u - from_u + 1
            else:
                band_size = remaining  # open-ended — consume all remaining

            used = min(remaining, band_size)
            total += used * tier_rate
            remaining -= used

        return total.quantize(Decimal("0.01"))

    def _calculate_expected(self, line_item: LineItem, rate_card: RateCard) -> Decimal:
        """
        Calculate the expected amount for a line item based on rate card type.
        Dispatches to tiered or flat calculation.
        """
        if rate_card.rate_type == "tiered" and rate_card.rate_tiers:
            return self._calculate_tiered(rate_card.rate_tiers, line_item.raw_quantity)
        # flat / hourly / mileage / per_diem — all use quantity × single rate
        return (line_item.raw_quantity * rate_card.contracted_rate).quantize(
            Decimal("0.01")
        )

    def _check_amount(
        self, line_item: LineItem, rate_card: RateCard
    ) -> RateValidationResult:
        """Check billed amount against expected amount (flat or tiered)."""
        expected = self._calculate_expected(line_item, rate_card)
        billed = line_item.raw_amount
        diff = billed - expected
        is_tiered = rate_card.rate_type == "tiered" and rate_card.rate_tiers
        units = line_item.raw_unit or "units"
        tier_count = len(rate_card.rate_tiers) if is_tiered else 0

        if abs(diff) <= AMOUNT_TOLERANCE:
            if is_tiered:
                calc_desc = (
                    f"tiered rate applied to {line_item.raw_quantity} {units} "
                    f"({tier_count} bands) = ${expected}"
                )
            else:
                calc_desc = f"${rate_card.contracted_rate} × {line_item.raw_quantity} {units} = ${expected}"
            return RateValidationResult(
                rate_card_id=str(rate_card.id),
                status=ValidationStatus.PASS,
                severity=ValidationSeverity.INFO,
                message=f"Amount validated: billed ${billed} matches contracted rate ({calc_desc}).",
                expected_value=f"${expected}",
                actual_value=f"${billed}",
                required_action=RequiredAction.NONE,
            )
        elif diff > AMOUNT_TOLERANCE:
            # Overbilled
            overage = diff
            if is_tiered:
                calc_desc = (
                    f"tiered rate ({tier_count} bands) applied to "
                    f"{line_item.raw_quantity} {units} = ${expected}"
                )
            else:
                calc_desc = (
                    f"${rate_card.contracted_rate} × "
                    f"{line_item.raw_quantity} {units} = ${expected}"
                )
            return RateValidationResult(
                rate_card_id=str(rate_card.id),
                status=ValidationStatus.FAIL,
                severity=ValidationSeverity.ERROR,
                message=(
                    f"Billed amount ${billed} exceeds contracted rate. "
                    f"Contracted rate: {calc_desc}. "
                    f"Overage: ${overage}. "
                    f"Payment will be limited to ${expected}."
                ),
                expected_value=f"${expected}",
                actual_value=f"${billed}",
                required_action=RequiredAction.ACCEPT_REDUCTION,
            )
        else:
            # Underbilled (unusual but not an error — warn for carrier visibility)
            if is_tiered:
                calc_desc = (
                    f"tiered rate ({tier_count} bands) × "
                    f"{line_item.raw_quantity} {units} = ${expected}"
                )
            else:
                calc_desc = f"${rate_card.contracted_rate} × {line_item.raw_quantity} {units} = ${expected}"
            return RateValidationResult(
                rate_card_id=str(rate_card.id),
                status=ValidationStatus.WARNING,
                severity=ValidationSeverity.WARNING,
                message=(
                    f"Billed amount ${billed} is less than contracted rate "
                    f"({calc_desc}). Amount will be paid as billed."
                ),
                expected_value=f"${expected}",
                actual_value=f"${billed}",
                required_action=RequiredAction.NONE,
            )

    def _check_max_units(
        self, line_item: LineItem, rate_card: RateCard
    ) -> RateValidationResult:
        """Check that billed quantity does not exceed the rate card max."""
        units = line_item.raw_unit or "units"
        if line_item.raw_quantity > rate_card.max_units:
            # Calculate capped expected amount using the same rate logic
            capped_line = type(
                "_Stub",
                (),
                {
                    "raw_quantity": rate_card.max_units,
                    "raw_unit": line_item.raw_unit,
                    "service_date": line_item.service_date,
                    "taxonomy_code": line_item.taxonomy_code,
                    "billing_component": getattr(line_item, "billing_component", None),
                },
            )()
            capped_amount = self._calculate_expected(capped_line, rate_card)
            return RateValidationResult(
                rate_card_id=str(rate_card.id),
                status=ValidationStatus.FAIL,
                severity=ValidationSeverity.ERROR,
                message=(
                    f"Quantity {line_item.raw_quantity} {units} "
                    f"exceeds contract maximum of {rate_card.max_units} "
                    f"for {line_item.taxonomy_code}. "
                    f"Payment will be limited to {rate_card.max_units} {units} = ${capped_amount}."
                ),
                expected_value=f"max {rate_card.max_units} {units}",
                actual_value=f"{line_item.raw_quantity} {units}",
                required_action=RequiredAction.ACCEPT_REDUCTION,
            )
        return RateValidationResult(
            rate_card_id=str(rate_card.id),
            status=ValidationStatus.PASS,
            severity=ValidationSeverity.INFO,
            message=f"Quantity {line_item.raw_quantity} {units} within contract maximum of {rate_card.max_units}.",
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
