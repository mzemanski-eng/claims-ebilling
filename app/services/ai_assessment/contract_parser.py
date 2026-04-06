"""
AI Contract Parser.

Uses Claude (via the Anthropic SDK) to extract contract metadata, rate cards,
and billing guidelines from a PDF uploaded by an admin user.

Follows the same lazy-singleton + graceful-failure pattern as description_assessor.py.

Graceful degradation: if ANTHROPIC_API_KEY is not set, or the API call fails
for any reason, returns a near-empty ParsedContractResult with extraction_notes
explaining why.  The caller (parse-pdf endpoint) returns the result to the
frontend WITHOUT saving anything to the DB — the user reviews and confirms.
"""

import base64
import json
import logging
from datetime import date

from app.config.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

# Prompt config — loaded from YAML at module import, cached by prompt_loader.
# Edit app/config/prompts/default/contract_parser.yaml to iterate without redeploy.
_PROMPT = load_prompt("contract_parser")
_SYSTEM_PROMPT = _PROMPT.get("system", "")
_USER_TEMPLATE = _PROMPT["user_template"]

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
        logger.warning("anthropic package not installed — contract parsing disabled")
        return None
    except Exception as exc:
        logger.warning("Could not initialise Anthropic client: %s", exc)
        return None


def _build_taxonomy_block() -> str:
    """
    Build a compact string listing all valid taxonomy codes, labels, and unit
    models. TAXONOMY is a list[dict], not a dict — iterate with for item in TAXONOMY.
    """
    try:
        from app.taxonomy.constants import TAXONOMY  # list of dicts

        lines = []
        for item in TAXONOMY:
            code = item["code"]
            label = item.get("label", code)
            unit_model = item.get("unit_model", "")
            lines.append(f"  {code} — {label} ({unit_model})")
        return "\n".join(lines)
    except Exception as exc:
        logger.warning("Could not load taxonomy constants: %s", exc)
        return "  (taxonomy unavailable)"




def _empty_result(supplier_id: str, notes: str) -> dict:
    """Return an empty (but valid) ParsedContractResult when parsing fails."""
    today = date.today().isoformat()
    return {
        "contract": {
            "supplier_id": supplier_id,
            "name": "Untitled Contract",
            "effective_from": today,
            "effective_to": None,
            "geography_scope": "national",
            "state_codes": None,
            "notes": None,
        },
        "rate_cards": [],
        "guidelines": [],
        "extraction_notes": notes,
    }


def _validate_taxonomy_codes(rate_cards: list[dict]) -> list[dict]:
    """Remove rate cards that reference codes not in our taxonomy registry."""
    try:
        from app.taxonomy.constants import TAXONOMY  # list of dicts

        valid_codes = {item["code"] for item in TAXONOMY}
    except Exception:
        return rate_cards  # can't validate — pass through unchanged

    cleaned = []
    for rc in rate_cards:
        code = rc.get("taxonomy_code", "")
        if code in valid_codes:
            cleaned.append(rc)
        else:
            logger.warning(
                "AI returned unknown taxonomy code %r — dropping rate card", code
            )
    return cleaned


def parse_contract(pdf_bytes: bytes, supplier_id: str, db) -> dict:
    """
    Send PDF to Claude (native document type) and extract contract data.

    Args:
        pdf_bytes:   Raw PDF bytes from the uploaded file.
        supplier_id: UUID string of the supplier (pre-fills the contract payload).
        db:          SQLAlchemy session (reserved for future lookups).

    Returns:
        ParsedContractResult-shaped dict. Never raises — failures are reported
        in extraction_notes with an empty rate_cards/guidelines payload.
    """
    client = _get_client()
    if client is None:
        return _empty_result(
            supplier_id,
            "AI parsing is unavailable (ANTHROPIC_API_KEY not set). "
            "Please enter the contract details manually.",
        )

    taxonomy_block = _build_taxonomy_block()
    user_text = _USER_TEMPLATE.format(
        taxonomy_block=taxonomy_block,
        supplier_id=supplier_id,
    )
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    try:
        model = _PROMPT["model"]
        message = client.messages.create(
            model=model,
            max_tokens=_PROMPT["max_tokens"],
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": user_text,
                        },
                    ],
                }
            ],
        )

        raw_text = message.content[0].text.strip()

        # Strip markdown code fences if the model wraps the JSON despite instructions
        if raw_text.startswith("```"):
            lines = raw_text.splitlines()
            raw_text = "\n".join(lines[1:-1]).strip()

        data = json.loads(raw_text)

        # Validate taxonomy codes — drop hallucinated codes silently
        if "rate_cards" in data:
            data["rate_cards"] = _validate_taxonomy_codes(data["rate_cards"])

        # Always override supplier_id from our parameter — never trust PDF content
        if "contract" in data:
            data["contract"]["supplier_id"] = supplier_id

        return data

    except json.JSONDecodeError as exc:
        logger.warning("Contract parser returned non-JSON: %s", exc)
        return _empty_result(
            supplier_id,
            "AI extraction failed — the model returned an unstructured response. "
            "Please enter the contract details manually.",
        )
    except Exception as exc:
        logger.warning("Contract parsing failed: %s", exc)
        return _empty_result(
            supplier_id,
            "AI extraction encountered an error. Please enter the contract details manually.",
        )
