"""
AI Invoice Triage Agent.

At the start of each invoice pipeline run, Claude scores the invoice for risk
based on supplier history, invoice characteristics, and billing patterns.

Graceful degradation: if ANTHROPIC_API_KEY is not set, or the API call fails
for any reason, this module returns None and the pipeline continues normally.
The triage_risk_level and triage_notes columns stay NULL — no exceptions raised.

Output schema:
    {
        "risk_level": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
        "risk_factors": ["factor 1", "factor 2", ...]
    }

Risk level definitions:
    LOW      — Established supplier, clean history, invoice within normal range.
    MEDIUM   — Minor anomalies (slightly elevated amount, occasional exceptions).
    HIGH     — Notable concerns: new supplier, significant amount, exception history.
    CRITICAL — Serious red flags: repeated exceptions, large amount, scope creep.
"""

import json
import logging
from typing import Optional

from app.config.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

_client = None

_VALID_LEVELS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

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
        logger.warning("anthropic package not installed — invoice triage disabled")
        return None
    except Exception as exc:
        logger.warning("Could not initialise Anthropic client: %s", exc)
        return None




def triage_invoice(
    supplier_name: str,
    invoice_number: str,
    invoice_date: str,
    line_item_count: int,
    estimated_total: float,
    prior_review_required_count: int,
    vertical: str = "default",
) -> Optional[dict]:
    """
    Call Claude to assign a risk level to an incoming invoice.

    Args:
        supplier_name:               Supplier display name.
        invoice_number:              Supplier's invoice reference number.
        invoice_date:                Invoice date as ISO string.
        line_item_count:             Number of line items parsed from the file.
        estimated_total:             Rough total billed (sum of raw amounts if available).
        prior_review_required_count: Number of REVIEW_REQUIRED invoices from this
                                     supplier in the past 90 days.

    Returns:
        dict with keys: risk_level (str), risk_factors (list[str])
        OR None if the API key is not set, the call fails, or the response
        cannot be parsed.
    """
    client = _get_client()
    if client is None:
        return None

    prompt = load_prompt("invoice_triage", vertical=vertical)
    system_prompt = prompt.get("system", "")
    user_content = prompt["user_template"].format(
        supplier_name=supplier_name,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        line_item_count=line_item_count,
        estimated_total=estimated_total,
        prior_review_required_count=prior_review_required_count,
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

        risk_level = str(data.get("risk_level", "")).upper()
        if risk_level not in _VALID_LEVELS:
            logger.warning(
                "Triage returned unknown risk level %r for invoice %r",
                risk_level,
                invoice_number,
            )
            risk_level = "MEDIUM"  # conservative default

        risk_factors = [str(f)[:200] for f in data.get("risk_factors", [])][
            :6
        ]  # cap at 6 factors

        return {
            "risk_level": risk_level,
            "risk_factors": risk_factors,
        }

    except json.JSONDecodeError as exc:
        logger.warning(
            "Invoice triage returned non-JSON for %r: %s", invoice_number, exc
        )
        return None
    except Exception as exc:
        logger.warning("Invoice triage failed for %r: %s", invoice_number, exc)
        return None
