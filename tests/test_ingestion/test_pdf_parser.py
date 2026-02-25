"""
PDF parser tests — all skipped in v1.

These tests define the expected behavior for v2 implementation.
When PDFParser.parse() is implemented, remove the skip markers.

The test file structure and fixture setup is already in place —
PDF support is one pytest.mark.skip removal away from being live.
"""

import pytest
from app.services.ingestion.pdf_parser import PDFParser


@pytest.fixture
def parser():
    return PDFParser()


@pytest.mark.skip(reason="PDF parsing not yet implemented — v2 feature")
class TestPDFParserHappyPath:
    def test_parses_simple_table_pdf(self, parser):
        """PDF with a clean table layout should extract all rows."""
        pass  # TODO: load fixture PDF bytes

    def test_amounts_are_decimal(self, parser):
        pass

    def test_multi_page_pdf(self, parser):
        """Line items can span multiple pages."""
        pass

    def test_raw_text_stored_for_each_page(self, parser):
        """Extraction artifacts should capture per-page raw text."""
        pass


def test_pdf_parser_raises_not_implemented():
    """
    v1: PDFParser.parse() must raise NotImplementedError with a
    helpful message directing suppliers to use CSV.
    This test must PASS in v1 — it documents the stub behavior.
    """
    parser = PDFParser()
    with pytest.raises(NotImplementedError, match="not yet implemented"):
        parser.parse(b"%PDF-1.4 fake content", "invoice.pdf")
