"""Tests for CSVParser — the primary ingestion path."""

import pytest
from decimal import Decimal

from app.services.ingestion.csv_parser import CSVParser
from app.services.ingestion.base import ParseError


SAMPLE_CSV = b"""claim_number,service_date,description,code,quantity,unit,amount
CLM-001,2024-11-15,IME Physician Examination,IME-001,1,report,650.00
CLM-001,2024-11-15,Mileage - 47 miles,MILE-001,47,mile,28.20
CLM-002,2024-11-18,IME Addendum Report,IME-003,1,report,150.00
"""

SAMPLE_CSV_ALT_HEADERS = b"""Reference,Date,Service Description,BillingCode,Qty,UoM,Total
CLM-001,11/15/2024,IME Physician Examination,IME-001,1,report,650.00
"""

SAMPLE_CSV_MISSING_AMOUNT = b"""claim_number,service_date,description,quantity,unit
CLM-001,2024-11-15,IME Physician Examination,1,report
"""


@pytest.fixture
def parser():
    return CSVParser()


class TestCSVParserHappyPath:
    def test_parses_standard_csv(self, parser):
        result = parser.parse(SAMPLE_CSV, "invoice.csv")
        assert len(result.line_items) == 3
        assert result.extraction_method == "csv"

    def test_line_numbers_are_sequential(self, parser):
        result = parser.parse(SAMPLE_CSV, "invoice.csv")
        assert [li.line_number for li in result.line_items] == [1, 2, 3]

    def test_amounts_are_decimal(self, parser):
        result = parser.parse(SAMPLE_CSV, "invoice.csv")
        assert result.line_items[0].raw_amount == Decimal("650.00")
        assert result.line_items[1].raw_amount == Decimal("28.20")

    def test_quantity_defaults_to_one(self, parser):
        """Quantity defaults to 1 if column missing."""
        csv = b"description,amount\nIME Exam,600.00\n"
        result = parser.parse(csv, "test.csv")
        assert result.line_items[0].raw_quantity == Decimal("1")

    def test_claim_number_parsed(self, parser):
        result = parser.parse(SAMPLE_CSV, "invoice.csv")
        assert result.line_items[0].claim_number == "CLM-001"

    def test_service_date_parsed(self, parser):
        result = parser.parse(SAMPLE_CSV, "invoice.csv")
        from datetime import date
        assert result.line_items[0].service_date == date(2024, 11, 15)

    def test_raw_code_parsed(self, parser):
        result = parser.parse(SAMPLE_CSV, "invoice.csv")
        assert result.line_items[0].raw_code == "IME-001"

    def test_alternative_column_headers(self, parser):
        """Parser should find columns with non-standard headers."""
        result = parser.parse(SAMPLE_CSV_ALT_HEADERS, "invoice.csv")
        assert len(result.line_items) == 1
        assert result.line_items[0].raw_description == "IME Physician Examination"
        assert result.line_items[0].raw_amount == Decimal("650.00")

    def test_strips_dollar_signs_from_amounts(self, parser):
        csv = b"description,amount\nIME Exam,$600.00\n"
        result = parser.parse(csv, "test.csv")
        assert result.line_items[0].raw_amount == Decimal("600.00")

    def test_strips_commas_from_amounts(self, parser):
        csv = b"description,amount\nIME Exam,\"1,200.00\"\n"
        result = parser.parse(csv, "test.csv")
        assert result.line_items[0].raw_amount == Decimal("1200.00")

    def test_bom_handled(self, parser):
        """UTF-8 BOM should be silently stripped."""
        csv = b"\xef\xbb\xbfdescription,amount\nIME Exam,600.00\n"
        result = parser.parse(csv, "test.csv")
        assert len(result.line_items) == 1


class TestCSVParserEdgeCases:
    def test_empty_file_raises(self, parser):
        with pytest.raises(ParseError, match="no data rows"):
            parser.parse(b"description,amount\n", "empty.csv")

    def test_completely_empty_file_raises(self, parser):
        with pytest.raises(ParseError):
            parser.parse(b"", "empty.csv")

    def test_missing_amount_column_raises(self, parser):
        with pytest.raises(ParseError):
            parser.parse(SAMPLE_CSV_MISSING_AMOUNT, "test.csv")

    def test_invalid_amount_skips_row(self, parser):
        """Rows with invalid amounts are skipped with a warning, not a crash."""
        csv = b"description,amount\nIME Exam,NOT_A_NUMBER\nAddendum,125.00\n"
        result = parser.parse(csv, "test.csv")
        assert len(result.line_items) == 1   # Second row survived
        assert len(result.warnings) > 0

    def test_tsv_delimiter_detected(self, parser):
        tsv = b"description\tamount\nIME Exam\t600.00\n"
        result = parser.parse(tsv, "invoice.tsv")
        assert len(result.line_items) == 1
        assert result.line_items[0].raw_amount == Decimal("600.00")


class TestCSVParserFixture:
    def test_full_fixture_file(self, parser, sample_csv_bytes):
        """The canonical fixture should parse without errors."""
        result = parser.parse(sample_csv_bytes, "sample_invoice_ime.csv")
        assert len(result.line_items) == 13
        assert result.extraction_method == "csv"
        assert not any("Required column" in w for w in result.warnings)
