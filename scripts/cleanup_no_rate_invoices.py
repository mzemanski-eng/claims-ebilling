"""
Clean up invoices that show "No rate" in the invoice queue.

"No rate" appears when an invoice goes through the AI pipeline but the
supplier's contract has no rate card for the billed taxonomy code.  These are
pre-existing test invoices (not from the SEED-* suppliers) whose contracts
were never fully configured.

Usage:
    python scripts/cleanup_no_rate_invoices.py --preview   # Show what would be deleted
    python scripts/cleanup_no_rate_invoices.py --commit    # Delete the invoices
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import SessionLocal


def find_no_rate_invoices(db) -> list[dict]:
    """
    Return all non-SEED invoices that have at least one line item with an
    ESTABLISH_CONTRACT_RATE validation result (the "No rate" signal).
    """
    rows = db.execute(text("""
        SELECT DISTINCT
            i.id::text          AS invoice_id,
            i.invoice_number,
            i.status,
            s.name              AS supplier_name,
            s.tax_id,
            c.name              AS contract_name,
            COUNT(DISTINCT li.id) FILTER (
                WHERE vr.required_action = 'ESTABLISH_CONTRACT_RATE'
            )                   AS no_rate_lines,
            COUNT(DISTINCT li.id) AS total_lines
        FROM invoices i
        JOIN suppliers s ON s.id = i.supplier_id
        LEFT JOIN contracts c ON c.id = i.contract_id
        JOIN line_items li ON li.invoice_id = i.id
        JOIN validation_results vr ON vr.line_item_id = li.id
        WHERE vr.required_action = 'ESTABLISH_CONTRACT_RATE'
          AND s.tax_id NOT LIKE 'SEED-%'
        GROUP BY i.id, i.invoice_number, i.status, s.name, s.tax_id, c.name
        ORDER BY s.name, i.invoice_number
    """)).fetchall()

    return [dict(r._mapping) for r in rows]


def delete_invoices(db, invoice_ids: list[str]) -> int:
    """
    Hard-delete invoices by ID.  Cascade deletes line items, validation
    results, exception records, and audit events via FK ON DELETE CASCADE.
    """
    if not invoice_ids:
        return 0
    result = db.execute(
        text("DELETE FROM invoices WHERE id = ANY(:ids)"),
        {"ids": invoice_ids},
    )
    return result.rowcount


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove 'No rate' invoices from non-SEED suppliers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preview", action="store_true",
                      help="Show invoices that would be deleted (no changes)")
    mode.add_argument("--commit",  action="store_true",
                      help="Delete the invoices")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        invoices = find_no_rate_invoices(db)

        if not invoices:
            print("\n  ✓ No 'No rate' invoices found — queue is clean.\n")
            return

        # ── Preview ───────────────────────────────────────────────────────────
        print(f"\n{'='*72}")
        print(f"  {'No-Rate' if args.preview else 'Deleting'} Invoices  "
              f"({len(invoices)} found)")
        print(f"{'='*72}")
        print(f"  {'Supplier':<34} {'Invoice':<20} {'Status':<22} {'No-rate/Total'}")
        print(f"  {'-'*68}")

        for inv in invoices:
            ratio = f"{inv['no_rate_lines']}/{inv['total_lines']} lines"
            print(
                f"  {inv['supplier_name'][:33]:<34} "
                f"{inv['invoice_number']:<20} "
                f"{inv['status']:<22} "
                f"{ratio}"
            )

        print(f"  {'-'*68}")
        print(f"  {len(invoices)} invoice(s) from non-SEED suppliers with missing rate cards\n")

        if args.preview:
            print("  Run with --commit to delete these invoices.\n")
            return

        # ── Delete ────────────────────────────────────────────────────────────
        invoice_ids = [inv["invoice_id"] for inv in invoices]
        deleted = delete_invoices(db, invoice_ids)
        db.commit()

        print(f"  ✓ Deleted {deleted} invoice(s) and all related line items,")
        print(f"    validation results, and exception records.\n")
        print(f"  The invoice queue now shows only properly-configured invoices.\n")

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
