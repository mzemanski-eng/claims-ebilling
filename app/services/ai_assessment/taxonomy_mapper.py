"""
Taxonomy Mapper — AI matching of one supplier billing code to a platform taxonomy code.

Called row-by-row from POST /admin/suppliers/{id}/taxonomy-import.
No DB writes — caller creates MappingRule entries from the returned dict.

The taxonomy_items list is pre-fetched by the caller before the loop to avoid
N+1 DB queries. Pass the same list for every row in the same import job.

Graceful degradation: returns None if ANTHROPIC_API_KEY is not set or the call
fails. The endpoint treats None rows as "unmapped" and continues processing
remaining rows rather than aborting the import.

Output schema (per row):
    {
        "taxonomy_code": str | None,   # matched taxonomy code, or None
        "confidence": "HIGH" | "MEDIUM" | "LOW" | None
    }
"""

import json
import logging
from typing import Optional

from app.config.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

_client = None

_VALID_CONFIDENCES = {"HIGH", "MEDIUM", "LOW"}

# Cached at module import — edit taxonomy_mapper.yaml to iterate without redeploy.
_PROMPT = load_prompt("taxonomy_mapper")
_SYSTEM_PROMPT = _PROMPT.get("system", "")
_USER_TEMPLATE = _PROMPT["user_template"]

# Confidence → weight mapping (mirrors MappingRule confidence_weight semantics)
_CONFIDENCE_WEIGHTS = {
    "HIGH": 0.9,
    "MEDIUM": 0.6,
    "LOW": 0.3,
}


def _get_client():
    """Return an Anthropic client, or None if SDK / API key unavailable."""
    global _client
    if _client is not None:
        return _client
    try:
        from app.settings import settings

        if not settings.anthropic_api_key:
            return None
        import anthropic

        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        return _client
    except ImportError:
        logger.warning("anthropic package not installed — taxonomy mapper disabled")
        return None
    except Exception as exc:
        logger.warning("Could not initialise Anthropic client: %s", exc)
        return None


def _build_taxonomy_block(taxonomy_items: list[dict]) -> str:
    """Format taxonomy items into a compact tabular string for the prompt."""
    lines = []
    for item in taxonomy_items:
        code = item.get("code", "")
        label = (item.get("label") or "")[:40]
        domain = item.get("domain", "")
        description = (item.get("description") or "")[:80]
        lines.append(f"  {code:<45} {label:<40} {domain:<12} {description}")
    return "\n".join(lines)


def match_supplier_code(
    supplier_code: str,
    description: str,
    taxonomy_items: list[dict],
) -> Optional[dict]:
    """
    Call Claude to match one supplier billing entry to a platform taxonomy code.

    Args:
        supplier_code:   The supplier's internal billing code string.
        description:     The supplier's description of the line item.
        taxonomy_items:  Pre-fetched list of dicts: [{code, label, domain, description}]
                         — pass the same list for all rows in an import job to avoid
                         rebuilding the taxonomy block on every call.

    Returns:
        {"taxonomy_code": str | None, "confidence": "HIGH"|"MEDIUM"|"LOW"|None}
        OR None if the API call fails (caller treats as "unmapped").
    """
    client = _get_client()
    if client is None:
        return None

    taxonomy_block = _build_taxonomy_block(taxonomy_items)

    user_content = _USER_TEMPLATE.format(
        supplier_code=supplier_code,
        description=description,
        taxonomy_block=taxonomy_block,
    )

    try:
        model = _PROMPT["model"]
        message = client.messages.create(
            model=model,
            max_tokens=_PROMPT["max_tokens"],
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        raw_text = message.content[0].text.strip()

        # Strip markdown fences if present
        if raw_text.startswith("```"):
            lines = raw_text.splitlines()
            raw_text = "\n".join(lines[1:-1]).strip()

        data = json.loads(raw_text)

        taxonomy_code = data.get("taxonomy_code")
        if taxonomy_code is not None:
            taxonomy_code = str(taxonomy_code).strip() or None

        confidence = str(data.get("confidence", "")).upper()
        if confidence not in _VALID_CONFIDENCES:
            confidence = None

        # Validate that the returned code actually exists in our taxonomy list
        # to prevent hallucinated codes from being written as MappingRules
        if taxonomy_code is not None:
            valid_codes = {item["code"] for item in taxonomy_items}
            if taxonomy_code not in valid_codes:
                logger.warning(
                    "taxonomy_mapper: model returned unknown code %r for supplier_code=%r — treating as no match",
                    taxonomy_code,
                    supplier_code,
                )
                taxonomy_code = None
                confidence = None

        return {"taxonomy_code": taxonomy_code, "confidence": confidence}

    except json.JSONDecodeError as exc:
        logger.warning(
            "taxonomy_mapper: non-JSON response for supplier_code=%r: %s",
            supplier_code,
            exc,
        )
        return None
    except Exception as exc:
        logger.warning(
            "taxonomy_mapper: failed for supplier_code=%r: %s",
            supplier_code,
            exc,
        )
        return None


def confidence_to_weight(confidence: Optional[str]) -> float:
    """
    Convert a confidence label to a numeric weight for MappingRule.confidence_weight.

    HIGH → 0.9, MEDIUM → 0.6, LOW → 0.3, None → 0.3 (default to lowest).
    """
    return _CONFIDENCE_WEIGHTS.get(confidence or "", 0.3)
