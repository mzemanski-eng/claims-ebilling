"""
Integration tests for the full invoice processing pipeline.

These tests exercise the complete classify → rate validate → guideline validate
flow against a real (test) database. They use the sample IME fixture CSV.

Requires DB — run with a live Postgres instance (provided by CI or docker-compose).
"""

import pytest
from datetime import date

from app.models.invoice import Invoice, SubmissionStatus, LineItemStatus
from app.models.validation import ValidationStatus, ExceptionStatus
from app.workers.invoice_pipeline import process_invoice_sync


pytestmark = pytest.mark.usefixtures("db")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_invoice(db, supplier, contract, invoice_number="INV-PIPE-001"):
    invoice = Invoice(
        supplier_id=supplier.id,
        contract_id=contract.id,
        invoice_number=invoice_number,
        invoice_date=date(2025, 2, 15),
        status=SubmissionStatus.SUBMITTED,
        current_version=1,
    )
    db.add(invoice)
    db.flush()
    return invoice


# ── Full pipeline tests ───────────────────────────────────────────────────────


class TestPipelineFullRun:
    """End-to-end pipeline tests using the sample IME fixture CSV."""

    def test_pipeline_processes_all_lines(
        self, db, sample_supplier, sample_contract, sample_rate_cards, sample_csv_bytes
    ):
        """All 13 lines in the fixture CSV should be processed."""
        invoice = _make_invoice(db, sample_supplier, sample_contract)

        summary = process_invoice_sync(
            invoice_id=str(invoice.id),
            file_bytes=sample_csv_bytes,
            filename="sample_invoice_ime.csv",
            db=db,
        )

        assert summary["lines_processed"] == 13
        assert "error" not in summary

    def test_pipeline_creates_line_items(
        self, db, sample_supplier, sample_contract, sample_rate_cards, sample_csv_bytes
    ):
        """Line items should be persisted in the DB after processing."""
        invoice = _make_invoice(db, sample_supplier, sample_contract)

        process_invoice_sync(
            invoice_id=str(invoice.id),
            file_bytes=sample_csv_bytes,
            filename="sample_invoice_ime.csv",
            db=db,
        )

        db.refresh(invoice)
        assert len(invoice.line_items) == 13

    def test_pipeline_classifies_ime_exam(
        self, db, sample_supplier, sample_contract, sample_rate_cards, sample_csv_bytes
    ):
        """IME Physician Examination should classify to IME.PHY_EXAM.PROF_FEE."""
        invoice = _make_invoice(db, sample_supplier, sample_contract)

        process_invoice_sync(
            invoice_id=str(invoice.id),
            file_bytes=sample_csv_bytes,
            filename="sample_invoice_ime.csv",
            db=db,
        )

        db.refresh(invoice)
        exam_line = next(
            li
            for li in invoice.line_items
            if "Physician Examination" in li.raw_description
            and "Neurology" not in li.raw_description
        )
        assert exam_line.taxonomy_code == "IME.PHY_EXAM.PROF_FEE"
        assert exam_line.mapping_confidence in ("HIGH", "MEDIUM")

    def test_pipeline_validates_correct_rate(
        self, db, sample_supplier, sample_contract, sample_rate_cards, sample_csv_bytes
    ):
        """No-show fee at $100 matches contracted rate — should PASS rate validation."""
        invoice = _make_invoice(db, sample_supplier, sample_contract)

        process_invoice_sync(
            invoice_id=str(invoice.id),
            file_bytes=sample_csv_bytes,
            filename="sample_invoice_ime.csv",
            db=db,
        )

        db.refresh(invoice)
        no_show = next(
            li for li in invoice.line_items if "No-show" in li.raw_description
        )
        assert no_show.taxonomy_code == "IME.NO_SHOW.NO_SHOW_FEE"
        rate_results = [
            v for v in no_show.validation_results if v.validation_type == "RATE"
        ]
        assert any(v.status == ValidationStatus.PASS for v in rate_results)

    def test_pipeline_flags_overbilled_line(
        self, db, sample_supplier, sample_contract, sample_rate_cards, sample_csv_bytes
    ):
        """Neurology IME at $725 vs $600 contracted rate should FAIL rate check."""
        invoice = _make_invoice(db, sample_supplier, sample_contract)

        process_invoice_sync(
            invoice_id=str(invoice.id),
            file_bytes=sample_csv_bytes,
            filename="sample_invoice_ime.csv",
            db=db,
        )

        db.refresh(invoice)
        neuro = next(
            li for li in invoice.line_items if "Neurology" in li.raw_description
        )
        assert neuro.taxonomy_code == "IME.PHY_EXAM.PROF_FEE"
        rate_results = [
            v for v in neuro.validation_results if v.validation_type == "RATE"
        ]
        assert any(v.status == ValidationStatus.FAIL for v in rate_results)
        assert neuro.status == LineItemStatus.EXCEPTION

    def test_pipeline_sets_review_required_on_errors(
        self, db, sample_supplier, sample_contract, sample_rate_cards, sample_csv_bytes
    ):
        """Invoice with billing errors should end in REVIEW_REQUIRED status."""
        invoice = _make_invoice(db, sample_supplier, sample_contract)

        summary = process_invoice_sync(
            invoice_id=str(invoice.id),
            file_bytes=sample_csv_bytes,
            filename="sample_invoice_ime.csv",
            db=db,
        )

        db.refresh(invoice)
        assert invoice.status == SubmissionStatus.REVIEW_REQUIRED
        assert summary["lines_error"] > 0

    def test_pipeline_opens_exceptions_for_failures(
        self, db, sample_supplier, sample_contract, sample_rate_cards, sample_csv_bytes
    ):
        """Each validation FAIL should create an open ExceptionRecord."""
        invoice = _make_invoice(db, sample_supplier, sample_contract)

        process_invoice_sync(
            invoice_id=str(invoice.id),
            file_bytes=sample_csv_bytes,
            filename="sample_invoice_ime.csv",
            db=db,
        )

        db.refresh(invoice)
        all_exceptions = [exc for li in invoice.line_items for exc in li.exceptions]
        assert len(all_exceptions) > 0
        for exc in all_exceptions:
            assert exc.status == ExceptionStatus.OPEN


class TestPipelineCleanInvoice:
    """Tests for an invoice with all lines correctly billed."""

    def test_clean_invoice_gets_pending_carrier_review(
        self, db, sample_supplier, sample_contract, sample_rate_cards
    ):
        """An invoice with no billing errors should end in PENDING_CARRIER_REVIEW."""
        from app.models.invoice import InvoiceVersion

        # Build a clean CSV with all amounts matching contracted rates
        clean_csv = (
            b"claim_number,service_date,description,code,quantity,unit,amount\n"
            b"CLM-CLEAN-001,2025-02-15,IME Physician Examination - Orthopedic,IME-001,1,report,600.00\n"
            b"CLM-CLEAN-001,2025-02-15,No-show Fee - claimant did not appear,IME-007,1,flat,100.00\n"
            b"CLM-CLEAN-001,2025-02-15,IME Cancellation Fee - less than 48 hour notice,IME-005,1,flat,150.00\n"
        )

        invoice = _make_invoice(db, sample_supplier, sample_contract, "INV-CLEAN-001")

        # Create version record (normally done by upload endpoint)
        version = InvoiceVersion(
            invoice_id=invoice.id,
            version_number=1,
            raw_file_path="/tmp/test_clean.csv",
            file_format="csv",
            submitted_at=invoice.invoice_date,
        )
        db.add(version)
        db.flush()

        summary = process_invoice_sync(
            invoice_id=str(invoice.id),
            file_bytes=clean_csv,
            filename="clean_invoice.csv",
            db=db,
        )

        db.refresh(invoice)
        assert invoice.status == SubmissionStatus.PENDING_CARRIER_REVIEW
        assert summary["lines_error"] == 0
        assert summary["lines_processed"] == 3

    def test_clean_invoice_has_no_open_exceptions(
        self, db, sample_supplier, sample_contract, sample_rate_cards
    ):
        """A correctly billed invoice should have zero open exceptions."""
        from app.models.invoice import InvoiceVersion

        clean_csv = (
            b"claim_number,service_date,description,code,quantity,unit,amount\n"
            b"CLM-CLEAN-002,2025-02-15,IME Addendum Report - additional records review,IME-003,1,report,125.00\n"
        )

        invoice = _make_invoice(db, sample_supplier, sample_contract, "INV-CLEAN-002")
        version = InvoiceVersion(
            invoice_id=invoice.id,
            version_number=1,
            raw_file_path="/tmp/test_addendum.csv",
            file_format="csv",
            submitted_at=invoice.invoice_date,
        )
        db.add(version)
        db.flush()

        process_invoice_sync(
            invoice_id=str(invoice.id),
            file_bytes=clean_csv,
            filename="addendum_invoice.csv",
            db=db,
        )

        db.refresh(invoice)
        all_exceptions = [exc for li in invoice.line_items for exc in li.exceptions]
        assert len(all_exceptions) == 0


class TestPipelineEdgeCases:
    """Edge case and error handling tests."""

    def test_empty_csv_fails_gracefully(
        self, db, sample_supplier, sample_contract, sample_rate_cards
    ):
        """An empty CSV should not crash the pipeline."""
        invoice = _make_invoice(db, sample_supplier, sample_contract, "INV-EMPTY-001")

        summary = process_invoice_sync(
            invoice_id=str(invoice.id),
            file_bytes=b"claim_number,service_date,description,code,quantity,unit,amount\n",
            filename="empty.csv",
            db=db,
        )

        # Should process 0 lines without error
        assert summary.get("lines_processed", 0) == 0

    def test_unrecognized_service_creates_exception(
        self, db, sample_supplier, sample_contract, sample_rate_cards
    ):
        """A completely unrecognizable service description should generate a classification exception."""
        from app.models.invoice import InvoiceVersion

        mystery_csv = (
            b"claim_number,service_date,description,code,quantity,unit,amount\n"
            b"CLM-MYSTERY-001,2025-02-15,Completely unrecognizable xyzzy service,XYZ-999,1,unit,999.99\n"
        )
        invoice = _make_invoice(db, sample_supplier, sample_contract, "INV-MYSTERY-001")
        version = InvoiceVersion(
            invoice_id=invoice.id,
            version_number=1,
            raw_file_path="/tmp/test_mystery.csv",
            file_format="csv",
            submitted_at=invoice.invoice_date,
        )
        db.add(version)
        db.flush()

        process_invoice_sync(
            invoice_id=str(invoice.id),
            file_bytes=mystery_csv,
            filename="mystery.csv",
            db=db,
        )

        db.refresh(invoice)
        mystery_line = invoice.line_items[0]
        assert mystery_line.status == LineItemStatus.EXCEPTION
        exceptions = mystery_line.exceptions
        assert len(exceptions) > 0

    def test_invoice_not_found_returns_error(self, db):
        """Processing a non-existent invoice_id should return an error dict, not raise."""
        import uuid

        result = process_invoice_sync(
            invoice_id=str(uuid.uuid4()),
            file_bytes=b"",
            filename="test.csv",
            db=db,
        )
        assert "error" in result
