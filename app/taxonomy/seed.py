"""
Taxonomy seeder — idempotent upsert of all TaxonomyItem rows.

Run via:
  python -m app.taxonomy.seed          (directly)
  alembic upgrade head && python -m app.taxonomy.seed   (after migrations)

On Render, the build command runs this after `alembic upgrade head`.
Safe to run multiple times — uses INSERT ... ON CONFLICT DO UPDATE.

Phase 3: also populates TaxonomyItem.vertical_id from the 'vertical' field
in taxonomy.yaml.  Requires the verticals table to be seeded first (done by
migration 0012).
"""

import sys
import logging
import uuid

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import SessionLocal
from app.models.taxonomy import TaxonomyItem, Vertical
from app.taxonomy.loader import TAXONOMY, load_with_vertical

logger = logging.getLogger(__name__)


def seed_taxonomy(session=None) -> int:
    """
    Upsert all taxonomy items from taxonomy.yaml.
    Returns the number of rows upserted.
    Uses a session if provided (for testability); opens its own otherwise.

    Also resolves each entry's 'vertical' slug to a vertical_id UUID so that
    TaxonomyItem.vertical_id is populated correctly for per-vertical routing.
    """
    _owns_session = session is None
    if _owns_session:
        session = SessionLocal()

    try:
        items_with_vertical = load_with_vertical()

        # Build slug → UUID map from the verticals table (seeded by migration 0012).
        # If the verticals table is empty (e.g. in a clean test DB without migrations),
        # vertical_id will stay NULL — a safe graceful degradation.
        vertical_map: dict[str, uuid.UUID] = {
            v.slug: v.id for v in session.query(Vertical).all()
        }
        if not vertical_map:
            logger.warning(
                "seed_taxonomy: verticals table is empty — vertical_id will be NULL for all items. "
                "Run 'alembic upgrade head' to seed verticals first."
            )

        # Build rows for upsert; resolve vertical slug → UUID (None if not found)
        rows: list[dict] = []
        for item in items_with_vertical:
            row = {k: v for k, v in item.items() if k != "vertical"}
            slug = item.get("vertical")
            row["vertical_id"] = vertical_map.get(slug) if slug else None
            rows.append(row)

        stmt = pg_insert(TaxonomyItem).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["code"],
            set_={
                "domain": stmt.excluded.domain,
                "service_item": stmt.excluded.service_item,
                "billing_component": stmt.excluded.billing_component,
                "unit_model": stmt.excluded.unit_model,
                "label": stmt.excluded.label,
                "description": stmt.excluded.description,
                "vertical_id": stmt.excluded.vertical_id,
                # is_active intentionally not overwritten (carrier may deactivate codes)
            },
        )
        session.execute(stmt)
        session.commit()
        count = len(rows)
        logger.info("Taxonomy seed complete: %d items upserted.", count)
        return count
    except Exception:
        session.rollback()
        raise
    finally:
        if _owns_session:
            session.close()


def get_taxonomy_codes() -> set[str]:
    """Return the set of all canonical taxonomy codes (from YAML, not DB)."""
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
