"""
PDFParser — PDF invoice extraction.

STATUS: STUBBED — v1 ships CSV-only.

The interface is fully wired:
  - PDFParser implements BaseParser (same contract as CSVParser)
  - The worker's format-dispatch logic routes PDF files here
  - All downstream code (classification, validation, audit) is format-agnostic

When PDF parsing is activated for v2:
  1. Remove the NotImplementedError from parse()
  2. Implement _extract_with_pdfplumber()
  3. Implement _extract_tables() for structured invoice tables
  4. Add per-supplier layout templates as needed
  5. Enable the skipped tests in tests/test_ingestion/test_pdf_parser.py

De-risking experiment to run before implementation:
  Collect 5-10 real PDFs per service domain. Run:
    python -c "
    import pdfplumber
    with pdfplumber.open('sample.pdf') as pdf:
        for page in pdf.pages:
            print(page.extract_table())
            print(page.extract_text())
    "
  Assess: table detection rate, column alignment, amount accuracy.
  Decision gate: >80% line-item accuracy → proceed with pdfplumber.
  Otherwise: build per-supplier layout templates.
"""

import logging
from typing import Optional

from app.services.ingestion.base import BaseParser, ParseResult, RawLineItem

logger = logging.getLogger(__name__)


class PDFParser(BaseParser):
    """
    PDF invoice parser using pdfplumber.

    NOT YET IMPLEMENTED — see module docstring for activation instructions.
    Wired into the format dispatch so it is impossible to forget.
    """

    def parse(self, data: bytes, filename: str) -> ParseResult:
        """
        Parse PDF bytes into a ParseResult.

        TODO (v2): Implement using pdfplumber.
          - Open PDF from bytes using io.BytesIO
          - Detect tables on each page (pdfplumber.Page.extract_table())
          - Fall back to text extraction if no tables found
          - Normalize rows to RawLineItem using BaseParser utilities
          - Store per-page raw_text in extraction_artifacts

        Known complexity points to address in v2:
          - Multi-page invoices with header-only on page 1
          - Landscape-oriented tables
          - Invoices with sub-total rows (detect and skip)
          - Scanned PDFs (will need OCR — out of scope even for v2)
        """
        raise NotImplementedError(
            f"PDF parsing is not yet implemented. "
            f"File: {filename!r}. "
            f"Please convert your invoice to CSV format for v1. "
            f"PDF support is planned for a future release."
        )

    def _extract_with_pdfplumber(self, data: bytes) -> list[dict]:
        """
        TODO (v2): Extract raw rows from PDF using pdfplumber.

        Implementation sketch:
            import pdfplumber, io
            rows = []
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                for page in pdf.pages:
                    table = page.extract_table()
                    if table:
                        rows.extend(table[1:])  # skip header row
                    # else: fall back to text extraction
            return rows
        """
        raise NotImplementedError("PDF extraction not yet implemented")

    def _normalize_row(self, row: list, header_map: dict) -> Optional[RawLineItem]:
        """
        TODO (v2): Map a raw PDF table row to a RawLineItem.
        header_map: {canonical_name: column_index}
        """
        raise NotImplementedError("PDF row normalization not yet implemented")
