"""
VerticalConfig — derives the active vertical from a Contract for prompt routing.

Usage in the invoice pipeline::

    from app.taxonomy.vertical_config import VerticalConfig

    vertical_cfg = VerticalConfig.from_contract(contract)
    vertical = vertical_cfg.slug  # "ale" | "restoration" | "legal" | "default"

    triage_result = triage_invoice(..., vertical=vertical)

The slug maps directly to a subdirectory name under app/config/prompts/.
load_prompt(name, vertical=slug) will fall back to "default" automatically
if no override file exists for the given vertical.
"""

from dataclasses import dataclass

# Only slugs matching a seeded Vertical row and a prompts/ subdirectory are valid.
_VALID_SLUGS = {"ale", "restoration", "legal"}


@dataclass(frozen=True)
class VerticalConfig:
    """
    Immutable configuration object representing the vertical context for one
    invoice processing run.

    Attributes:
        slug: The prompt-directory slug to pass to load_prompt().
              Always one of: "ale", "restoration", "legal", "default".
        name: Human-readable display name (e.g. "Restoration", "Default").
    """

    slug: str
    name: str

    @classmethod
    def from_contract(cls, contract) -> "VerticalConfig":
        """
        Derive a VerticalConfig from a Contract ORM instance.

        Returns the contract's vertical if it is active and recognised,
        otherwise returns the "default" vertical (which maps to the
        prompts/default/ directory — no per-vertical overrides).

        Args:
            contract: A Contract ORM instance with an optional .vertical
                      relationship loaded (may be None).
        """
        v = getattr(contract, "vertical", None)
        if v is not None and getattr(v, "is_active", False) and v.slug in _VALID_SLUGS:
            return cls(slug=v.slug, name=v.name)
        return cls(slug="default", name="Default")
