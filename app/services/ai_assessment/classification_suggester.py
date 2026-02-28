"""
AI Classification Suggester.

Uses Claude (via the Anthropic SDK) to assess UNRECOGNIZED invoice line items —
those where the rule-based classifier returned no match — and produce one of three
verdicts:

  SUGGESTED    — The charge is a legitimate billable service and maps to a known
                 taxonomy code. Returns suggested_code, confidence, and rationale.
  TAXONOMY_GAP — The charge appears to be a legitimate billable service but no
                 taxonomy code covers it. Ops should consider adding a new code.
  OUT_OF_SCOPE — The charge is not a legitimate billable service (e.g. meals,
                 personal expenses, unrelated items).

Graceful degradation: if ANTHROPIC_API_KEY is not set, or the API call fails
for any reason, this module returns None and the pipeline continues normally.
The ai_classification_suggestion column stays NULL — no exceptions are raised.

Suggestion schema (stored as JSONB on LineItem):
    {
        "verdict": "SUGGESTED" | "TAXONOMY_GAP" | "OUT_OF_SCOPE",
        "suggested_code": "IME.RECORDS_REVIEW.PROF_FEE" | null,
        "suggested_billing_component": "PROF_FEE" | null,
        "confidence": "HIGH" | "MEDIUM" | "LOW" | null,
        "rationale": "<one sentence>",
        "model": "claude-haiku-4-5"
    }
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy-loaded client — only imported when actually needed
_client = None

# Build a set of valid codes and a compact taxonomy block for prompting.
# Constructed once at import time; both are derived from the canonical list.
_TAXONOMY_CODES: Optional[set] = None
_TAXONOMY_BLOCK: Optional[str] = None


def _get_taxonomy_data() -> tuple[set, str]:
    """Return (set_of_valid_codes, formatted_block_string). Built lazily and cached."""
    global _TAXONOMY_CODES, _TAXONOMY_BLOCK
    if _TAXONOMY_CODES is None:
        from app.taxonomy.constants import TAXONOMY

        _TAXONOMY_CODES = {entry["code"] for entry in TAXONOMY}
        _TAXONOMY_BLOCK = "\n".join(
            f"  {entry['code']}: {entry['label']}" for entry in TAXONOMY
        )
    return _TAXONOMY_CODES, _TAXONOMY_BLOCK  # type: ignore[return-value]


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
            "anthropic package not installed — AI classification suggestion disabled"
        )
        return None
    except Exception as exc:
        logger.warning("Could not initialise Anthropic client: %s", exc)
        return None


def suggest_classification(
    raw_description: str,
    raw_code: Optional[str],
) -> Optional[dict]:
    """
    Call Claude to assess an UNRECOGNIZED invoice line item.

    Args:
        raw_description: The supplier's invoice line description.
        raw_code:        The supplier's own billing code (may be None/empty).

    Returns:
        dict with keys: verdict, suggested_code, suggested_billing_component,
                        confidence, rationale, model
        OR None if the API key is not set, the call fails, or the response
        cannot be parsed / validated.
    """
    client = _get_client()
    if client is None:
        return None

    valid_codes, taxonomy_block = _get_taxonomy_data()

    billed_code_line = (
        f"  Billed code:  {raw_code}" if raw_code else "  Billed code:  (none provided)"
    )

    prompt = f"""You are a billing auditor reviewing an insurance claims invoice line item that could not be automatically classified against the contracted service taxonomy.

Available taxonomy codes:
{taxonomy_block}

Line item to assess:
  Description: {raw_description}
{billed_code_line}

Return ONLY valid JSON (no markdown fences, no extra text) with this exact shape:
{{
  "verdict": "SUGGESTED" | "TAXONOMY_GAP" | "OUT_OF_SCOPE",
  "suggested_code": "<taxonomy code from the list above, or null>",
  "confidence": "HIGH" | "MEDIUM" | "LOW" | null,
  "rationale": "<one concise sentence explaining your verdict>"
}}

Rules:
- SUGGESTED: The charge is a legitimate billable service that maps cleanly to one of
  the listed taxonomy codes. Set suggested_code to the EXACT code from the list above
  (copy it verbatim). Set confidence to HIGH, MEDIUM, or LOW.
- TAXONOMY_GAP: The charge appears to be a legitimate billable service but none of
  the listed codes cover it. Set suggested_code and confidence to null.
- OUT_OF_SCOPE: The charge is not a legitimate billable service
  (e.g. meals not tied to physician travel, personal expenses, unrelated items).
  Set suggested_code and confidence to null.
"""

    try:
        model = "claude-haiku-4-5"
        message = client.messages.create(
            model=model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = message.content[0].text.strip()

        # Strip markdown code fences — haiku sometimes wraps JSON in ```json ... ```
        # despite instructions. Handle both ```json and plain ```.
        if raw_text.startswith("```"):
            lines = raw_text.splitlines()
            raw_text = "\n".join(lines[1:-1]).strip()

        data = json.loads(raw_text)

        verdict = data.get("verdict", "").upper()
        if verdict not in ("SUGGESTED", "TAXONOMY_GAP", "OUT_OF_SCOPE"):
            logger.warning(
                "AI suggester returned unknown verdict %r for description %r",
                verdict,
                raw_description[:60],
            )
            return None

        suggested_code = data.get("suggested_code")
        confidence = data.get("confidence")

        # Validate suggested_code against known taxonomy to prevent hallucinated codes.
        if verdict == "SUGGESTED":
            if not suggested_code or suggested_code not in valid_codes:
                logger.warning(
                    "AI suggester returned unknown/invalid taxonomy code %r for %r "
                    "— downgrading to TAXONOMY_GAP",
                    suggested_code,
                    raw_description[:60],
                )
                verdict = "TAXONOMY_GAP"
                suggested_code = None
                confidence = None

        # For non-SUGGESTED verdicts, ensure code + confidence are null.
        if verdict != "SUGGESTED":
            suggested_code = None
            confidence = None

        # Derive billing_component from the last segment of the code.
        suggested_billing_component = (
            suggested_code.rsplit(".", 1)[-1] if suggested_code else None
        )

        return {
            "verdict": verdict,
            "suggested_code": suggested_code,
            "suggested_billing_component": suggested_billing_component,
            "confidence": confidence,
            "rationale": str(data.get("rationale", ""))[:500],
            "model": model,
        }

    except json.JSONDecodeError as exc:
        logger.warning(
            "AI suggester returned non-JSON response for %r: %s",
            raw_description[:60],
            exc,
        )
        return None
    except Exception as exc:
        logger.warning(
            "AI classification suggestion failed for %r: %s",
            raw_description[:60],
            exc,
        )
        return None
