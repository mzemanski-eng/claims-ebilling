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
     - All PASS/WARNING     → APPROVED (if auto_approve_clean_invoices)
                            → PENDING_CARRIER_REVIEW (if manual approval required)
  6. Write audit events throughout
"""

import logging
import uuid
from datetime import date, datetime, timezone

from app.database import SessionLocal
from app.taxonomy.vertical_config import VerticalConfig
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
from app.services.ai_assessment.classification_suggester import suggest_classification
from app.services.ai_assessment.description_assessor import assess_description_alignment
from app.services.audit import logger as audit
from app.services.classification.classifier import Classifier
from app.services.ingestion.base import ParseError, RawLineItem
from app.services.ingestion.dispatcher import detect_format, get_parser
from app.services.storage.base import get_storage
from app.services.ai_assessment.exception_resolver import assess_exception
from app.services.ai_assessment.invoice_triage import triage_invoice
from app.services.notifications.email import (
    notify_invoice_approved,
    notify_invoice_flagged,
)
from app.services.validation.guideline_validator import GuidelineValidator
from app.services.validation.rate_validator import RateValidator
from app.settings import settings
from app.schemas.carrier_settings import CarrierSettings

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


def process_invoice(invoice_id: str, file_bytes: bytes, filename: str) -> dict:
    """
    RQ background job entry point.

    File bytes are received directly as a job argument (passed through Redis at
    enqueue time) — no disk read is required on the worker. This removes any
    shared-disk dependency between the web service and the worker service.

    Args:
        invoice_id: String UUID of the Invoice to process.
        file_bytes: Raw file content (passed from the upload endpoint via Redis).
        filename:   Original filename for format detection.

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

        # ── Parse file (bytes received from RQ job args) ──────────────────────
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
        logger.exception("Unhandled error processing invoice %s (async)", invoice_id)
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

    # ── Load contract + carrier settings ─────────────────────────────────────
    contract = invoice.contract
    if contract is None:
        return _fail_invoice(db, invoice, "Contract not found for invoice")

    # Resolve effective per-carrier settings (falls back to platform defaults).
    _raw_cs = (contract.carrier.settings or {}) if contract.carrier else {}
    cs = CarrierSettings.model_validate(_raw_cs)

    # Detect vertical for per-vertical AI prompt routing.
    # Falls back to "default" if contract has no vertical assigned.
    vertical = VerticalConfig.from_contract(contract).slug

    # ── Verify the contract is active and currently effective ─────────────────
    today = date.today()
    if not contract.is_active:
        return _fail_invoice(
            db,
            invoice,
            f"Contract '{contract.name}' is inactive. "
            "An executed, active contract is required to process invoices.",
        )
    if contract.effective_from > today:
        return _fail_invoice(
            db,
            invoice,
            f"Contract '{contract.name}' is not yet effective "
            f"(effective from {contract.effective_from}). "
            "Invoice cannot be processed until the contract effective date.",
        )
    if contract.effective_to is not None and contract.effective_to < today:
        return _fail_invoice(
            db,
            invoice,
            f"Contract '{contract.name}' expired on {contract.effective_to}. "
            "A current, executed contract is required to process invoices.",
        )

    guidelines = [g for g in contract.guidelines if g.is_active]

    # ── AI invoice triage (non-blocking) ──────────────────────────────────────
    try:
        prior_rr_count = _prior_review_required_count(db, invoice.supplier_id)
        estimated_total = sum(
            float(item.raw_amount or 0) for item in parse_result.line_items
        )
        triage_result = triage_invoice(
            supplier_name=invoice.supplier.name,
            invoice_number=invoice.invoice_number,
            invoice_date=str(invoice.invoice_date),
            line_item_count=len(parse_result.line_items),
            estimated_total=estimated_total,
            prior_review_required_count=prior_rr_count,
            vertical=vertical,
        )
        if triage_result:
            invoice.triage_risk_level = triage_result["risk_level"]
            invoice.triage_notes = "\n".join(triage_result.get("risk_factors", []))
            db.flush()
            logger.info(
                "Invoice %s triage: %s (%d risk factors)",
                invoice_id,
                triage_result["risk_level"],
                len(triage_result.get("risk_factors", [])),
            )
    except Exception as triage_exc:
        logger.warning("Invoice triage failed for %s: %s", invoice_id, triage_exc)

    # ── Instantiate services ──────────────────────────────────────────────────
    classifier = Classifier(db)
    rate_validator = RateValidator(db)
    guideline_validator = GuidelineValidator()

    # ── Process each line item ────────────────────────────────────────────────
    error_count = 0
    # Tracks only RATE / GUIDELINE failures (not classification).
    # Classification failures affect line status (EXCEPTION) but do NOT trigger
    # REVIEW_REQUIRED — those invoices land in PENDING_CARRIER_REVIEW so the
    # carrier ops team can confirm taxonomy without the supplier being notified.
    spend_error_count = 0
    warning_count = 0
    pass_count = 0
    total_expected = 0
    processed_lines: list = []

    for raw_item in parse_result.line_items:
        line_item, item_errors, item_spend_errors, item_warnings, item_expected = _process_line(
            db=db,
            raw_item=raw_item,
            invoice=invoice,
            contract=contract,
            guidelines=guidelines,
            classifier=classifier,
            rate_validator=rate_validator,
            guideline_validator=guideline_validator,
            vertical=vertical,
        )
        processed_lines.append(line_item)
        error_count += item_errors
        spend_error_count += item_spend_errors
        warning_count += item_warnings
        if item_errors == 0:
            pass_count += 1
        total_expected += item_expected

    db.flush()

    # ── Invoice-level exclusivity guideline checks ────────────────────────────
    # invoice_codes_exclusive rules fire when mutually exclusive service codes
    # appear on the same invoice (e.g. LA service hierarchy: only one of
    # Harness Inspection / Roof Inspection / Ladder Access per visit).
    excl_pairs = guideline_validator.validate_invoice_exclusivity(
        processed_lines, guidelines
    )
    for anchor_line, excl_result in excl_pairs:
        excl_val = ValidationResult(
            line_item_id=anchor_line.id,
            validation_type=excl_result.validation_type,
            guideline_id=uuid.UUID(excl_result.guideline_id)
            if excl_result.guideline_id
            else None,
            status=excl_result.status,
            severity=excl_result.severity,
            message=excl_result.message,
            expected_value=excl_result.expected_value,
            actual_value=excl_result.actual_value,
            required_action=excl_result.required_action,
        )
        db.add(excl_val)
        db.flush()

        if excl_result.status == ValidationStatus.FAIL:
            exc_record = ExceptionRecord(
                line_item_id=anchor_line.id,
                validation_result_id=excl_val.id,
                status=ExceptionStatus.OPEN,
            )
            db.add(exc_record)
            audit.log_line_item_exception_opened(db, anchor_line, excl_result)
            if anchor_line.status == LineItemStatus.VALIDATED:
                anchor_line.status = LineItemStatus.EXCEPTION
            error_count += 1
            spend_error_count += 1  # guideline exclusivity = spend error
        elif excl_result.status == ValidationStatus.WARNING:
            warning_count += 1

    # ── Invoice-level percentage guideline checks ─────────────────────────────
    # max_pct_of_invoice rules need the full line list; they are deliberately
    # skipped during the per-line loop above and evaluated here instead.
    pct_pairs = guideline_validator.validate_invoice_percentages(
        processed_lines, guidelines
    )
    for anchor_line, pct_result in pct_pairs:
        pct_val = ValidationResult(
            line_item_id=anchor_line.id,
            validation_type=pct_result.validation_type,
            guideline_id=uuid.UUID(pct_result.guideline_id)
            if pct_result.guideline_id
            else None,
            status=pct_result.status,
            severity=pct_result.severity,
            message=pct_result.message,
            expected_value=pct_result.expected_value,
            actual_value=pct_result.actual_value,
            required_action=pct_result.required_action,
        )
        db.add(pct_val)
        db.flush()

        if pct_result.status == ValidationStatus.FAIL:
            exc_record = ExceptionRecord(
                line_item_id=anchor_line.id,
                validation_result_id=pct_val.id,
                status=ExceptionStatus.OPEN,
            )
            db.add(exc_record)
            audit.log_line_item_exception_opened(db, anchor_line, pct_result)
            # Promote line to EXCEPTION if it had previously passed per-line checks
            if anchor_line.status == LineItemStatus.VALIDATED:
                anchor_line.status = LineItemStatus.EXCEPTION
            error_count += 1
            spend_error_count += 1  # percentage guideline = spend error
        elif pct_result.status == ValidationStatus.WARNING:
            warning_count += 1

    # ── Determine final invoice status ────────────────────────────────────────
    # spend_error_count > 0  → REVIEW_REQUIRED (billing dispute; supplier notified)
    # spend_error_count == 0, error_count > 0 → classification-only exceptions;
    #   HIGH/MEDIUM AI confidence → auto-resolve + APPROVED (no human needed)
    #   LOW confidence or no suggestion → PENDING_CARRIER_REVIEW (carrier confirms)
    # error_count == 0 → PENDING_CARRIER_REVIEW (auto-approve if setting enabled)
    if spend_error_count > 0:
        new_status = SubmissionStatus.REVIEW_REQUIRED

    elif error_count > 0:
        # Classification-only exceptions. Auto-resolve when every flagged line
        # has a HIGH or MEDIUM confidence AI suggestion — no billing dispute
        # exists and the AI is confident in the mapping, so human review adds no value.
        # Suppressed when carrier has set ai_classification_mode = "supervised".
        _HIGH_CONF = {"HIGH", "MEDIUM"}
        can_auto_resolve = cs.ai_classification_mode != "supervised" and all(
            line.status != LineItemStatus.EXCEPTION
            or (
                isinstance(line.ai_classification_suggestion, dict)
                and line.ai_classification_suggestion.get("confidence") in _HIGH_CONF
            )
            for line in processed_lines
        )
        if can_auto_resolve:
            now = datetime.now(timezone.utc)
            for line in processed_lines:
                if line.status == LineItemStatus.EXCEPTION:
                    suggestion = line.ai_classification_suggestion or {}
                    conf_label = suggestion.get("confidence", "HIGH")
                    suggested_code = suggestion.get("suggested_code") or "—"
                    for exc in line.exceptions:
                        if exc.status == ExceptionStatus.OPEN:
                            exc.status = ExceptionStatus.RESOLVED
                            exc.resolution_action = "RECLASSIFIED"
                            exc.resolution_notes = (
                                f"Auto-resolved by AI classification pipeline "
                                f"(confidence: {conf_label}, "
                                f"suggested code: {suggested_code})."
                            )
                            exc.resolved_at = now
                    # ── Write AI suggestion onto the line item (was missing) ────
                    # Without this, approved lines have taxonomy_code=NULL and
                    # mapping_confidence=LOW, breaking analytics and the review queue.
                    if suggestion.get("suggested_code"):
                        line.taxonomy_code = suggestion["suggested_code"]
                        line.billing_component = (
                            suggestion.get("suggested_billing_component") or ""
                        )
                        line.mapping_confidence = conf_label  # LOW → HIGH or MEDIUM
                    line.status = LineItemStatus.APPROVED
                elif line.status == LineItemStatus.VALIDATED:
                    line.status = LineItemStatus.APPROVED
            db.flush()

            # ── Write confirmed mappings to the MappingRule corpus ────────────
            # Classifier checks MappingRule first, so these rules immediately
            # improve accuracy for future invoices from the same supplier.
            from app.services.classification.mapping_learner import record_confirmed_mapping
            from app.models.mapping import ConfirmedBy

            for line in processed_lines:
                if line.status == LineItemStatus.APPROVED:
                    sug = line.ai_classification_suggestion
                    if (
                        sug
                        and sug.get("verdict") == "SUGGESTED"
                        and sug.get("suggested_code")
                    ):
                        record_confirmed_mapping(
                            db=db,
                            line_item=line,
                            taxonomy_code=sug["suggested_code"],
                            billing_component=sug.get("suggested_billing_component") or "",
                            source=ConfirmedBy.SYSTEM,
                            scope="this_supplier",
                        )

            new_status = SubmissionStatus.APPROVED
            logger.info(
                "Invoice %s auto-approved: classification exceptions auto-resolved "
                "(all lines had HIGH/MEDIUM AI confidence)",
                invoice_id,
            )
        else:
            new_status = SubmissionStatus.PENDING_CARRIER_REVIEW
            logger.info(
                "Invoice %s → PENDING_CARRIER_REVIEW: classification exceptions "
                "need carrier confirmation (low-confidence or missing AI suggestion)",
                invoice_id,
            )

    else:
        new_status = SubmissionStatus.PENDING_CARRIER_REVIEW

    # ── Auto-approve fully clean invoices (if configured) ─────────────────────
    # Only applies when error_count == 0 (no classification or spend errors).
    # The high-confidence classification path above handles its own approval.
    #
    # Effective auto_approve is resolved in priority order:
    #   1. carrier.settings.auto_approve_clean_invoices  (per-carrier override)
    #   2. settings.auto_approve_clean_invoices          (platform default)
    #
    # Amount guards applied on top of the flag:
    #   auto_approve_max_amount:      only auto-approve when total ≤ limit
    #   require_review_above_amount:  always review when total > threshold
    _eff_auto_approve = (
        cs.auto_approve_clean_invoices
        if cs.auto_approve_clean_invoices is not None
        else settings.auto_approve_clean_invoices
    )

    if _eff_auto_approve and (cs.auto_approve_max_amount is not None or cs.require_review_above_amount is not None):
        _invoice_total = float(
            sum(line.raw_amount or 0 for line in processed_lines)
        )
        if cs.require_review_above_amount is not None and _invoice_total > cs.require_review_above_amount:
            _eff_auto_approve = False
        elif cs.auto_approve_max_amount is not None and _invoice_total > cs.auto_approve_max_amount:
            _eff_auto_approve = False

    if (
        new_status == SubmissionStatus.PENDING_CARRIER_REVIEW
        and error_count == 0
        and _eff_auto_approve
    ):
        new_status = SubmissionStatus.APPROVED
        for line in processed_lines:
            if line.status == LineItemStatus.VALIDATED:
                line.status = LineItemStatus.APPROVED
        logger.info(
            "Invoice %s auto-approved: %d lines approved, %d warnings present",
            invoice_id,
            pass_count,
            warning_count,
        )

    old_status = invoice.status
    invoice.status = new_status
    invoice.processed_at = datetime.now(timezone.utc)
    db.flush()

    audit.log_invoice_status_changed(
        db, invoice, from_status=old_status, to_status=new_status
    )

    db.commit()

    # ── Supplier notifications (non-blocking — never raises) ──────────────────
    if new_status == SubmissionStatus.REVIEW_REQUIRED:
        notify_invoice_flagged(db, invoice)
    elif new_status == SubmissionStatus.APPROVED:
        notify_invoice_approved(db, invoice)
    # PENDING_CARRIER_REVIEW intentionally sends no notification — no action
    # is needed from the supplier at this stage and a "we're reviewing it"
    # email provides no value and adds noise to their inbox.

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
    vertical: str = "default",
) -> tuple[LineItem, int, int, int, float]:
    """
    Process a single raw line item through the full pipeline.
    Returns (line_item, error_count, spend_error_count, warning_count, expected_amount).
    error_count       — all failures (classification + rate + guideline); drives line EXCEPTION status.
    spend_error_count — only rate / guideline failures; drives invoice REVIEW_REQUIRED status.
    """
    error_count = 0
    spend_error_count = 0
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
        service_state=raw_item.service_state,
        service_zip=raw_item.service_zip,
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
            # ── AI classification suggestion (runs BEFORE deciding to exception) ─
            # We ask the AI suggester first. If it returns HIGH or MEDIUM confidence
            # we accept the taxonomy inline and fall through to rate/guideline
            # validation — decoupling classification from spend audit so these lines
            # aren't held in dispute just because the rule engine didn't recognise them.
            # LOW confidence or no suggestion → flag for carrier review as before.
            suggestion = None
            try:
                suggestion = suggest_classification(
                    raw_description=raw_item.raw_description,
                    raw_code=raw_item.raw_code,
                    vertical=vertical,
                )
                if suggestion:
                    line_item.ai_classification_suggestion = suggestion
            except Exception as ai_exc:
                logger.warning(
                    "AI classification suggestion skipped for line %d: %s",
                    raw_item.line_number,
                    ai_exc,
                )

            _AUTO_CONF = {"HIGH", "MEDIUM"}
            auto_accepted = (
                isinstance(suggestion, dict)
                and suggestion.get("confidence") in _AUTO_CONF
                and suggestion.get("suggested_code")
            )

            if auto_accepted:
                # Accept the AI suggestion inline; continue to rate validation below.
                line_item.taxonomy_code = suggestion["suggested_code"]  # type: ignore[index]
                line_item.billing_component = (
                    suggestion.get("suggested_billing_component") or ""  # type: ignore[union-attr]
                )
                line_item.mapping_confidence = suggestion["confidence"]  # type: ignore[index]
                line_item.mapping_rule_id = None  # AI-suggested, no rule matched
                logger.info(
                    "Line %d: UNRECOGNIZED → AI auto-accepted '%s' (%s confidence); "
                    "proceeding to rate validation",
                    raw_item.line_number,
                    suggestion["suggested_code"],  # type: ignore[index]
                    suggestion["confidence"],  # type: ignore[index]
                )
                # Record the accepted mapping so the rule engine learns from it
                # and won't need to call the AI suggester again for the same supplier.
                try:
                    from app.services.classification.mapping_learner import (
                        record_confirmed_mapping,
                    )
                    from app.models.mapping import ConfirmedBy

                    record_confirmed_mapping(
                        db=db,
                        line_item=line_item,
                        taxonomy_code=suggestion["suggested_code"],  # type: ignore[index]
                        billing_component=suggestion.get("suggested_billing_component") or "",  # type: ignore[union-attr]
                        source=ConfirmedBy.SYSTEM,
                        scope="this_supplier",
                    )
                except Exception as learn_exc:
                    logger.warning(
                        "Mapping learning skipped for auto-accepted line %d: %s",
                        raw_item.line_number,
                        learn_exc,
                    )
                # Fall through to rate/guideline validation (do NOT return early).

            else:
                # No confident suggestion — flag for carrier classification review.
                # spend_error_count intentionally NOT incremented: classification
                # failures do not require supplier correction; carrier confirms taxonomy.
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
                return line_item, error_count, spend_error_count, warning_count, 0

        # ── AI description alignment assessment ───────────────────────────────
        # Run after a successful classification (not UNRECOGNIZED). Fetches the
        # taxonomy item to get its label and description, then asks Claude whether
        # the raw_description semantically matches. Gracefully skips on failure.
        try:
            from app.models.taxonomy import TaxonomyItem as TaxItem

            tax_item = db.get(TaxItem, result.taxonomy_code)
            if tax_item:
                assessment = assess_description_alignment(
                    raw_description=raw_item.raw_description,
                    taxonomy_label=tax_item.label,
                    taxonomy_description=tax_item.description,
                    vertical=vertical,
                )
                if assessment:
                    line_item.ai_description_assessment = assessment
        except Exception as ai_exc:
            logger.warning(
                "AI assessment skipped for line %d: %s", raw_item.line_number, ai_exc
            )

    except Exception as exc:
        logger.error("Classification failed for line %d: %s", raw_item.line_number, exc)
        line_item.status = LineItemStatus.EXCEPTION
        error_count += 1
        return line_item, error_count, spend_error_count, warning_count, 0

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
            db.flush()
            _attach_ai_recommendation(db, exc_record, val, line_item, invoice, contract, vertical=vertical)
            audit.log_line_item_exception_opened(db, line_item, rate_result)
            error_count += 1
            spend_error_count += 1
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
            db.flush()
            _attach_ai_recommendation(db, exc_record, val, line_item, invoice, contract, vertical=vertical)
            audit.log_line_item_exception_opened(db, line_item, guide_result)
            error_count += 1
            spend_error_count += 1
        elif guide_result.status == ValidationStatus.WARNING:
            warning_count += 1

    # ── Set final line item status ─────────────────────────────────────────────
    line_item.status = (
        LineItemStatus.EXCEPTION if error_count > 0 else LineItemStatus.VALIDATED
    )
    line_item.expected_amount = expected_amount

    return line_item, error_count, spend_error_count, warning_count, expected_amount


# ── Helpers ────────────────────────────────────────────────────────────────────


def _prior_review_required_count(db, supplier_id) -> int:
    """Count REVIEW_REQUIRED invoices for this supplier in the past 90 days."""
    from datetime import timedelta
    from app.models.invoice import Invoice as _Invoice, SubmissionStatus as _SS

    cutoff = date.today() - timedelta(days=90)
    return (
        db.query(_Invoice)
        .filter(
            _Invoice.supplier_id == supplier_id,
            _Invoice.status == _SS.REVIEW_REQUIRED,
            _Invoice.submitted_at >= cutoff,
        )
        .count()
    )


def _prior_exception_count(db, supplier_id, taxonomy_code) -> int:
    """Count exceptions for this supplier + taxonomy code in the past 90 days."""
    if not taxonomy_code:
        return 0
    from datetime import timedelta
    from app.models.invoice import Invoice as _Invoice, LineItem as _LI
    from app.models.validation import ExceptionRecord as _ER

    cutoff = date.today() - timedelta(days=90)
    return (
        db.query(_ER)
        .join(_LI, _LI.id == _ER.line_item_id)
        .join(_Invoice, _Invoice.id == _LI.invoice_id)
        .filter(
            _Invoice.supplier_id == supplier_id,
            _LI.taxonomy_code == taxonomy_code,
            _Invoice.submitted_at >= cutoff,
        )
        .count()
    )


def _attach_ai_recommendation(
    db, exc_record, val_result, line_item, invoice, contract, vertical: str = "default"
) -> None:
    """
    Call the exception resolver and attach ai_recommendation + ai_reasoning
    to the exception record. Non-blocking — silently skips on any failure.
    """
    try:
        prior = _prior_exception_count(db, invoice.supplier_id, line_item.taxonomy_code)
        rec = assess_exception(
            exception_message=val_result.message,
            required_action=val_result.required_action,
            taxonomy_code=line_item.taxonomy_code,
            contract_name=contract.name,
            supplier_name=invoice.supplier.name,
            prior_exception_count=prior,
            vertical=vertical,
        )
        if rec:
            exc_record.ai_recommendation = rec["recommendation"]
            exc_record.ai_reasoning = rec["reasoning"]
    except Exception as ai_exc:
        logger.warning("Exception resolver failed: %s", ai_exc)


def _fail_invoice(db, invoice, reason: str) -> dict:
    """Mark invoice as REVIEW_REQUIRED and return error summary."""
    logger.error("Invoice %s pipeline failed: %s", invoice.id, reason)
    try:
        invoice.status = SubmissionStatus.REVIEW_REQUIRED
        db.commit()
    except Exception:
        db.rollback()
    return {"error": reason, "invoice_id": str(invoice.id)}
