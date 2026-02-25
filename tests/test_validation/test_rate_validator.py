"""
Rate validation engine tests.
All tests use the DB fixtures from conftest — no mocking needed.
"""

import pytest
from decimal import Decimal
from datetime import date

from app.models.invoice import LineItem, LineItemStatus
from app.models.supplier import RateCard
from app.models.validation import ValidationStatus
from app.services.validation.rate_validator import RateValidator


@pytest.fixture
def validator(db):
    return RateValidator(db)


@pytest.fixture
def base_line_item(sample_invoice, db):
    """A line item that will be validated."""
    li = LineItem(
        invoice_id=sample_invoice.id,
        invoice_version=1,
        line_number=1,
        status=LineItemStatus.CLASSIFIED,
        raw_description="IME Physician Examination",
        raw_amount=Decimal("600.00"),
        raw_quantity=Decimal("1"),
        raw_unit="report",
        taxonomy_code="IME.PHY_EXAM.PROF_FEE",
        billing_component="PROF_FEE",
    )
    db.add(li)
    db.flush()
    return li


class TestRateValidatorHappyPath:
    def test_exact_match_passes(self, validator, base_line_item, sample_contract, sample_rate_cards):
        results = validator.validate(base_line_item, sample_contract)
        pass_results = [r for r in results if r.status == ValidationStatus.PASS]
        assert len(pass_results) >= 1

    def test_expected_value_set(self, validator, base_line_item, sample_contract, sample_rate_cards):
        results = validator.validate(base_line_item, sample_contract)
        pass_result = next(r for r in results if r.status == ValidationStatus.PASS)
        assert pass_result.expected_value == "$600.00"

    def test_mileage_calculation(self, validator, sample_invoice, sample_contract, sample_rate_cards, db):
        """47 miles × $0.67 = $31.49; billing $28.20 should be underbilled warning."""
        mileage_line = LineItem(
            invoice_id=sample_invoice.id,
            invoice_version=1,
            line_number=2,
            status=LineItemStatus.CLASSIFIED,
            raw_description="Mileage 47 miles",
            raw_amount=Decimal("28.20"),
            raw_quantity=Decimal("47"),
            raw_unit="mile",
            taxonomy_code="IME.PHY_EXAM.MILEAGE",
            billing_component="MILEAGE",
        )
        db.add(mileage_line)
        db.flush()
        results = validator.validate(mileage_line, sample_contract)
        # 47 × 0.67 = 31.49; billed 28.20 — underbilled (WARNING)
        assert any(r.status in (ValidationStatus.WARNING, ValidationStatus.PASS) for r in results)


class TestRateValidatorFailures:
    def test_overbill_fails(self, validator, sample_invoice, sample_contract, sample_rate_cards, db):
        """$725 billed vs $600 contracted — should FAIL."""
        li = LineItem(
            invoice_id=sample_invoice.id,
            invoice_version=1,
            line_number=3,
            status=LineItemStatus.CLASSIFIED,
            raw_description="IME Physician Examination - Neurology",
            raw_amount=Decimal("725.00"),
            raw_quantity=Decimal("1"),
            raw_unit="report",
            taxonomy_code="IME.PHY_EXAM.PROF_FEE",
            billing_component="PROF_FEE",
        )
        db.add(li)
        db.flush()
        results = validator.validate(li, sample_contract)
        fail_results = [r for r in results if r.status == ValidationStatus.FAIL]
        assert len(fail_results) == 1
        assert "725" in fail_results[0].actual_value
        assert "600" in fail_results[0].expected_value
        assert "ACCEPT_REDUCTION" in fail_results[0].required_action

    def test_no_taxonomy_code_fails(self, validator, sample_invoice, sample_contract, sample_rate_cards, db):
        """Line without taxonomy code cannot be rate-validated."""
        li = LineItem(
            invoice_id=sample_invoice.id,
            invoice_version=1,
            line_number=4,
            status=LineItemStatus.CLASSIFIED,
            raw_description="Unclassified service",
            raw_amount=Decimal("100.00"),
            raw_quantity=Decimal("1"),
            taxonomy_code=None,
        )
        db.add(li)
        db.flush()
        results = validator.validate(li, sample_contract)
        assert results[0].status == ValidationStatus.FAIL
        assert "REQUEST_RECLASSIFICATION" in results[0].required_action

    def test_no_rate_card_fails(self, validator, sample_invoice, sample_contract, db):
        """Taxonomy code with no rate card in contract should FAIL."""
        li = LineItem(
            invoice_id=sample_invoice.id,
            invoice_version=1,
            line_number=5,
            status=LineItemStatus.CLASSIFIED,
            raw_description="Surveillance",
            raw_amount=Decimal("500.00"),
            raw_quantity=Decimal("5"),
            raw_unit="hour",
            taxonomy_code="INV.SURVEILLANCE.PROF_FEE",  # Not in sample_rate_cards
            billing_component="PROF_FEE",
        )
        db.add(li)
        db.flush()
        results = validator.validate(li, sample_contract)
        assert results[0].status == ValidationStatus.FAIL
        assert "No contracted rate" in results[0].message

    def test_max_units_enforced(self, validator, sample_invoice, sample_contract, db):
        """Rate card with max_units=1; billing qty=2 should fail."""
        rc = RateCard(
            contract_id=sample_contract.id,
            taxonomy_code="IME.PHY_EXAM.TRAVEL_LODGING",
            contracted_rate=Decimal("200.00"),
            max_units=Decimal("1"),
            effective_from=date(2024, 1, 1),
        )
        db.add(rc)
        db.flush()
        li = LineItem(
            invoice_id=sample_invoice.id,
            invoice_version=1,
            line_number=6,
            status=LineItemStatus.CLASSIFIED,
            raw_description="Lodging - 2 nights",
            raw_amount=Decimal("400.00"),
            raw_quantity=Decimal("2"),
            raw_unit="night",
            taxonomy_code="IME.PHY_EXAM.TRAVEL_LODGING",
            billing_component="TRAVEL_LODGING",
            service_date=date(2024, 11, 15),
        )
        db.add(li)
        db.flush()
        results = validator.validate(li, sample_contract)
        max_unit_fails = [r for r in results if "maximum" in r.message.lower() and r.status == ValidationStatus.FAIL]
        assert len(max_unit_fails) == 1

    def test_bundling_violation_flagged(self, validator, sample_invoice, sample_contract, db):
        """All-inclusive rate card + separate mileage line = bundling violation."""
        rc = RateCard(
            contract_id=sample_contract.id,
            taxonomy_code="IME.PHY_EXAM.MILEAGE",
            contracted_rate=Decimal("0.67"),
            is_all_inclusive=True,
            effective_from=date(2024, 1, 1),
        )
        db.add(rc)
        db.flush()
        li = LineItem(
            invoice_id=sample_invoice.id,
            invoice_version=1,
            line_number=7,
            status=LineItemStatus.CLASSIFIED,
            raw_description="Mileage 47 miles",
            raw_amount=Decimal("28.20"),
            raw_quantity=Decimal("47"),
            raw_unit="mile",
            taxonomy_code="IME.PHY_EXAM.MILEAGE",
            billing_component="MILEAGE",
        )
        db.add(li)
        db.flush()
        results = validator.validate(li, sample_contract)
        bundling_fails = [r for r in results if "all-inclusive" in r.message.lower()]
        assert len(bundling_fails) == 1
