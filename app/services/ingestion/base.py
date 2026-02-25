"""
Ingestion abstractions — raw extraction types and the BaseParser interface.

RawLineItem is the canonical normalized row that all parsers must produce.
Everything downstream operates on RawLineItem — parsers are the only
layer that knows about file formats.
"""

import abc
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional


@dataclass
class RawLineItem:
    """
    A single normalized line extracted from a supplier invoice file.

    'Raw' means: amounts/quantities are normalized to Decimal,
    dates to date objects, strings stripped — but no classification
    or validation has occurred yet.
    """
    line_number: int
    raw_description: str
    raw_amount: Decimal
    raw_quantity: Decimal
    raw_unit: Optional[str]
    raw_code: Optional[str]          # Supplier's own billing code, if present
    claim_number: Optional[str]
    service_date: Optional[date]
    extraction_notes: list[str] = field(default_factory=list)  # Parser warnings


@dataclass
class ParseResult:
    """Result of parsing a single file."""
    line_items: list[RawLineItem]
    raw_text: str                    # Full extracted text (for RawExtractionArtifact)
    extraction_method: str           # "csv" | "pdfplumber" | etc.
    warnings: list[str] = field(default_factory=list)
    page_count: Optional[int] = None  # PDF only


class ParseError(Exception):
    """Raised when a file cannot be parsed (bad format, encoding error, etc.)."""
    pass


class BaseParser(abc.ABC):
    """
    Abstract parser interface. One concrete implementation per file format.

    All parsers receive raw bytes and return a ParseResult.
    They must never write to the database — that is the worker's job.
    """

    @abc.abstractmethod
    def parse(self, data: bytes, filename: str) -> ParseResult:
        """
        Parse file bytes into normalized RawLineItems.

        Args:
            data: Raw file bytes.
            filename: Original filename (used for format hints).

        Returns:
            ParseResult with normalized line items.

        Raises:
            ParseError: If the file cannot be parsed.
        """

    # ── Shared utilities for subclasses ──────────────────────────────────────

    @staticmethod
    def to_decimal(value: object) -> Decimal:
        """Safely convert a value to Decimal. Raises ParseError on failure."""
        if isinstance(value, Decimal):
            return value
        try:
            cleaned = str(value).strip().replace(",", "").replace("$", "").replace(" ", "")
            if not cleaned:
                raise ParseError(f"Cannot convert empty value to Decimal")
            return Decimal(cleaned)
        except InvalidOperation:
            raise ParseError(f"Cannot convert {value!r} to a monetary Decimal")

    @staticmethod
    def to_date(value: object) -> Optional[date]:
        """Attempt to parse a date from various string formats. Returns None on failure."""
        if value is None or str(value).strip() in ("", "nan", "NaT", "None"):
            return None
        if isinstance(value, date):
            return value
        from dateutil import parser as date_parser
        try:
            return date_parser.parse(str(value)).date()
        except (ValueError, OverflowError):
            return None

    @staticmethod
    def clean_str(value: object) -> Optional[str]:
        """Strip and normalize a string value; return None if empty."""
        if value is None:
            return None
        s = str(value).strip()
        return s if s and s.lower() not in ("nan", "none", "n/a", "") else None
