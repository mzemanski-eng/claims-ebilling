"""
Guideline Validation Engine.

Evaluates structured rules derived from contract narrative language.
Each Guideline has a rule_type and rule_params (JSONB).

Supported rule types:
  max_units               — quantity must not exceed a maximum
  requires_auth           — line must have an auth number attached (stub in v1)
  billing_increment       — quantity must be in allowed increments (e.g. 0.1 hr)
  bundling_prohibition    — listed billing components must not appear on the invoice
  cap_amount              — billed amount must not exceed a dollar cap
  max_pct_of_invoice      — named line(s) total must not exceed X% of invoice
                            (or domain) total.  Invoice-level check — evaluated
                            separately via validate_invoice_percentages(); skipped
                            during per-line validate().
  invoice_codes_exclusive — at most one code from a mutually exclusive set may appear
                            on the same invoice (e.g. LA service hierarchy: only one
                            of Harness Inspection / Roof Inspection / Ladder Access
                            per visit).  Invoice-level check — evaluated separately
                            via validate_invoice_exclusivity(); skipped during
                            per-line validate().

Rule params for max_pct_of_invoice:
  {
    "max_pct":            5.0,            # % threshold (0–100)
    "basis":              "amount",       # "amount" (dollars) | "quantity" (hrs)
    "description":        "Admin...",     # label that appears in exception message
    # Numerator targeting — use one of:
    "applies_to_codes":   ["ENG.AOS.L6"], # explicit taxonomy code list  OR
    "applies_to_suffix":  ".L1",          # match by code suffix
    "applies_to_domain":  "ENG",          # required when using applies_to_suffix
    # Denominator filter (optional):
    "denominator_domain": "ENG",          # omit / null = all invoice lines
  }

Rule params for invoice_codes_exclusive:
  {
    "exclusive_codes":  ["LA.ROOF_INSPECT_HARNESS.FLAT_FEE",
                         "LA.ROOF_INSPECT.FLAT_FEE",
                         "LA.LADDER_ACCESS.FLAT_FEE"],
    "description":      "primary ladder/roof service",  # label in exception message
  }

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
        Run all applicable guideline checks for a single line item.
        Returns a list of results (one per applicable guideline).

        NOTE: max_pct_of_invoice and invoice_codes_exclusive guidelines are
        intentionally excluded here — they need the full invoice context and
        are handled by validate_invoice_percentages() and
        validate_invoice_exclusivity() after all lines are processed.
        """
        results: list[GuidelineValidationResult] = []

        _INVOICE_LEVEL_TYPES = {"max_pct_of_invoice", "invoice_codes_exclusive"}

        for guideline in guidelines:
            if guideline.rule_type in _INVOICE_LEVEL_TYPES:
                continue  # Invoice-level check — handled separately
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

    # ── Invoice-level code exclusivity checks ────────────────────────────────

    def validate_invoice_exclusivity(
        self,
        all_lines: list[LineItem],
        guidelines: list[Guideline],
    ) -> list[tuple[LineItem, "GuidelineValidationResult"]]:
        """
        Evaluate all invoice_codes_exclusive guidelines against the full line list.

        Returns (anchor_line, result) tuples for every firing guideline.
        The anchor_line is the first conflicting line found so the caller can
        attach a ValidationResult + ExceptionRecord to an existing line.

        Called from the pipeline AFTER the per-line loop is complete.
        """
        output: list[tuple[LineItem, GuidelineValidationResult]] = []

        excl_guidelines = [
            g
            for g in guidelines
            if g.rule_type == "invoice_codes_exclusive" and g.is_active
        ]
        if not excl_guidelines or not all_lines:
            return output

        for guideline in excl_guidelines:
            params = guideline.rule_params or {}
            try:
                result = self._check_invoice_codes_exclusive(
                    guideline, all_lines, params
                )
            except Exception as exc:
                logger.error(
                    "Error evaluating invoice_codes_exclusive guideline %s: %s",
                    guideline.id,
                    exc,
                    exc_info=True,
                )
                result = GuidelineValidationResult(
                    guideline_id=str(guideline.id),
                    status=ValidationStatus.WARNING,
                    severity=ValidationSeverity.WARNING,
                    message=(
                        "Exclusivity guideline check could not be evaluated. "
                        "Carrier review required."
                    ),
                    required_action=RequiredAction.NONE,
                )

            if result is not None:
                exclusive_set = set(params.get("exclusive_codes", []))
                conflicting = [
                    li for li in all_lines if li.taxonomy_code in exclusive_set
                ]
                anchor = conflicting[0] if conflicting else all_lines[0]
                output.append((anchor, result))

        return output

    def _check_invoice_codes_exclusive(
        self,
        guideline: Guideline,
        all_lines: list[LineItem],
        params: dict,
    ) -> Optional[GuidelineValidationResult]:
        """
        If more than one code from the exclusive set appears on the same invoice,
        return a FAIL result.

        params: {
            "exclusive_codes": ["LA.ROOF_INSPECT_HARNESS.FLAT_FEE",
                                "LA.ROOF_INSPECT.FLAT_FEE",
                                "LA.LADDER_ACCESS.FLAT_FEE"],
            "description": "primary ladder/roof service"   # optional label
        }
        """
        exclusive_codes = params.get("exclusive_codes", [])
        if not exclusive_codes:
            logger.warning(
                "Guideline %s: invoice_codes_exclusive has no exclusive_codes",
                guideline.id,
            )
            return None

        exclusive_set = set(exclusive_codes)
        present_codes = sorted(
            {li.taxonomy_code for li in all_lines if li.taxonomy_code in exclusive_set}
        )

        if len(present_codes) <= 1:
            return None  # PASS — zero or one exclusive code present

        description = params.get("description", "exclusive service codes")
        narrative = self._narrative_cite(guideline)
        return GuidelineValidationResult(
            guideline_id=str(guideline.id),
            status=ValidationStatus.FAIL,
            severity=guideline.severity,
            message=(
                f"Multiple {description} billed on the same invoice: "
                f"{', '.join(present_codes)}. "
                f"Only one primary service code from this group may be billed per visit. "
                f"Remove the lower-tier line or resubmit with a single service code. "
                f"{narrative}"
            ),
            expected_value=f"At most 1 of: {', '.join(sorted(exclusive_codes))}",
            actual_value=f"{len(present_codes)} present: {', '.join(present_codes)}",
            required_action=RequiredAction.REUPLOAD,
        )

    # ── Invoice-level percentage checks ──────────────────────────────────────

    def validate_invoice_percentages(
        self,
        all_lines: list[LineItem],
        guidelines: list[Guideline],
    ) -> list[tuple[LineItem, "GuidelineValidationResult"]]:
        """
        Evaluate all max_pct_of_invoice guidelines against the full line list.

        Returns a list of (line_item, result) tuples — one per failing guideline,
        attributed to an arbitrary line in the numerator set so the caller can
        attach it to an existing ValidationResult row.  If a guideline fires but
        no numerator lines exist the tuple is (all_lines[0], result) so there is
        always a line to attach to.

        Called from the pipeline AFTER the per-line loop is complete.
        """
        output: list[tuple[LineItem, GuidelineValidationResult]] = []

        pct_guidelines = [
            g for g in guidelines if g.rule_type == "max_pct_of_invoice" and g.is_active
        ]
        if not pct_guidelines or not all_lines:
            return output

        for guideline in pct_guidelines:
            params = guideline.rule_params or {}
            try:
                result = self._check_max_pct_of_invoice(guideline, all_lines, params)
            except Exception as exc:
                logger.error(
                    "Error evaluating max_pct_of_invoice guideline %s: %s",
                    guideline.id,
                    exc,
                    exc_info=True,
                )
                result = GuidelineValidationResult(
                    guideline_id=str(guideline.id),
                    status=ValidationStatus.WARNING,
                    severity=ValidationSeverity.WARNING,
                    message=(
                        "Percentage guideline check could not be evaluated. "
                        "Carrier review required."
                    ),
                    required_action=RequiredAction.NONE,
                )

            if result is not None:
                numerator_lines = self._pct_numerator_lines(all_lines, params)
                anchor = numerator_lines[0] if numerator_lines else all_lines[0]
                output.append((anchor, result))

        return output

    def _pct_numerator_lines(
        self, lines: list[LineItem], params: dict
    ) -> list[LineItem]:
        """
        Return the subset of lines that form the numerator of the percentage check.

        Priority:
          1. ``applies_to_codes``  — explicit taxonomy code list
          2. ``applies_to_suffix`` + ``applies_to_domain`` — suffix match within domain
        """
        if "applies_to_codes" in params:
            codes = set(params["applies_to_codes"])
            return [li for li in lines if li.taxonomy_code in codes]

        suffix = params.get("applies_to_suffix")
        domain = params.get("applies_to_domain")
        if suffix and domain:
            return [
                li
                for li in lines
                if li.taxonomy_code
                and li.taxonomy_code.startswith(f"{domain}.")
                and li.taxonomy_code.endswith(suffix)
            ]

        # No targeting → numerator is all lines (unusual but allowed)
        return list(lines)

    def _pct_denominator_lines(
        self, lines: list[LineItem], params: dict
    ) -> list[LineItem]:
        """
        Return the subset of lines that form the denominator.

        ``denominator_domain`` (optional): restrict to lines in that domain.
        Omit / null → all invoice lines.
        """
        domain = params.get("denominator_domain")
        if domain:
            return [
                li
                for li in lines
                if li.taxonomy_code and li.taxonomy_code.startswith(f"{domain}.")
            ]
        return list(lines)

    def _check_max_pct_of_invoice(
        self,
        guideline: Guideline,
        all_lines: list[LineItem],
        params: dict,
    ) -> Optional[GuidelineValidationResult]:
        """
        Core percentage rule logic.

        Computes numerator / denominator (in dollars or hours) and compares to
        ``max_pct``.  Returns a FAIL result if the threshold is exceeded,
        None otherwise.
        """
        try:
            max_pct = Decimal(str(params["max_pct"]))
        except (KeyError, InvalidOperation):
            logger.warning(
                "Guideline %s: missing or invalid max_pct in params: %s",
                guideline.id,
                params,
            )
            return None

        basis = params.get("basis", "amount")  # "amount" | "quantity"
        description = params.get("description", "specified lines")

        numerator_lines = self._pct_numerator_lines(all_lines, params)
        denominator_lines = self._pct_denominator_lines(all_lines, params)

        if not denominator_lines:
            return None  # No denominator — nothing to check

        if basis == "quantity":
            numerator_val = sum(
                (li.raw_quantity or Decimal("0")) for li in numerator_lines
            )
            denominator_val = sum(
                (li.raw_quantity or Decimal("0")) for li in denominator_lines
            )
            unit_label = "hours"
        else:
            numerator_val = sum(
                (li.raw_amount or Decimal("0")) for li in numerator_lines
            )
            denominator_val = sum(
                (li.raw_amount or Decimal("0")) for li in denominator_lines
            )
            unit_label = "dollars"

        if denominator_val == 0:
            return None

        actual_pct = (numerator_val / denominator_val * Decimal("100")).quantize(
            Decimal("0.01")
        )

        if actual_pct <= max_pct:
            return None  # PASS

        narrative = self._narrative_cite(guideline)
        return GuidelineValidationResult(
            guideline_id=str(guideline.id),
            status=ValidationStatus.FAIL,
            severity=guideline.severity,
            message=(
                f"{description} total ({actual_pct}% of invoice {unit_label}) "
                f"exceeds the contract limit of {max_pct}%. "
                f"Numerator: {numerator_val} {unit_label}; "
                f"Denominator: {denominator_val} {unit_label}. "
                f"{narrative}"
            ),
            expected_value=f"≤ {max_pct}%",
            actual_value=f"{actual_pct}%",
            required_action=RequiredAction.ACCEPT_REDUCTION
            if guideline.severity == ValidationSeverity.ERROR
            else RequiredAction.NONE,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _narrative_cite(guideline: Guideline) -> str:
        """Format the contract narrative source as an inline citation."""
        if guideline.narrative_source:
            return f'Contract reference: "{guideline.narrative_source}"'
        return ""
