"""
Backward-compat shim — TAXONOMY list is now loaded from taxonomy.yaml via loader.py.

All code that does `from app.taxonomy.constants import TAXONOMY` continues to work
unchanged.  Edit app/taxonomy/data/taxonomy.yaml to add, remove, or modify codes.
"""

from app.taxonomy.loader import TAXONOMY  # noqa: F401

__all__ = ["TAXONOMY"]
