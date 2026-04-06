"""
Prompt configuration loader.

Loads AI prompt configs from YAML files under app/config/prompts/{vertical}/.
Supports per-vertical overrides: call load_prompt("name", vertical="restoration")
to get a restoration-specific prompt, with automatic fallback to "default" if the
vertical-specific file doesn't exist.

Configs are cached via lru_cache — identical (name, vertical) pairs are read
from disk only once per process lifetime.  Call reload_prompts() to clear the
cache (e.g. in tests or after a hot-file update without restart).

YAML schema expected for each prompt file:
    model: claude-haiku-4-5          # Anthropic model name
    max_tokens: 512                  # max_tokens for the API call
    system: |                        # optional; omit for no system prompt
      You are a...
    user_template: |                 # required; Python .format()-style template
      CONTEXT
        Field: {variable_name}
      ...

Note on brace escaping: user_template is processed via Python str.format(), so
use {variable} for placeholders and {{ / }} for literal braces in the template
(they appear as { / } in the final prompt sent to the model).
"""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"


@lru_cache(maxsize=256)
def load_prompt(name: str, vertical: str = "default") -> dict[str, Any]:
    """
    Load and cache a prompt config by name and vertical.

    Args:
        name:     Prompt name — must match a YAML filename without extension,
                  e.g. "invoice_triage" maps to prompts/{vertical}/invoice_triage.yaml.
        vertical: Vertical override directory name.  Defaults to "default".
                  Falls back to "default" automatically when the requested
                  vertical directory or file does not exist.

    Returns:
        dict with at minimum the keys: model, max_tokens, user_template.
        The "system" key is present only when a system prompt is configured.

    Raises:
        FileNotFoundError: When neither the vertical-specific nor default file exists.
        ValueError:        When the YAML file is missing required keys.
    """
    try:
        import yaml  # Optional dep — only needed when prompts are actually loaded
    except ImportError as exc:
        raise ImportError(
            "PyYAML is required to load prompt configs. "
            "Install it with: pip install pyyaml"
        ) from exc

    # Resolve path: try requested vertical first, fall back to default
    path = _PROMPTS_DIR / vertical / f"{name}.yaml"
    if not path.exists():
        if vertical != "default":
            logger.debug(
                "Prompt '%s' not found for vertical '%s' — falling back to default",
                name,
                vertical,
            )
        path = _PROMPTS_DIR / "default" / f"{name}.yaml"

    if not path.exists():
        raise FileNotFoundError(
            f"Prompt config '{name}' not found. "
            f"Expected: {_PROMPTS_DIR / vertical / name}.yaml "
            f"or {_PROMPTS_DIR / 'default' / name}.yaml"
        )

    with open(path, encoding="utf-8") as f:
        config: dict = yaml.safe_load(f)

    # Validate required fields
    for required_key in ("model", "max_tokens", "user_template"):
        if required_key not in config:
            raise ValueError(
                f"Prompt config '{path}' is missing required key '{required_key}'"
            )

    logger.debug("Loaded prompt config '%s' (vertical=%s) from %s", name, vertical, path)
    return config


def reload_prompts() -> None:
    """Clear the prompt config cache. Useful in tests or after YAML edits."""
    load_prompt.cache_clear()
    logger.info("Prompt config cache cleared")
