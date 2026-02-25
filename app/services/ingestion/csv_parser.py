"""
CSVParser — parses supplier invoice CSV files into RawLineItems.

Column mapping strategy:
  Each supplier may use different column headers. The parser uses a flexible
  alias map to find the right columns regardless of exact naming.
  If a column cannot be found, it logs a warning and uses a safe default.

Expected (but flexible) columns:
  claim_number, service_date, description, code, quantity, unit, amount

The alias map below covers the most common variations we expect to see
from IME schedulers, IA networks, and engineering firms.
"""

import io
import logging
from decimal import Decimal
from typing import Optional

import pandas as pd

from app.services.ingestion.base import BaseParser, ParseError, ParseResult, RawLineItem

logger = logging.getLogger(__name__)

# ── Column alias map ──────────────────────────────────────────────────────────
# canonical_name: [list of accepted header variants] (all lowercased, stripped)
COLUMN_ALIASES: dict[str, list[str]] = {
    "description": [
        "description",
        "service description",
        "service_description",
        "line description",
        "line_description",
        "desc",
        "service",
        "item",
        "charge description",
        "charge_description",
        "billing description",
    ],
    "amount": [
        "amount",
        "total",
        "total amount",
        "billed amount",
        "billed_amount",
        "charge",
        "fee",
        "invoice amount",
        "gross amount",
        "line total",
        "line_total",
        "extended amount",
        "extended_amount",
    ],
    "quantity": [
        "quantity",
        "qty",
        "units",
        "unit quantity",
        "hours",
        "count",
        "num",
        "number",
        "volume",
    ],
    "unit": [
        "unit",
        "unit type",
        "unit_type",
        "uom",
        "unit of measure",
        "billing unit",
        "rate unit",
    ],
    "code": [
        "code",
        "service code",
        "service_code",
        "billing code",
        "billing_code",
        "procedure code",
        "procedure_code",
        "item code",
        "charge code",
        "cpt",
        "cpt code",
    ],
    "claim_number": [
        "claim number",
        "claim_number",
        "claim",
        "claim no",
        "claim#",
        "claimant number",
        "file number",
        "file_number",
        "file no",
        "ref",
        "reference",
        "reference number",
    ],
    "service_date": [
        "service date",
        "service_date",
        "date of service",
        "dos",
        "date",
        "exam date",
        "inspection date",
        "visit date",
        "transaction date",
        "invoice date",
    ],
}


class CSVParser(BaseParser):
    """
    Parses CSV files (and TSV) into RawLineItems.
    Resilient to column naming variations via COLUMN_ALIASES.
    """

    def parse(self, data: bytes, filename: str) -> ParseResult:
        """Parse CSV bytes into a ParseResult."""
        warnings: list[str] = []

        # ── Detect delimiter ──────────────────────────────────────────────────
        try:
            text = data.decode("utf-8-sig")  # utf-8-sig strips BOM if present
        except UnicodeDecodeError:
            try:
                text = data.decode("latin-1")
                warnings.append("File decoded as latin-1 (not UTF-8)")
            except UnicodeDecodeError:
                raise ParseError(
                    f"Cannot decode file {filename!r} — unsupported encoding"
                )

        delimiter = "\t" if "\t" in text[:2000] else ","

        # ── Load DataFrame ────────────────────────────────────────────────────
        try:
            df = pd.read_csv(
                io.StringIO(text),
                delimiter=delimiter,
                dtype=str,  # Read everything as string; we convert manually
                keep_default_na=False,  # Don't auto-convert '' to NaN
                skip_blank_lines=True,
            )
        except Exception as exc:
            raise ParseError(f"pandas failed to parse {filename!r}: {exc}") from exc

        if df.empty:
            raise ParseError(f"File {filename!r} contains no data rows")

        # ── Normalize column headers ──────────────────────────────────────────
        df.columns = [col.strip().lower() for col in df.columns]
        col_map = self._build_column_map(df.columns.tolist(), warnings)

        # ── Parse rows ────────────────────────────────────────────────────────
        line_items: list[RawLineItem] = []
        raw_text_lines: list[str] = [text[:5000]]  # Store sample for artifact

        for idx, row in df.iterrows():
            row_number = int(idx) + 2  # 1-based + header row
            row_warnings: list[str] = []

            try:
                raw_amount = self._get_decimal(row, col_map, "amount", row_number)
                raw_description = (
                    self._get_str(row, col_map, "description")
                    or f"(no description - row {row_number})"
                )

                item = RawLineItem(
                    line_number=row_number
                    - 1,  # 1-based line number (excluding header)
                    raw_description=raw_description,
                    raw_amount=raw_amount,
                    raw_quantity=self._get_decimal(
                        row, col_map, "quantity", row_number, default=Decimal("1")
                    ),
                    raw_unit=self._get_str(row, col_map, "unit"),
                    raw_code=self._get_str(row, col_map, "code"),
                    claim_number=self._get_str(row, col_map, "claim_number"),
                    service_date=self._get_date(row, col_map, "service_date"),
                    extraction_notes=row_warnings,
                )
                line_items.append(item)

            except ParseError as exc:
                warnings.append(f"Row {row_number} skipped: {exc}")
                logger.warning("Skipping row %d in %s: %s", row_number, filename, exc)
                continue

        if not line_items:
            raise ParseError(f"No valid line items found in {filename!r}")

        logger.info(
            "CSVParser: parsed %d line items from %s", len(line_items), filename
        )

        return ParseResult(
            line_items=line_items,
            raw_text="\n".join(raw_text_lines),
            extraction_method="csv",
            warnings=warnings,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_column_map(
        self, actual_cols: list[str], warnings: list[str]
    ) -> dict[str, Optional[str]]:
        """
        Map canonical column names to actual column names found in the file.
        Returns dict[canonical_name] -> actual_col_name | None
        """
        col_map: dict[str, Optional[str]] = {}
        for canonical, aliases in COLUMN_ALIASES.items():
            found = None
            for actual in actual_cols:
                if actual in aliases or actual == canonical:
                    found = actual
                    break
            if found is None and canonical in ("description", "amount"):
                # These two are non-negotiable
                warnings.append(
                    f"Required column '{canonical}' not found. "
                    f"Available: {actual_cols}. "
                    f"Accepted aliases: {aliases}"
                )
            elif found is None:
                logger.debug("Optional column '%s' not found in file", canonical)
            col_map[canonical] = found
        return col_map

    def _get_str(self, row: pd.Series, col_map: dict, canonical: str) -> Optional[str]:
        col = col_map.get(canonical)
        if col is None or col not in row:
            return None
        return self.clean_str(row[col])

    def _get_decimal(
        self,
        row: pd.Series,
        col_map: dict,
        canonical: str,
        row_number: int,
        default: Optional[Decimal] = None,
    ) -> Decimal:
        col = col_map.get(canonical)
        if col is None or col not in row:
            if default is not None:
                return default
            raise ParseError(f"Column '{canonical}' is missing and has no default")
        raw = row[col]
        if not raw or str(raw).strip() == "":
            if default is not None:
                return default
            raise ParseError(f"Column '{canonical}' is empty in row {row_number}")
        return self.to_decimal(raw)

    def _get_date(self, row: pd.Series, col_map: dict, canonical: str):
        col = col_map.get(canonical)
        if col is None or col not in row:
            return None
        return self.to_date(row[col])
