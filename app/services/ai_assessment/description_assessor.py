"""
AI Description Alignment Assessor.

Uses Claude (via the Anthropic SDK) to semantically assess whether a supplier's
invoice line description is consistent with the contracted service it was
classified under.

Graceful degradation: if ANTHROPIC_API_KEY is not set, or the API call fails
for any reason, this module returns None and the pipeline continues normally.
The ai_description_assessment column stays NULL — no exceptions are raised.

Assessment schema (stored as JSONB on LineItem):
    {
        "score": "ALIGNED" | "PARTIAL" | "MISALIGNED",
        "rationale": "<one sentence>",
        "model": "claude-haiku-4-5"
    }

Score definitions:
    ALIGNED     — Description clearly refers to the contracted service type,
                  even if worded differently (e.g., abbreviations, synonyms).
    PARTIAL     — Description is vague, ambiguous, or only partially identifies
                  the service; the classification may be correct but it's unclear.
    MISALIGNED  — Description appears to describe a different service than
                  what was contracted. Warrants manual review.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy-loaded client — only imported when actually needed
_client = None


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
            "anthropic package not installed — AI description assessment disabled"
        )
        return None
    except Exception as exc:
        logger.warning("Could not initialise Anthropic client: %s", exc)
        return None


_SYSTEM_PROMPT = """\
You are an insurance claims billing auditor reviewing invoice line items.
Your task is to assess whether a supplier's invoice description is semantically
consistent with the contracted service type it was classified under.

Respond with valid JSON only — no markdown, no explanation outside the JSON.
"""

_USER_TEMPLATE = """\
CONTRACT SERVICE
  Label:       {taxonomy_label}
  Description: {taxonomy_description}

SUPPLIER INVOICE LINE
  Description: "{raw_description}"

Assess whether the supplier's description is consistent with the contracted service.

Return exactly this JSON shape:
{{
  "score": "<ALIGNED | PARTIAL | MISALIGNED>",
  "rationale": "<one concise sentence>"
}}

Scoring guide:
  ALIGNED    — Description clearly refers to the same service type, even if worded differently.
  PARTIAL    — Description is vague, ambiguous, or only partially describes the service.
  MISALIGNED — Description appears to be a different type of service than contracted.
"""


def assess_description_alignment(
    raw_description: str,
    taxonomy_label: str,
    taxonomy_description: Optional[str],
) -> Optional[dict]:
    """
    Call Claude to assess whether raw_description aligns with the taxonomy item.

    Args:
        raw_description:    The supplier's invoice line description.
        taxonomy_label:     Short human-readable label of the taxonomy item.
        taxonomy_description: Longer taxonomy description (may be None/empty).

    Returns:
        dict with keys: score, rationale, model
        OR None if the API key is not set, the call fails, or the response
        cannot be parsed.
    """
    client = _get_client()
    if client is None:
        return None

    desc = taxonomy_description or taxonomy_label  # fall back to label if no description

    user_content = _USER_TEMPLATE.format(
        taxonomy_label=taxonomy_label,
        taxonomy_description=desc,
        raw_description=raw_description,
    )

    try:
        model = "claude-haiku-4-5"
        message = client.messages.create(
            model=model,
            max_tokens=256,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        raw_text = message.content[0].text.strip()

        # Parse JSON response
        data = json.loads(raw_text)

        score = data.get("score", "").upper()
        if score not in ("ALIGNED", "PARTIAL", "MISALIGNED"):
            logger.warning(
                "AI assessor returned unexpected score %r for description %r",
                score,
                raw_description[:60],
            )
            return None

        return {
            "score": score,
            "rationale": str(data.get("rationale", ""))[:500],  # cap length
            "model": model,
        }

    except json.JSONDecodeError as exc:
        logger.warning(
            "AI assessor returned non-JSON response for %r: %s",
            raw_description[:60],
            exc,
        )
        return None
    except Exception as exc:
        logger.warning(
            "AI assessment failed for description %r: %s",
            raw_description[:60],
            exc,
        )
        return None
