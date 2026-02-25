"""
Invoice Processing Pipeline.

Supports two entry points:
  - process_invoice_sync(): called directly from the upload endpoint (MVP default).
    Uses the caller's DB session and file bytes already in memory.
  - process_invoice():      legacy RQ background job entry point.
    Opens its own DB session and loads file from storage.

Pipeline steps:
  1. Set invoice status = PROCESSING
  2. Parse file → RawLineItems
  3. Store RawExtractionArtifact
  4. For each RawLineItem:
     a. Create LineItem (PENDING)
     b. Classify → taxonomy_code + confidence (CLASSIFIED)
     c. Run rate validation → ValidationResults
     d. Run guideline validation → ValidationResults
     e. Create ExceptionRecords for failures
     f. Update LineItem status (VALIDATED or EXCEPTION)
  5. Update Invoice status:
     - Any ERROR exceptions → REVIEW_REQUIRED
     - All PASS/WARNING     → PENDING_CARRIER_REVIEW
  6. Write audit events throughout
"""

import logging
import uuid

from app.database import SessionLocal
from app.models.invoice import (
    Invoice,
    InvoiceVersion,
    LineItem,
    LineItemStatus,
    RawExtractionArtifact,
    SubmissionStatus,
)
from app.models.validation import (
    ExceptionRecord,
    ExceptionStatus,
    RequiredAction,
    ValidationResult,
    ValidationSeverity,
    ValidationStatus,
    ValidationType,
)
from app.services.audit import logger as audit
from app.services.classification.classifier import Classifier
from app.services.ingestion.base import ParseError, RawLineItem
from app.services.ingestion.dispatcher import detect_format, get_parser
from app.services.storage.base import get_storage
from app.services.validation.guideline_validator import GuidelineValidator
from app.services.validation.rate_validator import RateValidator

logger = logging.getLogger(__name__)


# ── Public entry points ────────────────────────────────────────────────────────


def process_invoice_sync(
    invoice_id: str,
    file_bytes: bytes,
    filename: str,
    db,
) -> dict:
    """
    Synchronous pipeline — called directly from the upload endpoint.

    Receives file bytes already in memory (no disk read required), and uses
    the caller's DB session so everything commits in one transaction.

    Args:
        invoice_id: String UUID of the Invoice to process.
        file_bytes: Raw file content already in memory.
        filename:   Original filename (used for format detection).
        db:         Caller-provided SQLAlchemy session.

    Returns:
        Summary dict with processing results.
    """
    inv_uuid = uuid.UUID(invoice_id)
    logger.info("Starting invoice pipeline (sync) for %s", invoice_id)

    invoice = db.get(Invoice, inv_uuid)
    if invoice is None:
        logger.error("Invoice %s not found", invoice_id)
        return {"error": "Invoice not found", "invoice_id": invoice_id}

    try:
        # ── Set status → PROCESSING ───────────────────────────────────────────
        old_status = invoice.status
        invoice.status = SubmissionStatus.PROCESSING
        db.flush()
        audit.log_invoice_status_changed(
            db, invoice, from_status=old_status, to_status=SubmissionStatus.PROCESSING
        )

        # ── Parse file (bytes already in memory — no disk read) ───────────────
        try:
            file_format = detect_format(filename)
            parser = get_parser(file_format)
            parse_result = parser.parse(file_bytes, filename)
        except ParseError as exc:
            return _fail_invoice(db, invoice, str(exc))
        except NotImplementedError as exc:
            return _fail_invoice(db, invoice, str(exc))

        return _run_pipeline(db, invoice, parse_result)

    except Exception:
        db.rollback()
        logger.exception("Unhandled error processing invoice %s (sync)", invoice_id)
        raise


def process_invoice(invoice_id: str) -> dict:
    """
    RQ background job entry point (legacy — used when worker service is enabled).

    Args:
        invoice_id: String UUID of the Invoice to process.

    Returns:
        Summary dict (stored as RQ job result).
    """
    inv_uuid = uuid.UUID(invoice_id)
    logger.info("Starting invoice pipeline (async) for %s", invoice_id)

    db = SessionLocal()
    try:
        invoice = db.get(Invoice, inv_uuid)
        if invoice is None:
            logger.error("Invoice %s not found", invoice_id)
            return {"error": "Invoice not found", "invoice_id": invoice_id}

        # ── Set status → PROCESSING ───────────────────────────────────────────
        old_status = invoice.status
        invoice.status = SubmissionStatus.PROCESSING
        db.flush()
        audit.log_invoice_status_changed(
            db, invoice, from_status=old_status, to_status=SubmissionStatus.PROCESSING
        )

        # ── Load file from storage ────────────────────────────────────────────
        storage = get_storage()
        try:
            file_bytes = storage.load(invoice.raw_file_path)
        except Exception as exc:
            return _fail_invoice(db, invoice, f"Could not load invoice file: {exc}")

        # ── Parse file ────────────────────────────────────────────────────────
        filename = invoice.raw_file_path.rsplit("/", 1)[-1]
        try:
            file_format = detect_format(filename)
            parser = get_parser(file_format)
            parse_result = parser.parse(file_bytes, filename)
        except ParseError as exc:
            return _fail_invoice(db, invoice, str(exc))
        except NotImplementedError as exc:
            return _fail_invoice(db, invoice, str(exc))

        return _run_pipeline(db, invoice, parse_result)

    except Exception:
        db.rollback()
        logger.exception("Unhandled error processing invoice %s", invoice_id)
        try:
            invoice = db.get(Invoice, inv_uuid)
            if invoice and invoice.status == SubmissionStatus.PROCESSING:
                invoice.status = SubmissionStatus.SUBMITTED
                db.commit()
        except Exception:
            pass
        raise
    finally:
        db.close()


# ── Core pipeline ──────────────────────────────────────────────────────────────


def _run_pipeline(db, invoice, parse_result) -> dict:
    """
    Shared pipeline logic used by both sync and async entry points.
    Runs from post-parse through to final invoice status commit.
    """
    invoice_id = str(invoice.id)

    # ── Store extraction artifact ─────────────────────────────────────────────
    version = (
        db.query(InvoiceVersion)
        .filter_by(
            invoice_id=invoice.id,
            version_number=invoice.current_version,
        )
        .first()
    )

    if version:
        artifact = RawExtractionArtifact(
            invoice_version_id=version.id,
            raw_text=parse_result.raw_text[:50000],
            extraction_method=parse_result.extraction_method,
            extraction_metadata={
                "warnings": parse_result.warnings,
                "line_count": len(parse_result.line_items),
            },
        )
        db.add(artifact)

    # ── Load contract + guidelines ────────────────────────────────────────────
    contract = invoice.contract
    if contract is None:
        return _fail_invoice(db, invoice, "Contract not found for invoice")

    guidelines = [g for g in contract.guidelines if g.is_active]

    # ── Instantiate services ──────────────────────────────────────────────────
    classifier = Classifier(db)
    rate_validator = RateValidator(db)
    guideline_validator = GuidelineValidator()

    # ── Process each line item ────────────────────────────────────────────────
    error_count = 0
    warning_count = 0
    pass_count = 0
    total_expected = 0

    for raw_item in parse_result.line_items:
        line_item, item_errors, item_warnings, item_expected = _process_line(
            db=db,
            raw_item=raw_item,
            invoice=invoice,
            contract=contract,
            guidelines=guidelines,
            classifier=classifier,
            rate_validator=rate_validator,
            guideline_validator=guideline_validator,
        )
        error_count += item_errors
        warning_count += item_warnings
        if item_errors == 0:
            pass_count += 1
        total_expected += item_expected

    db.flush()

    # ── Determine final invoice status ────────────────────────────────────────
    new_status = (
        SubmissionStatus.REVIEW_REQUIRED
        if error_count > 0
        else SubmissionStatus.PENDING_CARRIER_REVIEW
    )
    old_status = invoice.status
    invoice.status = new_status
    db.flush()

    audit.log_invoice_status_changed(
        db, invoice, from_status=old_status, to_status=new_status
    )

    db.commit()

    summary = {
        "invoice_id": invoice_id,
        "status": new_status,
        "lines_processed": len(parse_result.line_items),
        "lines_pass": pass_count,
        "lines_error": error_count,
        "lines_warning": warning_count,
        "parse_warnings": parse_result.warnings,
    }
    logger.info("Invoice %s processed: %s", invoice_id, summary)
    return summary


# ── Line-item processor ────────────────────────────────────────────────────────


def _process_line(
    db,
    raw_item: RawLineItem,
    invoice,
    contract,
    guidelines,
    classifier,
    rate_validator,
    guideline_validator,
) -> tuple[LineItem, int, int, float]:
    """
    Process a single raw line item through the full pipeline.
    Returns (line_item, error_count, warning_count, expected_amount).
    """
    error_count = 0
    warning_count = 0

    # ── Create LineItem (PENDING) ─────────────────────────────────────────────
    line_item = LineItem(
        invoice_id=invoice.id,
        invoice_version=invoice.current_version,
        line_number=raw_item.line_number,
        status=LineItemStatus.PENDING,
        raw_description=raw_item.raw_description,
        raw_code=raw_item.raw_code,
        raw_amount=raw_item.raw_amount,
        raw_quantity=raw_item.raw_quantity,
        raw_unit=raw_item.raw_unit,
        claim_number=raw_item.claim_number,
        service_date=raw_item.service_date,
    )
    db.add(line_item)
    db.flush()

    # ── Classify ──────────────────────────────────────────────────────────────
    try:
        result = classifier.classify(
            raw_description=raw_item.raw_description,
            raw_code=raw_item.raw_code,
            supplier_id=invoice.supplier_id,
        )
        line_item.taxonomy_code = result.taxonomy_code
        line_item.billing_component = result.billing_component
        line_item.mapping_confidence = (
            result.confidence if result.confidence != "UNRECOGNIZED" else "LOW"
        )
        line_item.mapping_rule_id = (
            uuid.UUID(result.matched_rule_id) if result.matched_rule_id else None
        )
        line_item.status = LineItemStatus.CLASSIFIED
        audit.log_line_item_classified(db, line_item, result)

        if result.confidence == "UNRECOGNIZED":
            val_result = ValidationResult(
                line_item_id=line_item.id,
                validation_type=ValidationType.CLASSIFICATION,
                status=ValidationStatus.FAIL,
                severity=ValidationSeverity.ERROR,
                message=(
                    f"Service description could not be classified: "
                    f"'{raw_item.raw_description}'. "
                    f"Please provide a clearer description or request manual "
                    f"reclassification."
                ),
                required_action=RequiredAction.REQUEST_RECLASSIFICATION,
            )
            db.add(val_result)
            db.flush()
            exc_record = ExceptionRecord(
                line_item_id=line_item.id,
                validation_result_id=val_result.id,
                status=ExceptionStatus.OPEN,
            )
            db.add(exc_record)
            line_item.status = LineItemStatus.EXCEPTION
            error_count += 1
            return line_item, error_count, warning_count, 0

    except Exception as exc:
        logger.error("Classification failed for line %d: %s", raw_item.line_number, exc)
        line_item.status = LineItemStatus.EXCEPTION
        error_count += 1
        return line_item, error_count, warning_count, 0

    # ── Rate validation ────────────────────────────────────────────────────────
    rate_results = rate_validator.validate(line_item, contract)
    expected_amount = float(raw_item.raw_amount)

    for rate_result in rate_results:
        val = ValidationResult(
            line_item_id=line_item.id,
            validation_type=rate_result.validation_type,
            rate_card_id=uuid.UUID(rate_result.rate_card_id)
            if rate_result.rate_card_id
            else None,
            status=rate_result.status,
            severity=rate_result.severity,
            message=rate_result.message,
            expected_value=rate_result.expected_value,
            actual_value=rate_result.actual_value,
            required_action=rate_result.required_action,
        )
        db.add(val)
        db.flush()

        if rate_result.status == ValidationStatus.FAIL:
            exc_record = ExceptionRecord(
                line_item_id=line_item.id,
                validation_result_id=val.id,
                status=ExceptionStatus.OPEN,
            )
            db.add(exc_record)
            audit.log_line_item_exception_opened(db, line_item, rate_result)
            error_count += 1
            if rate_result.expected_value:
                try:
                    expected_amount = float(
                        rate_result.expected_value.replace("$", "").replace(",", "")
                    )
                except (ValueError, AttributeError):
                    pass
        elif rate_result.status == ValidationStatus.WARNING:
            warning_count += 1

    # ── Guideline validation ───────────────────────────────────────────────────
    guide_results = guideline_validator.validate(line_item, guidelines)

    for guide_result in guide_results:
        val = ValidationResult(
            line_item_id=line_item.id,
            validation_type=guide_result.validation_type,
            guideline_id=uuid.UUID(guide_result.guideline_id)
            if guide_result.guideline_id
            else None,
            status=guide_result.status,
            severity=guide_result.severity,
            message=guide_result.message,
            expected_value=guide_result.expected_value,
            actual_value=guide_result.actual_value,
            required_action=guide_result.required_action,
        )
        db.add(val)
        db.flush()

        if guide_result.status == ValidationStatus.FAIL:
            exc_record = ExceptionRecord(
                line_item_id=line_item.id,
                validation_result_id=val.id,
                status=ExceptionStatus.OPEN,
            )
            db.add(exc_record)
            audit.log_line_item_exception_opened(db, line_item, guide_result)
            error_count += 1
        elif guide_result.status == ValidationStatus.WARNING:
            warning_count += 1

    # ── Set final line item status ─────────────────────────────────────────────
    line_item.status = (
        LineItemStatus.EXCEPTION if error_count > 0 else LineItemStatus.VALIDATED
    )
    line_item.expected_amount = expected_amount

    return line_item, error_count, warning_count, expected_amount


# ── Helpers ────────────────────────────────────────────────────────────────────


def _fail_invoice(db, invoice, reason: str) -> dict:
    """Mark invoice as REVIEW_REQUIRED and return error summary."""
    logger.error("Invoice %s pipeline failed: %s", invoice.id, reason)
    try:
        invoice.status = SubmissionStatus.REVIEW_REQUIRED
        db.commit()
    except Exception:
        db.rollback()
    return {"error": reason, "invoice_id": str(invoice.id)}
