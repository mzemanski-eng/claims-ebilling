"""
Synthetic data seeder for the Veridian claims eBilling platform.

Four AI agents generate a realistic dataset across all 11 P&C ALAE
taxonomy domains (IA, ENG, CR, INV, DRNE, INSP, LA, VIRT, REC, APPR, XDOMAIN).

Usage:
    python scripts/seed_platform.py --dry-run               # Preview — no DB writes
    python scripts/seed_platform.py --commit                # Write to DB (direct)
    python scripts/seed_platform.py --commit --clean        # Wipe SEED data, then write
    python scripts/seed_platform.py --commit --pipeline     # Write invoices as SUBMITTED,
                                                             # then run each through the
                                                             # full AI classification +
                                                             # validation pipeline
    python scripts/seed_platform.py --commit --clean --pipeline  # clean + pipeline
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.supplier import Carrier, Supplier
from app.workers.invoice_pipeline import process_invoice_sync
from scripts.agents import AuditManager, Biller, ContractFabricator, SeniorLeader
from scripts.agents.base import RunContext

# Show only WARNING+ from noisy libs; INFO from our agents is suppressed by default
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s [%(name)s] %(message)s",
)


def _run_pipeline_pass(ctx: RunContext, db) -> None:
    """
    Run each seeded invoice through the full AI classification + validation pipeline.

    Called after Biller commits invoices in pipeline mode.  Each InvoiceSpec has
    `db_id` (the Invoice UUID) and `csv_bytes` (the synthetic invoice as CSV).
    process_invoice_sync() takes over from there: it classifies every line item,
    runs rate + guideline validation, generates ExceptionRecords, and sets the
    final invoice status.
    """
    invoices = [iv for iv in ctx.invoices if iv.db_id and iv.csv_bytes]
    total = len(invoices)
    if not invoices:
        print("  ⚠ No invoices to pipeline (missing db_id or csv_bytes).\n")
        return

    print(f"\nRunning Pipeline Pass — {total} invoices through AI classification + validation")
    ok = err = 0
    for i, inv_spec in enumerate(invoices, 1):
        inv_num = inv_spec.invoice_number
        try:
            result = process_invoice_sync(
                invoice_id=str(inv_spec.db_id),
                file_bytes=inv_spec.csv_bytes,
                filename=f"{inv_num}.csv",
                db=db,
            )
            db.commit()
            status_val = result.get("status", "?")
            print(f"  [{i:>3}/{total}] {inv_num:<24} → {status_val}")
            ok += 1
        except Exception as exc:
            db.rollback()
            print(f"  [{i:>3}/{total}] {inv_num:<24} → ERROR: {exc}")
            err += 1

    print(f"\n  Pipeline complete: {ok} succeeded, {err} failed\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Veridian synthetic data seeder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview all agent output without writing to DB",
    )
    mode.add_argument(
        "--commit",
        action="store_true",
        help="Generate data and write to DB",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete all SEED-* supplier data before writing (--commit only)",
    )
    parser.add_argument(
        "--pipeline",
        action="store_true",
        help=(
            "Run each seeded invoice through the AI classification + validation "
            "pipeline instead of writing line items directly (--commit only)"
        ),
    )
    args = parser.parse_args()

    if args.clean and not args.commit:
        parser.error("--clean requires --commit")
    if args.pipeline and not args.commit:
        parser.error("--pipeline requires --commit")

    db = SessionLocal()
    try:
        # ── Require an existing carrier ────────────────────────────────────────
        carrier = db.query(Carrier).first()
        if not carrier:
            print("ERROR: No carrier found. Run scripts/bootstrap.py first.")
            sys.exit(1)

        mode_label = "DRY RUN — no DB writes" if args.dry_run else "COMMIT"
        print(f"\n{'='*60}")
        print(f"  Veridian Synthetic Data Seeder")
        print(f"  Carrier : {carrier.name} ({carrier.short_code})")
        print(f"  Mode    : {mode_label}")
        if args.clean:
            print(f"  Clean   : yes — SEED-* data will be wiped first")
        if args.pipeline:
            print(f"  Pipeline: yes — invoices routed through AI classification")
        print(f"{'='*60}\n")

        # ── Optional clean ────────────────────────────────────────────────────
        if args.clean:
            count = (
                db.query(Supplier)
                .filter(Supplier.tax_id.like("SEED-%"))
                .count()
            )
            db.query(Supplier).filter(
                Supplier.tax_id.like("SEED-%")
            ).delete(synchronize_session="fetch")
            db.flush()
            print(
                f"  Deleted {count} SEED-* supplier(s) and all child records "
                f"(contracts, invoices, line items, exceptions).\n"
            )

        ctx = RunContext(
            carrier_id=carrier.id,
            dry_run=args.dry_run,
            pipeline=args.pipeline if args.commit else False,
        )

        # ── Agent 1: ContractFabricator ───────────────────────────────────────
        print("Running Agent 1 — ContractFabricator  (Claude haiku × ~40 calls)")
        ContractFabricator(ctx=ctx, db=db).run()
        if not args.dry_run:
            db.commit()
            print("  ✓ Contracts committed\n")

        # ── Agent 2: Biller ───────────────────────────────────────────────────
        print("Running Agent 2 — Biller  (Claude haiku × 12 calls)")
        Biller(ctx=ctx, db=db).run()
        if not args.dry_run:
            db.commit()
            print("  ✓ Invoices committed\n")

        # ── Pipeline pass (optional) ──────────────────────────────────────────
        if args.pipeline and not args.dry_run:
            _run_pipeline_pass(ctx, db)

        # ── Agent 3: AuditManager (read-only) ─────────────────────────────────
        print("Running Agent 3 — AuditManager  (Claude sonnet × 1 call)")
        AuditManager(ctx=ctx, db=db).run()

        # ── Agent 4: SeniorLeader (read-only) ────────────────────────────────
        print("Running Agent 4 — SeniorLeader  (Claude sonnet × 1 call)")
        SeniorLeader(ctx=ctx, db=db).run()

        # ── Final summary ─────────────────────────────────────────────────────
        print(f"\n{'='*60}")
        if args.dry_run:
            print("  DRY RUN complete.")
            print("  Review the output above, then run with --commit to write.")
        else:
            total_lines = sum(len(iv.line_items) for iv in ctx.invoices)
            print("  SEED COMPLETE.")
            print(
                f"  {len(ctx.suppliers)} suppliers  |  "
                f"{len(ctx.contracts)} contracts  |  "
                f"{len(ctx.invoices)} invoices  |  "
                f"{total_lines} line items"
            )
        print(f"{'='*60}\n")

    except KeyboardInterrupt:
        db.rollback()
        print("\nInterrupted — rolling back any uncommitted changes.")
        sys.exit(130)
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
