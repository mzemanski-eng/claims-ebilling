"""
Duplicate Payment Detector.

Checks whether a line item matches a previously-approved, paid line under the
same carrier — protecting against suppliers re-billing already-paid services
on a new invoice.

Match key: claim_number + taxonomy_code + service_date (all three required).
Scope:     Same carrier only (LineItem → Invoice → Contract → carrier_id).
Flags against: APPROVED lines on APPROVED or EXPORTED invoices only.
               DENIED lines are never re-flagged.

Two checks per line:
  1. Within-invoice:  same key already seen in `already_seen_keys` on this
                      invoice (supplier billed the same service twice in one
                      invoice).
  2. Cross-invoice:   SQL query for a prior APPROVED line with the same key on
                      a *different* approved/exported invoice for this carrier.

Returns a list of DuplicateDetectionResult objects (empty if no duplicates).
The caller (invoice_pipeline) persists ValidationResult + ExceptionRecord and
increments error_count / spend_error_count.

Design principle: DB reads are performed in this service; DB writes stay in the
pipeline worker (same pattern as RateValidator / GuidelineValidator).
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from app.models.invoice import Invoice, LineItem, LineItemStatus, SubmissionStatus
from app.models.supplier import Contract
from app.models.validation import (
    RequiredAction,
    ValidationSeverity,
    ValidationStatus,
    ValidationType,
)

logger = logging.getLogger(__name__)

# ── Tuple key type alias ──────────────────────────────────────────────────────

DuplicateKey = tuple[str, str, date]  # (claim_number, taxonomy_code, service_date)


@dataclass
class DuplicateDetectionResult:
    """
    One duplicate finding for a single line item.
    Maps directly to ValidationResult model fields.
    """

    validation_type: str = ValidationType.DUPLICATE
    rate_card_id: Optional[str] = None
    guideline_id: Optional[str] = None
    status: str = ValidationStatus.FAIL
    severity: str = ValidationSeverity.ERROR
    message: str = ""
    expected_value: Optional[str] = None
    actual_value: Optional[str] = None
    required_action: str = RequiredAction.DUPLICATE_BILLING


class DuplicateDetector:
    """
    Detects duplicate billing for a single line item.

    Usage (from the pipeline):
        detector = DuplicateDetector(db)
        seen_keys: set[DuplicateKey] = set()

        # For each line_item after guideline validation:
        dup_results = detector.check(line_item, invoice, seen_keys)
        # seen_keys is mutated in-place — the key is added even if no duplicate
        # was found, so future lines on the same invoice can detect within-invoice
        # duplicates correctly.
    """

    def __init__(self, db) -> None:
        self.db = db

    def check(
        self,
        line_item: LineItem,
        invoice: Invoice,
        already_seen_keys: set,
    ) -> list[DuplicateDetectionResult]:
        """
        Check a line item for duplicate billing.

        Args:
            line_item:         The newly-created LineItem (not yet flushed to DB
                               with VALIDATED/EXCEPTION status).
            invoice:           The parent Invoice (carries contract reference).
            already_seen_keys: Mutable set of DuplicateKey tuples for lines
                               already processed on this invoice.  This method
                               *adds* the current line's key to the set before
                               returning so subsequent lines can detect
                               within-invoice duplicates.

        Returns:
            List of DuplicateDetectionResult.  Empty list when clean.
        """
        results: list[DuplicateDetectionResult] = []

        # ── Early exit when any key field is missing ──────────────────────────
        if (
            not line_item.claim_number
            or not line_item.taxonomy_code
            or not line_item.service_date
        ):
            logger.debug(
                "Line %d: skipping duplicate check (incomplete key fields)",
                line_item.line_number,
            )
            return results

        key: DuplicateKey = (
            line_item.claim_number,
            line_item.taxonomy_code,
            line_item.service_date,
        )

        # ── Check 1: within-invoice duplicate ─────────────────────────────────
        if key in already_seen_keys:
            already_seen_keys.add(key)  # no-op but explicit
            logger.info(
                "Line %d: within-invoice duplicate detected (claim=%s, code=%s, date=%s)",
                line_item.line_number,
                key[0],
                key[1],
                key[2],
            )
            results.append(
                DuplicateDetectionResult(
                    message=(
                        f"Duplicate billing detected: this invoice already contains a line "
                        f"for claim {key[0]}, service '{key[1]}' on {key[2]}. "
                        f"This service appears to have been billed twice on the same invoice."
                    ),
                )
            )
            return results

        # Register this key before the cross-invoice check so callers don't need
        # to track the add separately.
        already_seen_keys.add(key)

        # ── Check 2: cross-invoice duplicate ──────────────────────────────────
        carrier_id = invoice.contract.carrier_id if invoice.contract else None
        if carrier_id is None:
            logger.warning(
                "Line %d: skipping cross-invoice duplicate check (carrier_id not found)",
                line_item.line_number,
            )
            return results

        try:
            prior = (
                self.db.query(LineItem)
                .join(Invoice, Invoice.id == LineItem.invoice_id)
                .join(Contract, Contract.id == Invoice.contract_id)
                .filter(
                    LineItem.claim_number == key[0],
                    LineItem.taxonomy_code == key[1],
                    LineItem.service_date == key[2],
                    LineItem.status == LineItemStatus.APPROVED,
                    Invoice.status.in_(
                        [SubmissionStatus.APPROVED, SubmissionStatus.EXPORTED]
                    ),
                    Contract.carrier_id == carrier_id,
                    Invoice.id != invoice.id,  # exclude the current invoice
                )
                .first()
            )
        except Exception as exc:
            logger.warning(
                "Line %d: cross-invoice duplicate query failed: %s",
                line_item.line_number,
                exc,
            )
            return results

        if prior is not None:
            prior_invoice_number = (
                prior.invoice.invoice_number if prior.invoice else "a previous invoice"
            )
            logger.info(
                "Line %d: cross-invoice duplicate detected (claim=%s, code=%s, date=%s) "
                "— previously paid on invoice %s",
                line_item.line_number,
                key[0],
                key[1],
                key[2],
                prior_invoice_number,
            )
            results.append(
                DuplicateDetectionResult(
                    message=(
                        f"Possible duplicate payment: claim {key[0]}, service '{key[1]}' "
                        f"on {key[2]} was already approved and paid on "
                        f"invoice {prior_invoice_number}. "
                        f"Verify this is not a re-bill for a previously-paid service."
                    ),
                )
            )

        return results
