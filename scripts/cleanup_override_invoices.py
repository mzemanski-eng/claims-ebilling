"""
Clean up invoices that contain line items in OVERRIDE status.

OVERRIDE lines are a pre-Phase 4 artefact.  Before the Classification Queue
existed, carrier admins could inline-override a taxonomy code from the admin
invoice detail page ("Save & Learn").  This set line_items.status = 'OVERRIDE'
but did NOT trigger a post-classification bill audit, leaving the lines in an
ambiguous state — no Expected amount, $0 payable, confusing "Overridden" badge
in the audit view.

In Phase 4+ the correct flow is:
    Low-confidence line → Classification Queue → carrier confirms taxonomy →
    _run_post_classification_bill_audit() → VALIDATED or EXCEPTION status.

These legacy OVERRIDE invoices pre-date that pipeline and should be removed
before running a clean demo click-through.

Usage (run from Render Shell or locally with DATABASE_URL set):
    python scripts/cleanup_override_invoices.py --preview   # show what would be deleted
    python scripts/cleanup_override_invoices.py --commit    # delete the invoices
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import SessionLocal


def find_override_invoices(db) -> list[dict]:
    """Return all invoices that have at least one line in OVERRIDE status."""
    rows = db.execute(
        text("""
        SELECT DISTINCT
            i.id::text              AS invoice_id,
            i.invoice_number,
            i.status,
            s.name                  AS supplier_name,
            COUNT(li.id) FILTER (
                WHERE li.status = 'OVERRIDE'
            )                       AS override_lines,
            COUNT(li.id)            AS total_lines
        FROM invoices i
        JOIN suppliers s ON s.id = i.supplier_id
        JOIN line_items li ON li.invoice_id = i.id
        WHERE EXISTS (
            SELECT 1 FROM line_items li2
            WHERE li2.invoice_id = i.id
              AND li2.status = 'OVERRIDE'
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
        description="Remove pre-Phase 4 OVERRIDE-status invoices",
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
        invoices = find_override_invoices(db)

        if not invoices:
            print("\n  ✓ No OVERRIDE-status invoices found — queue is clean.\n")
            return

        # ── Preview ───────────────────────────────────────────────────────────
        print(f"\n{'=' * 72}")
        print(
            f"  {'Preview:' if args.preview else 'Deleting:'} "
            f"Invoices with OVERRIDE lines  ({len(invoices)} found)"
        )
        print(f"{'=' * 72}")
        print(f"  {'Supplier':<34} {'Invoice':<20} {'Status':<22} {'Override/Total'}")
        print(f"  {'-' * 68}")

        for inv in invoices:
            ratio = f"{inv['override_lines']}/{inv['total_lines']} lines"
            print(
                f"  {inv['supplier_name'][:33]:<34} "
                f"{inv['invoice_number']:<20} "
                f"{inv['status']:<22} "
                f"{ratio}"
            )

        print(f"  {'-' * 68}")
        print(f"  {len(invoices)} invoice(s) with pre-Phase 4 OVERRIDE line items\n")

        if args.preview:
            print("  Run with --commit to delete these invoices.\n")
            return

        # ── Delete ────────────────────────────────────────────────────────────
        invoice_ids = [inv["invoice_id"] for inv in invoices]
        deleted = delete_invoices(db, invoice_ids)
        db.commit()

        print(f"  ✓ Deleted {deleted} invoice(s) and all related line items,")
        print("    validation results, exception records, and classification")
        print("    queue items.\n")
        print("  The review queue now shows only Phase 4+ pipeline invoices.\n")

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
