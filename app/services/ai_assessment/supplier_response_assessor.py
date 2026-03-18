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

logger = logging.getLogger(__name__)

_client = None

_VALID_ASSESSMENTS = {"SUFFICIENT", "INSUFFICIENT", "PARTIAL"}


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


_SYSTEM_PROMPT = """\
You are a claims billing compliance specialist advising an insurance carrier.
A vendor has responded to a billing exception on their invoice.
Your task is to evaluate whether the supplier's response adequately addresses
the exception and recommend how the carrier should proceed.

Assessment verdicts:
  SUFFICIENT   — The response is credible and addresses the core issue.
                 Carrier may consider waiving or accepting the exception.
  PARTIAL      — The response partially addresses the issue but has gaps.
                 Carrier should request clarification before resolving.
  INSUFFICIENT — The response does not address the issue or is clearly inadequate.
                 Carrier should consider denying or requiring resubmission.

Respond with valid JSON only — no markdown, no explanation outside the JSON.
"""

_USER_TEMPLATE = """\
ORIGINAL EXCEPTION
  Exception message: {exception_message}
  Required action:   {required_action}
  Taxonomy code:     {taxonomy_code}
  Contract:          {contract_name}

SUPPLIER RESPONSE
  {supplier_response}

Evaluate whether the supplier's response adequately addresses the billing
exception. Consider the specificity of the response, whether it provides
documentary evidence (implied or stated), and whether it explains the
discrepancy in terms of the contract requirements.

Return exactly this JSON shape:
{{
  "assessment": "<SUFFICIENT, PARTIAL, or INSUFFICIENT>",
  "reasoning": "<one paragraph (2-4 sentences) for the carrier>"
}}

Guidelines:
- If the supplier cites a specific contract clause, service circumstance, or
  provides a clear explanation matching the billed amount, lean SUFFICIENT.
- If the response is vague, generic ("we believe our billing is correct"), or
  misses the specific issue, lean INSUFFICIENT.
- If the response acknowledges the issue but doesn't fully resolve it, use PARTIAL.
- Keep reasoning concise and actionable for the carrier reviewer.
"""


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
            model="claude-haiku-4-5",
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
