"""
AI Supplier Response Assessment Agent.

When a supplier responds to a billing exception, Claude evaluates whether the
response adequately addresses the issue and recommends how the carrier should
proceed.

Graceful degradation: if ANTHROPIC_API_KEY is not set, or the API call fails
for any reason, this module returns None and the pipeline continues normally.
The ai_response_assessment and ai_response_reasoning columns stay NULL.

Output schema:
    {
        "assessment": "SUFFICIENT",    # SUFFICIENT | INSUFFICIENT | PARTIAL
        "reasoning": "<one paragraph for the carrier>"
    }
"""

import json
import logging
from typing import Optional

from app.config.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

_client = None

_VALID_ASSESSMENTS = {"SUFFICIENT", "INSUFFICIENT", "PARTIAL"}

# Prompt config — loaded from YAML at module import, cached by prompt_loader.
# Edit app/config/prompts/default/supplier_response_assessor.yaml to iterate without redeploy.
_PROMPT = load_prompt("supplier_response_assessor")
_SYSTEM_PROMPT = _PROMPT.get("system", "")
_USER_TEMPLATE = _PROMPT["user_template"]


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
        logger.warning(
            "anthropic package not installed — supplier response assessor disabled"
        )
        return None
    except Exception as exc:
        logger.warning("Could not initialise Anthropic client: %s", exc)
        return None




def assess_supplier_response(
    exception_message: str,
    required_action: str,
    supplier_response: str,
    taxonomy_code: Optional[str],
    contract_name: str,
) -> Optional[dict]:
    """
    Call Claude to evaluate a supplier's response to a billing exception.

    Args:
        exception_message:  The full validation failure message.
        required_action:    The RequiredAction constant from validation.
        supplier_response:  The text the supplier submitted as their response.
        taxonomy_code:      The taxonomy code of the line item (may be None).
        contract_name:      Name of the applicable contract.

    Returns:
        dict with keys: assessment (SUFFICIENT|INSUFFICIENT|PARTIAL), reasoning
        OR None if the API key is not set, the call fails, or the response
        cannot be parsed.
    """
    client = _get_client()
    if client is None:
        return None

    if not supplier_response or not supplier_response.strip():
        return None

    user_content = _USER_TEMPLATE.format(
        exception_message=exception_message[:600],  # cap length
        required_action=required_action,
        taxonomy_code=taxonomy_code or "N/A",
        contract_name=contract_name,
        supplier_response=supplier_response[:800],  # cap response length
    )

    try:
        message = client.messages.create(
            model=_PROMPT["model"],
            max_tokens=_PROMPT["max_tokens"],
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        raw_text = message.content[0].text.strip()

        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            lines = raw_text.splitlines()
            raw_text = "\n".join(lines[1:-1]).strip()

        data = json.loads(raw_text)

        assessment = str(data.get("assessment", "")).upper()
        if assessment not in _VALID_ASSESSMENTS:
            logger.warning(
                "Supplier response assessor returned unknown verdict %r — "
                "defaulting to PARTIAL",
                assessment,
            )
            assessment = "PARTIAL"

        reasoning = str(data.get("reasoning", ""))[:1000]  # cap length

        return {
            "assessment": assessment,
            "reasoning": reasoning,
        }

    except json.JSONDecodeError as exc:
        logger.warning("Supplier response assessor returned non-JSON: %s", exc)
        return None
    except Exception as exc:
        logger.warning("Supplier response assessor failed: %s", exc)
        return None
