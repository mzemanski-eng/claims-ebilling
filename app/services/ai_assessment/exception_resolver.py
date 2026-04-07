"""
AI Exception Resolution Agent.

For each exception created during invoice processing, Claude reads the exception
context and recommends the most appropriate resolution action with reasoning.

Graceful degradation: if ANTHROPIC_API_KEY is not set, or the API call fails
for any reason, this module returns None and the pipeline continues normally.
The ai_recommendation and ai_reasoning columns stay NULL — no exceptions raised.

Output schema:
    {
        "recommendation": "HELD_CONTRACT_RATE",   # a ResolutionAction constant
        "reasoning": "<one paragraph explanation for the carrier>"
    }
"""

import json
import logging
from typing import Optional

from app.config.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

_client = None

_VALID_ACTIONS = {
    "WAIVED",
    "ACCEPTED_REDUCTION",
    "HELD_CONTRACT_RATE",
    "RECLASSIFIED",
    "DENIED",
}

# Prompt config loaded per-call via load_prompt(name, vertical=vertical).
# load_prompt uses @lru_cache(maxsize=256) so YAML is read only once per
# (name, vertical) pair across the process lifetime.


def _get_client():
    """Return an Anthropic client, or None if the SDK / API key is unavailable."""
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
        logger.warning("anthropic package not installed — exception resolver disabled")
        return None
    except Exception as exc:
        logger.warning("Could not initialise Anthropic client: %s", exc)
        return None


def assess_exception(
    exception_message: str,
    required_action: str,
    taxonomy_code: Optional[str],
    contract_name: str,
    supplier_name: str,
    prior_exception_count: int,
    vertical: str = "default",
) -> Optional[dict]:
    """
    Call Claude to recommend a resolution action for a billing exception.

    Args:
        exception_message:    The full validation failure message.
        required_action:      The RequiredAction constant from validation.
        taxonomy_code:        The taxonomy code of the line item (may be None).
        contract_name:        Name of the applicable contract.
        supplier_name:        Name of the supplier.
        prior_exception_count: How many exceptions this supplier has had on
                              this taxonomy code in the past 90 days.

    Returns:
        dict with keys: recommendation, reasoning
        OR None if the API key is not set, the call fails, or the response
        cannot be parsed.
    """
    client = _get_client()
    if client is None:
        return None

    prompt = load_prompt("exception_resolver", vertical=vertical)
    system_prompt = prompt.get("system", "")
    user_content = prompt["user_template"].format(
        exception_message=exception_message[:600],  # cap length
        required_action=required_action,
        taxonomy_code=taxonomy_code or "N/A",
        contract_name=contract_name,
        supplier_name=supplier_name,
        prior_exception_count=prior_exception_count,
    )

    try:
        model = prompt["model"]
        message = _get_client().messages.create(
            model=model,
            max_tokens=prompt["max_tokens"],
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        raw_text = message.content[0].text.strip()

        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            lines = raw_text.splitlines()
            raw_text = "\n".join(lines[1:-1]).strip()

        data = json.loads(raw_text)

        recommendation = str(data.get("recommendation", "")).upper()
        if recommendation not in _VALID_ACTIONS:
            logger.warning(
                "Exception resolver returned unknown action %r — defaulting to WAIVED",
                recommendation,
            )
            recommendation = "WAIVED"

        reasoning = str(data.get("reasoning", ""))[:1000]  # cap length

        return {
            "recommendation": recommendation,
            "reasoning": reasoning,
        }

    except json.JSONDecodeError as exc:
        logger.warning("Exception resolver returned non-JSON: %s", exc)
        return None
    except Exception as exc:
        logger.warning("Exception resolver failed: %s", exc)
        return None
