"""
Parser dispatcher — routes file bytes to the correct parser by format.
"""

from app.services.ingestion.base import BaseParser, ParseError
from app.services.ingestion.csv_parser import CSVParser
from app.services.ingestion.pdf_parser import PDFParser

_PARSERS: dict[str, BaseParser] = {
    "csv": CSVParser(),
    "pdf": PDFParser(),  # Stubbed — raises NotImplementedError until v2
}


def get_parser(file_format: str) -> BaseParser:
    """Return the parser for the given format string ('csv' or 'pdf')."""
    parser = _PARSERS.get(file_format.lower())
    if parser is None:
        supported = list(_PARSERS.keys())
        raise ParseError(
            f"Unsupported file format: {file_format!r}. Supported: {supported}"
        )
    return parser


def detect_format(filename: str) -> str:
    """
    Detect file format from extension.
    Returns 'csv' or 'pdf'. Raises ParseError for unsupported extensions.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in ("csv", "tsv"):
        return "csv"
    elif ext == "pdf":
        return "pdf"
    elif ext in ("xlsx", "xls"):
        # Future: wire up an Excel parser
        raise ParseError(
            "Excel files (.xlsx/.xls) are not yet supported. "
            "Please export your invoice as CSV."
        )
    else:
        raise ParseError(
            f"Cannot determine file format from filename {filename!r}. "
            f"Supported extensions: .csv, .tsv, .pdf"
        )
