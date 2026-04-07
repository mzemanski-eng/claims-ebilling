"""
Taxonomy loader — reads taxonomy.yaml and provides TAXONOMY list.

Consumers of TAXONOMY (classifier, contract parser, seed.py, frontend taxonomy.ts)
should import from here or from the backward-compat shim (constants.py).

Design:
- TAXONOMY strips the 'vertical' field — it is not a TaxonomyItem column and
  all existing consumers expect the 7-field dict format.
- load_with_vertical() returns the full list including 'vertical' — used only by
  seed.py to resolve vertical slugs to UUIDs when upserting taxonomy rows.
- _load_raw() is cached via lru_cache — YAML is read from disk only once per
  process lifetime.  Clear with _load_raw.cache_clear() in tests.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA_FILE = Path(__file__).parent / "data" / "taxonomy.yaml"


@lru_cache(maxsize=1)
def _load_raw() -> tuple[dict[str, Any], ...]:
    """
    Load raw YAML entries (including 'vertical' field) as an immutable tuple
    so lru_cache can hash the return value correctly.
    """
    try:
        import yaml  # pyyaml — same dep as prompt_loader
    except ImportError as exc:
        raise ImportError(
            "PyYAML is required to load taxonomy data. "
            "Install it with: pip install pyyaml"
        ) from exc

    with open(_DATA_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, list):
        raise ValueError(f"taxonomy.yaml must be a YAML list; got {type(data).__name__}")

    return tuple(data)


def load_with_vertical() -> list[dict[str, Any]]:
    """
    Return all taxonomy entries including the 'vertical' field.

    Used exclusively by seed.py to resolve vertical slug → vertical_id UUID
    when upserting TaxonomyItem rows.  All other consumers use TAXONOMY.
    """
    return list(_load_raw())


# ── Public constant ────────────────────────────────────────────────────────────
# Strip 'vertical' — not a TaxonomyItem column; preserves backward compatibility
# with all existing consumers (Classifier, ContractParser, etc.).

TAXONOMY: list[dict[str, Any]] = [
    {k: v for k, v in item.items() if k != "vertical"}
    for item in _load_raw()
]
