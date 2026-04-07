"""
RQ background job — runs the synthetic data seeder.

Called by enqueue_seed_demo(); carrier_id is passed explicitly so the job
doesn't need to discover the carrier at runtime.
"""

from __future__ import annotations

import logging
import os
import sys
import uuid as uuid_lib

logger = logging.getLogger(__name__)


def run_seed(carrier_id: str, clean: bool = False) -> dict:
    """
    RQ background job: generate and commit synthetic seed data.

    Args:
        carrier_id: UUID string of the carrier to seed data for.
        clean:      If True, wipe existing SEED-* data before generating.

    Returns:
        Summary dict stored as the RQ job result.
    """
    # Ensure app root is on path (worker process may not have it)
    repo_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    from app.database import SessionLocal
    from app.models.supplier import Carrier, Supplier
    from scripts.agents import Biller, ContractFabricator
    from scripts.agents.base import RunContext

    db = SessionLocal()
    try:
        carrier = db.get(Carrier, uuid_lib.UUID(carrier_id))
        if not carrier:
            logger.error("Carrier %s not found — seed job aborted", carrier_id)
            return {"error": f"Carrier {carrier_id} not found"}

        if clean:
            count = db.query(Supplier).filter(Supplier.tax_id.like("SEED-%")).count()
            db.query(Supplier).filter(Supplier.tax_id.like("SEED-%")).delete(
                synchronize_session="fetch"
            )
            db.flush()
            logger.info("Deleted %d SEED-* supplier(s)", count)

        ctx = RunContext(carrier_id=carrier.id, dry_run=False)

        # Agent 1: ContractFabricator
        logger.info("Seed job: running ContractFabricator")
        ContractFabricator(ctx=ctx, db=db).run()
        db.commit()

        # Agent 2: Biller
        logger.info("Seed job: running Biller")
        Biller(ctx=ctx, db=db).run()
        db.commit()

        # Agents 3 + 4 (AuditManager / SeniorLeader) are read-only narrative
        # generators; their output goes to stdout which no one reads in a
        # background job, so we skip them here.

        total_lines = sum(len(iv.line_items) for iv in ctx.invoices)
        result = {
            "status": "complete",
            "suppliers": len(ctx.suppliers),
            "contracts": len(ctx.contracts),
            "invoices": len(ctx.invoices),
            "line_items": total_lines,
        }
        logger.info("Seed job complete: %s", result)
        return result

    except Exception as exc:
        db.rollback()
        logger.exception("Seed job failed: %s", exc)
        raise
    finally:
        db.close()
