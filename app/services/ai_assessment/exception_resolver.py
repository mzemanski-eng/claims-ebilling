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

logger = logging.getLogger(__name__)

_client = None

_VALID_ACTIONS = {
    "WAIVED",
    "ACCEPTED_REDUCTION",
    "HELD_CONTRACT_RATE",
    "RECLASSIFIED",
    "DENIED",
}


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


_SYSTEM_PROMPT = """\
You are drafting a short message FROM an insurance carrier billing team TO a supplier
to explain a billing exception and what happens next.

Resolution actions available (internal — do not mention in the message):
  WAIVED            — Accept the line as billed; no action needed from supplier.
  ACCEPTED_REDUCTION — Payment will be reduced to the contracted amount.
  HELD_CONTRACT_RATE — Payment capped at the contracted rate.
  RECLASSIFIED      — Line reclassified; payment processed at corrected rate.
  DENIED            — Line rejected; supplier must correct and resubmit.

Writing style for the supplier message:
- Write directly to the supplier ("we", "your", "this line").
- 1-2 short sentences only.
- Plain English — no legal or insurance jargon.
- Tell them: (1) what the issue was, and (2) what will happen or what they need to do.
- Good example: "This service wasn't covered at the rate billed under your contract —
  we'll process it at the contracted amount of $X instead."
- Good example: "We couldn't find a contracted rate for this service code, so the line
  has been removed. Please resubmit with a corrected billing code."
- Bad example: "The taxonomy code lacks an established contracted rate, creating an
  uncontrolled billing situation requiring contract amendment procedures."

Respond with valid JSON only — no markdown, no explanation outside the JSON.
"""

_USER_TEMPLATE = """\
EXCEPTION DETAILS
  Exception message: {exception_message}
  Required action:   {required_action}
  Taxonomy code:     {taxonomy_code}
  Contract:          {contract_name}
  Supplier:          {supplier_name}
  Prior exceptions on this code (last 90 days): {prior_exception_count}

Choose the best resolution action and write a 1-2 sentence plain-English message
to send to the supplier explaining the issue and outcome.

Return exactly this JSON shape:
{{
  "recommendation": "<one of the five resolution actions above>",
  "reasoning": "<1-2 sentence supplier-facing message>"
}}

Guidelines:
- If the billed amount exceeds the contracted rate, prefer HELD_CONTRACT_RATE.
- If the supplier has repeatedly had the same issue (prior_exceptions > 2),
  prefer DENIED.
- If documentation is missing, prefer DENIED with a clear resubmit instruction.
- If the taxonomy code is out of scope for this supplier, prefer DENIED.
- If the exception is minor or a first occurrence, consider WAIVED.
"""


def assess_exception(
    exception_message: str,
    required_action: str,
    taxonomy_code: Optional[str],
    contract_name: str,
    supplier_name: str,
    prior_exception_count: int,
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

    user_content = _USER_TEMPLATE.format(
        exception_message=exception_message[:600],  # cap length
        required_action=required_action,
        taxonomy_code=taxonomy_code or "N/A",
        contract_name=contract_name,
        supplier_name=supplier_name,
        prior_exception_count=prior_exception_count,
    )

    try:
        model = "claude-haiku-4-5"
        message = _get_client().messages.create(
            model=model,
            max_tokens=512,
            system=_SYSTEM_PROMPT,
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
