"""
Taxonomy seeder — idempotent upsert of all TaxonomyItem rows.

Run via:
  python -m app.taxonomy.seed          (directly)
  alembic upgrade head && python -m app.taxonomy.seed   (after migrations)

On Render, the build command runs this after `alembic upgrade head`.
Safe to run multiple times — uses INSERT ... ON CONFLICT DO UPDATE.
"""

import sys
import logging

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import SessionLocal, engine
from app.models.taxonomy import TaxonomyItem
from app.taxonomy.constants import TAXONOMY

logger = logging.getLogger(__name__)


def seed_taxonomy(session=None) -> int:
    """
    Upsert all taxonomy items from constants.py.
    Returns the number of rows upserted.
    Uses a session if provided (for testability); opens its own otherwise.
    """
    _owns_session = session is None
    if _owns_session:
        session = SessionLocal()

    try:
        stmt = pg_insert(TaxonomyItem).values(TAXONOMY)
        stmt = stmt.on_conflict_do_update(
            index_elements=["code"],
            set_={
                "domain": stmt.excluded.domain,
                "service_item": stmt.excluded.service_item,
                "billing_component": stmt.excluded.billing_component,
                "unit_model": stmt.excluded.unit_model,
                "label": stmt.excluded.label,
                "description": stmt.excluded.description,
                # is_active intentionally not overwritten (carrier may deactivate)
            },
        )
        result = session.execute(stmt)
        session.commit()
        count = len(TAXONOMY)
        logger.info("Taxonomy seed complete: %d items upserted.", count)
        return count
    except Exception:
        session.rollback()
        raise
    finally:
        if _owns_session:
            session.close()


def get_taxonomy_codes() -> set[str]:
    """Return the set of all canonical taxonomy codes (from constants, not DB)."""
    return {item["code"] for item in TAXONOMY}


def get_taxonomy_by_domain(domain: str) -> list[dict]:
    """Return all taxonomy items for a given domain."""
    return [item for item in TAXONOMY if item["domain"] == domain]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        count = seed_taxonomy()
        print(f"✓ Taxonomy seeded: {count} items")
        sys.exit(0)
    except Exception as e:
        print(f"✗ Taxonomy seed failed: {e}", file=sys.stderr)
        sys.exit(1)
