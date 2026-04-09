"""
Clean up all pre-Phase 4 invoices that cannot be properly resolved in the
Phase 4+ workflow.  Two categories are handled in one pass:

1. OVERRIDE lines
   Before the Classification Queue existed, carrier admins could inline-override
   a taxonomy code from the admin invoice detail ("Save & Learn").  This set
   line_items.status = 'OVERRIDE' but never triggered a post-classification bill
   audit, leaving lines with no Expected amount and $0 payable.

2. EXCEPTION lines with no taxonomy code
   The old pipeline ran bill audit on every line regardless of confidence.
   Lines the AI couldn't classify (no taxonomy_code assigned) hit no rate card
   and were flagged as EXCEPTION with no Expected amount and no resolution path.
   In Phase 4+ these lines would be CLASSIFICATION_PENDING and routed to the
   Classification Queue first.

Both categories are dead-ends in the Phase 4+ workflow.  Remove them so that
the review queue and classification queue only contain properly-routed data,
then re-seed with run_demo.py to generate clean Phase 4+ invoices.

Usage (run from Render Shell or locally with DATABASE_URL set):
    python scripts/cleanup_legacy_invoices.py --preview   # show what would be deleted
    python scripts/cleanup_legacy_invoices.py --commit    # delete the invoices
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import SessionLocal


def find_legacy_invoices(db) -> list[dict]:
    """
    Return all invoices that have at least one line in either:
      - OVERRIDE status  (inline taxonomy override, bill audit never re-run)
      - EXCEPTION status with no taxonomy_code  (old pipeline, unclassified line)
    """
    rows = db.execute(
        text("""
        SELECT DISTINCT
            i.id::text              AS invoice_id,
            i.invoice_number,
            i.status                AS invoice_status,
            s.name                  AS supplier_name,
            COUNT(li.id) FILTER (
                WHERE li.status = 'OVERRIDE'
            )                       AS override_lines,
            COUNT(li.id) FILTER (
                WHERE li.status = 'EXCEPTION' AND li.taxonomy_code IS NULL
            )                       AS unclassified_exception_lines,
            COUNT(li.id)            AS total_lines
        FROM invoices i
        JOIN suppliers s ON s.id = i.supplier_id
        JOIN line_items li ON li.invoice_id = i.id
        WHERE EXISTS (
            SELECT 1 FROM line_items li2
            WHERE li2.invoice_id = i.id
              AND (
                  li2.status = 'OVERRIDE'
                  OR (li2.status = 'EXCEPTION' AND li2.taxonomy_code IS NULL)
              )
        )
        GROUP BY i.id, i.invoice_number, i.status, s.name
        ORDER BY s.name, i.invoice_number
    """)
    ).fetchall()

    return [dict(r._mapping) for r in rows]


def delete_invoices(db, invoice_ids: list[str]) -> int:
    """
    Hard-delete invoices by ID.  FK ON DELETE CASCADE removes line items,
    validation results, exception records, classification queue items, and
    audit events automatically.
    """
    if not invoice_ids:
        return 0
    result = db.execute(
        text("DELETE FROM invoices WHERE id::text = ANY(:ids)"),
        {"ids": invoice_ids},
    )
    return result.rowcount


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove pre-Phase 4 legacy invoices (OVERRIDE + unclassified EXCEPTION lines)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--preview",
        action="store_true",
        help="Show invoices that would be deleted (no changes)",
    )
    mode.add_argument("--commit", action="store_true", help="Delete the invoices")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        invoices = find_legacy_invoices(db)

        if not invoices:
            print("\n  ✓ No legacy invoices found — queue is clean.\n")
            return

        # ── Preview ───────────────────────────────────────────────────────────
        print(f"\n{'=' * 76}")
        print(
            f"  {'Preview:' if args.preview else 'Deleting:'} "
            f"Pre-Phase 4 legacy invoices  ({len(invoices)} found)"
        )
        print(f"{'=' * 76}")
        print(
            f"  {'Supplier':<30} {'Invoice':<18} {'Status':<24}"
            f" {'Override':>8} {'Unclassif':>9} {'Total':>5}"
        )
        print(f"  {'-' * 72}")

        for inv in invoices:
            print(
                f"  {inv['supplier_name'][:29]:<30} "
                f"{inv['invoice_number']:<18} "
                f"{inv['invoice_status']:<24} "
                f"{inv['override_lines']:>8} "
                f"{inv['unclassified_exception_lines']:>9} "
                f"{inv['total_lines']:>5}"
            )

        print(f"  {'-' * 72}")
        print(f"  {len(invoices)} invoice(s) with pre-Phase 4 pipeline artefacts\n")

        if args.preview:
            print("  Run with --commit to delete these invoices.")
            print(
                "  Then run: python scripts/run_demo.py to generate clean Phase 4+ data.\n"
            )
            return

        # ── Delete ────────────────────────────────────────────────────────────
        invoice_ids = [inv["invoice_id"] for inv in invoices]
        deleted = delete_invoices(db, invoice_ids)
        db.commit()

        print(f"  ✓ Deleted {deleted} invoice(s) and all related data.")
        print("    (line items, validation results, exceptions, classification")
        print("    queue items, and audit events removed via FK cascade)\n")
        print("  Next step: python scripts/run_demo.py")
        print("  This submits fresh invoices through the Phase 4+ pipeline and")
        print(
            "  populates the Classification Queue with real MEDIUM/LOW confidence items.\n"
        )

    except Exception as exc:
        db.rollback()
        print(f"\nERROR: {exc}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
