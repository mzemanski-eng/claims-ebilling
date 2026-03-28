"""
Biller agent — creates invoices and line items for each contract.
Uses Claude (haiku) for line item descriptions; scenarios are deterministic.
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy.orm import Session

from scripts.agents.base import (
    US_STATES,
    BaseAgent,
    InvoiceSpec,
    LineItemSpec,
    RunContext,
    calc_amount,
    random_claim_number,
    random_invoice_date,
    random_quantity,
    random_service_date,
)
from app.models.invoice import Invoice, LineItem, LineItemStatus, SubmissionStatus
from app.models.validation import (
    ExceptionRecord,
    ExceptionStatus,
    RequiredAction,
    ValidationResult,
    ValidationSeverity,
    ValidationStatus,
    ValidationType,
)

logger = logging.getLogger(__name__)

INVOICES_PER_CONTRACT = 10

# Scenario distribution for 10 invoices: 70% clean, 20% rate discrepancy, 10% guideline
_BASE_SCENARIOS = ["clean"] * 7 + ["rate_discrepancy"] * 2 + ["guideline_violation"] * 1


def _billing_component(taxonomy_code: str) -> str:
    """Extract last segment of taxonomy code, e.g. 'PROF_FEE', 'L1'."""
    parts = taxonomy_code.split(".")
    return parts[-1] if parts else ""


def _unit_model(rate_type: str) -> str:
    return {
        "hourly": "hourly",
        "mileage": "mileage",
        "per_diem": "per_diem",
        "flat": "flat_fee",
    }.get(rate_type, "flat_fee")


def _raw_unit(taxonomy_code: str, rate_type: str) -> str:
    code_lower = taxonomy_code.lower()
    if "transcript" in code_lower or "copy_repro" in code_lower:
        return "pg"
    if "mileage" in code_lower or rate_type == "mileage":
        return "mi"
    if rate_type == "hourly" or "videography" in code_lower:
        return "hr"
    if rate_type == "per_diem":
        return "day"
    return "ea"


class Biller(BaseAgent):
    """Agent 2: Creates invoices and line items for each contract."""

    def __init__(self, ctx: RunContext, db: Session) -> None:
        super().__init__(ctx, db)
        self._invoice_seq = 0

    def run(self) -> None:
        logger.info("Biller starting (dry_run=%s)", self.dry_run)

        for contract_spec in self.ctx.contracts:
            codes = [rc.taxonomy_code for rc in contract_spec.rate_cards]

            # 1 Claude call per contract: get line item descriptions
            descriptions = self._generate_descriptions(
                domain=contract_spec.domain,
                taxonomy_codes=codes,
            )

            # Shuffle scenario order for variety within each contract
            scenarios = _BASE_SCENARIOS.copy()
            random.shuffle(scenarios)

            for scenario in scenarios[:INVOICES_PER_CONTRACT]:
                self._invoice_seq += 1
                inv_date = random_invoice_date(contract_spec.contract_idx)
                year = inv_date.year
                domain_prefix = contract_spec.domain[:2].upper()
                invoice_number = f"{domain_prefix}-{year}-{self._invoice_seq:04d}"

                # 1-3 claim numbers per invoice, reused across line items
                n_claims = random.randint(1, 3)
                claim_numbers = [random_claim_number() for _ in range(n_claims)]
                n_lines = random.randint(3, 8)

                # For guideline_violation: find a max_units guideline with a code in this contract
                violation_guideline = None
                effective_scenario = scenario
                if scenario == "guideline_violation":
                    for g in contract_spec.guidelines:
                        if (
                            g.rule_type == "max_units"
                            and g.taxonomy_code
                            and g.taxonomy_code in codes
                        ):
                            violation_guideline = g
                            break
                    if violation_guideline is None:
                        # Fallback if no usable max_units guideline
                        effective_scenario = "rate_discrepancy"

                line_items: list[LineItemSpec] = []
                has_exception = False

                for line_num in range(1, n_lines + 1):
                    claim = random.choice(claim_numbers)
                    state = random.choice(US_STATES)
                    svc_date = random_service_date(inv_date)

                    # Pick rate card for this line
                    if (
                        effective_scenario == "guideline_violation"
                        and line_num == 1
                        and violation_guideline
                    ):
                        # Force the violating code onto the first line
                        tc = violation_guideline.taxonomy_code
                        rc_spec = next(
                            (r for r in contract_spec.rate_cards
                             if r.taxonomy_code == tc),
                            contract_spec.rate_cards[0],
                        )
                    else:
                        rc_spec = random.choice(contract_spec.rate_cards)
                        tc = rc_spec.taxonomy_code

                    contracted_rate = rc_spec.contracted_rate
                    rate_type = rc_spec.rate_type
                    unit = _raw_unit(tc, rate_type)

                    # Determine quantity and scenario for this line
                    if (
                        effective_scenario == "guideline_violation"
                        and line_num == 1
                        and violation_guideline
                    ):
                        max_val = Decimal(
                            str(violation_guideline.rule_params.get("max", 5))
                        )
                        quantity = max_val + Decimal(str(random.randint(1, 3)))
                        line_scenario = "guideline_violation"
                        has_exception = True
                    else:
                        quantity = random_quantity(tc, rate_type)
                        line_scenario = "clean"

                    expected = calc_amount(contracted_rate, quantity)

                    # Rate discrepancy: overbill some lines
                    if (
                        effective_scenario == "rate_discrepancy"
                        and line_scenario == "clean"
                        and line_num <= max(1, n_lines // 2)
                    ):
                        multiplier = Decimal(
                            str(round(random.uniform(1.10, 1.50), 2))
                        )
                        raw_amount = (expected * multiplier).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )
                        line_scenario = "rate_discrepancy"
                        has_exception = True
                    else:
                        raw_amount = expected

                    desc = descriptions.get(tc, tc.replace(".", " — ").replace("_", " ").title())

                    line_items.append(
                        LineItemSpec(
                            line_number=line_num,
                            raw_description=desc,
                            raw_code=None,
                            raw_amount=raw_amount,
                            raw_quantity=quantity,
                            raw_unit=unit,
                            taxonomy_code=tc,
                            contracted_rate=contracted_rate,
                            expected_amount=expected,
                            claim_number=claim,
                            service_date=svc_date,
                            service_state=state,
                            scenario=line_scenario,
                        )
                    )

                inv_status = (
                    SubmissionStatus.REVIEW_REQUIRED
                    if has_exception
                    else SubmissionStatus.APPROVED
                )

                contract_global_idx = self.ctx.contracts.index(contract_spec)
                supplier_idx = contract_spec.supplier_idx

                invoice_spec = InvoiceSpec(
                    contract_idx_global=contract_global_idx,
                    supplier_idx=supplier_idx,
                    invoice_number=invoice_number,
                    invoice_date=inv_date,
                    status=inv_status,
                    line_items=line_items,
                )
                self.ctx.invoices.append(invoice_spec)

        # Write to DB if not dry_run
        if not self.dry_run:
            self._write_to_db()

        self._print_preview()

    # ── Claude call ──────────────────────────────────────────────────────────

    def _generate_descriptions(
        self, domain: str, taxonomy_codes: list[str]
    ) -> dict[str, str]:
        """1 Claude call → {taxonomy_code: description}."""
        code_list = "\n".join(
            f"  {i + 1}. {code}" for i, code in enumerate(taxonomy_codes)
        )
        text = self._call_claude(
            system=(
                "You are a billing coordinator at an insurance services vendor. "
                "You write concise, professional descriptions for invoice line items."
            ),
            user=(
                f"Generate one realistic invoice line item description for each billing "
                f"code from service domain '{domain}'.\n\n"
                f"{code_list}\n\n"
                f"Return ONLY a JSON array of exactly {len(taxonomy_codes)} strings, "
                f"one per code in the same order. Each should be 5-12 words, professional, "
                f"and sound like a real invoice entry."
            ),
            max_tokens=1024,
        )
        try:
            result = self._parse_json_response(text)
            if isinstance(result, list) and len(result) == len(taxonomy_codes):
                return {code: str(result[i]) for i, code in enumerate(taxonomy_codes)}
        except Exception:
            pass
        # Fallback: code-derived descriptions
        return {
            code: code.replace(".", " — ").replace("_", " ").title()
            for code in taxonomy_codes
        }

    # ── DB write ─────────────────────────────────────────────────────────────

    def _write_to_db(self) -> None:
        """Write invoices, line items, validation results, and exception records."""
        for invoice_spec in self.ctx.invoices:
            contract_spec = self.ctx.contracts[invoice_spec.contract_idx_global]
            supplier_spec = self.ctx.suppliers[invoice_spec.supplier_idx]

            if not contract_spec.db_id or not supplier_spec.db_id:
                logger.warning(
                    "Missing db_id for contract/supplier — skipping invoice %s",
                    invoice_spec.invoice_number,
                )
                continue

            # Skip-if-exists on invoice_number + supplier_id
            existing = (
                self.db.query(Invoice)
                .filter(
                    Invoice.invoice_number == invoice_spec.invoice_number,
                    Invoice.supplier_id == supplier_spec.db_id,
                )
                .first()
            )
            if existing:
                logger.info("Invoice %s exists — skipping", invoice_spec.invoice_number)
                invoice_spec.db_id = existing.id
                continue

            inv = Invoice(
                supplier_id=supplier_spec.db_id,
                contract_id=contract_spec.db_id,
                invoice_number=invoice_spec.invoice_number,
                invoice_date=invoice_spec.invoice_date,
                status=invoice_spec.status,
                current_version=1,
            )
            self.db.add(inv)
            self.db.flush()
            invoice_spec.db_id = inv.id
            logger.info("Created invoice %s", invoice_spec.invoice_number)

            for li_spec in invoice_spec.line_items:
                rc_spec = next(
                    (r for r in contract_spec.rate_cards
                     if r.taxonomy_code == li_spec.taxonomy_code),
                    None,
                )

                li_status = (
                    LineItemStatus.VALIDATED
                    if li_spec.scenario == "clean"
                    else LineItemStatus.EXCEPTION
                )

                li = LineItem(
                    invoice_id=inv.id,
                    invoice_version=1,
                    line_number=li_spec.line_number,
                    status=li_status,
                    raw_description=li_spec.raw_description,
                    raw_code=li_spec.raw_code,
                    raw_amount=li_spec.raw_amount,
                    raw_quantity=li_spec.raw_quantity,
                    raw_unit=li_spec.raw_unit,
                    claim_number=li_spec.claim_number,
                    service_date=li_spec.service_date,
                    service_state=li_spec.service_state,
                    taxonomy_code=li_spec.taxonomy_code,
                    billing_component=_billing_component(li_spec.taxonomy_code),
                    mapped_unit_model=_unit_model(rc_spec.rate_type if rc_spec else "flat"),
                    mapping_confidence="HIGH",
                    mapped_rate=li_spec.contracted_rate,
                    expected_amount=li_spec.expected_amount,
                )
                self.db.add(li)
                self.db.flush()
                li_spec.db_id = li.id

                if li_spec.scenario == "rate_discrepancy":
                    self._write_rate_exception(li, li_spec, rc_spec)

                elif li_spec.scenario == "guideline_violation":
                    g_spec = next(
                        (g for g in contract_spec.guidelines
                         if g.rule_type == "max_units"
                         and g.taxonomy_code == li_spec.taxonomy_code),
                        None,
                    )
                    self._write_guideline_exception(li, li_spec, g_spec)

    def _write_rate_exception(
        self,
        li: "LineItem",
        li_spec: LineItemSpec,
        rc_spec,
    ) -> None:
        vr = ValidationResult(
            line_item_id=li.id,
            validation_type=ValidationType.RATE,
            rate_card_id=rc_spec.db_id if rc_spec else None,
            guideline_id=None,
            status=ValidationStatus.FAIL,
            severity=ValidationSeverity.ERROR,
            message=(
                f"Billed amount {li_spec.raw_amount} exceeds contracted rate "
                f"({li_spec.contracted_rate} \u00d7 {li_spec.raw_quantity} = "
                f"{li_spec.expected_amount})"
            ),
            expected_value=str(li_spec.expected_amount),
            actual_value=str(li_spec.raw_amount),
            required_action=RequiredAction.ACCEPT_REDUCTION,
        )
        self.db.add(vr)
        self.db.flush()
        exc = ExceptionRecord(
            line_item_id=li.id,
            validation_result_id=vr.id,
            status=ExceptionStatus.OPEN,
        )
        self.db.add(exc)
        self.db.flush()

    def _write_guideline_exception(
        self,
        li: "LineItem",
        li_spec: LineItemSpec,
        g_spec,
    ) -> None:
        max_val = g_spec.rule_params.get("max", 5) if g_spec else 5
        period = g_spec.rule_params.get("period", "per_claim") if g_spec else "per_claim"
        vr = ValidationResult(
            line_item_id=li.id,
            validation_type=ValidationType.GUIDELINE,
            rate_card_id=None,
            guideline_id=g_spec.db_id if g_spec else None,
            status=ValidationStatus.FAIL,
            severity=ValidationSeverity.ERROR,
            message=(
                f"Quantity {li_spec.raw_quantity} exceeds maximum {max_val} units "
                f"{period} per contract guidelines"
            ),
            expected_value=str(max_val),
            actual_value=str(li_spec.raw_quantity),
            required_action=RequiredAction.ACCEPT_REDUCTION,
        )
        self.db.add(vr)
        self.db.flush()
        exc = ExceptionRecord(
            line_item_id=li.id,
            validation_result_id=vr.id,
            status=ExceptionStatus.OPEN,
        )
        self.db.add(exc)
        self.db.flush()

    # ── Preview ──────────────────────────────────────────────────────────────

    def _print_preview(self) -> None:
        W = 80
        print("\n" + "=" * W)
        print("  AGENT 2 — BILLER PREVIEW")
        print("=" * W)
        header = (
            f"  {'Supplier':<30} {'Dom':<6} {'Inv':>4} "
            f"{'Billed':>12} {'Clean%':>7} {'Rate%':>6} {'Gline%':>7}"
        )
        print(header)
        print("  " + "-" * 74)

        for supplier_spec in self.ctx.suppliers:
            for contract_spec in supplier_spec.contracts:
                c_idx = self.ctx.contracts.index(contract_spec)
                inv_list = [
                    iv for iv in self.ctx.invoices
                    if iv.contract_idx_global == c_idx
                ]
                if not inv_list:
                    continue
                all_lines = [li for iv in inv_list for li in iv.line_items]
                n = max(len(all_lines), 1)
                total = sum(li.raw_amount for li in all_lines)
                n_clean = sum(1 for li in all_lines if li.scenario == "clean")
                n_rate = sum(1 for li in all_lines if li.scenario == "rate_discrepancy")
                n_gline = sum(
                    1 for li in all_lines if li.scenario == "guideline_violation"
                )
                print(
                    f"  {supplier_spec.name[:29]:<30} {contract_spec.domain:<6} "
                    f"{len(inv_list):>4} {float(total):>12,.2f} "
                    f"{100*n_clean/n:>6.0f}% {100*n_rate/n:>5.0f}% "
                    f"{100*n_gline/n:>6.0f}%"
                )

        print("  " + "-" * 74)
        all_inv = self.ctx.invoices
        all_lines = [li for iv in all_inv for li in iv.line_items]
        n = max(len(all_lines), 1)
        total = sum(li.raw_amount for li in all_lines)
        n_clean = sum(1 for li in all_lines if li.scenario == "clean")
        n_rate = sum(1 for li in all_lines if li.scenario == "rate_discrepancy")
        n_gline = sum(1 for li in all_lines if li.scenario == "guideline_violation")
        print(
            f"  TOTALS → {len(all_inv)} invoices | {len(all_lines)} lines | "
            f"${float(total):,.2f} | "
            f"{100*n_clean/n:.0f}% clean / "
            f"{100*n_rate/n:.0f}% rate / "
            f"{100*n_gline/n:.0f}% guideline"
        )

        # 3 sample line items
        if all_lines:
            print("\n  Sample line items:")
            samples = random.sample(all_lines, min(3, len(all_lines)))
            for li in samples:
                tag = f"[{li.scenario[:4]}]"
                print(
                    f"    {tag} {li.taxonomy_code:<42} ${float(li.raw_amount):>8.2f}  "
                    f"'{li.raw_description[:38]}'"
                )
        print("=" * W + "\n")
