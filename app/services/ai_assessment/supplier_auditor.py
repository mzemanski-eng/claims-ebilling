"""
AI Supplier Audit Agent.

On-demand analysis of a supplier's billing history. Produces structured audit
findings — anomalies, billing pattern observations, and recommended actions —
based on invoice and exception data from the past 90 days (or all-time).

Called from POST /admin/suppliers/{id}/audit. No DB writes — returns findings
directly to the caller.

Graceful degradation: returns None if ANTHROPIC_API_KEY is not set or the call
fails. The endpoint returns a 503 in that case.

Output schema:
    {
        "risk_rating": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
        "findings": [
            {"title": "...", "detail": "...", "severity": "INFO|WARNING|ERROR"}
        ],
        "recommendations": ["action 1", "action 2", ...]
    }
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_client = None

_VALID_RATINGS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
_VALID_SEVERITIES = {"INFO", "WARNING", "ERROR"}


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
        logger.warning("anthropic package not installed — supplier auditor disabled")
        return None
    except Exception as exc:
        logger.warning("Could not initialise Anthropic client: %s", exc)
        return None


_SYSTEM_PROMPT = """\
You are a claims billing audit specialist for an insurance carrier.
Your task is to analyse a vendor supplier's billing history and produce a
structured audit report with specific findings and actionable recommendations.

Respond with valid JSON only — no markdown, no explanation outside the JSON.
"""

_USER_TEMPLATE = """\
SUPPLIER: {supplier_name}

INVOICE HISTORY (all-time)
  Total invoices:          {total_invoices}
  Approved:                {approved_count}
  Flagged for review:      {review_required_count}
  Pending approval:        {pending_count}
  Exception rate:          {exception_rate}%

TOP BILLED TAXONOMY CODES (by total amount)
{top_codes_block}

EXCEPTION PATTERNS (by taxonomy code and action required)
{exception_block}

Analyse this supplier's billing history and produce a structured audit report.

Return exactly this JSON shape:
{{
  "risk_rating": "<LOW | MEDIUM | HIGH | CRITICAL>",
  "findings": [
    {{
      "title": "<short finding title>",
      "detail": "<1-2 sentence explanation>",
      "severity": "<INFO | WARNING | ERROR>"
    }}
  ],
  "recommendations": ["<actionable recommendation 1>", "<actionable recommendation 2>", ...]
}}

Guidelines:
- Include 3-6 findings covering billing patterns, exception trends, and any anomalies.
- Recommendations should be specific and actionable (e.g., "Add max_units guideline for
  ENG.STRUCT.L1 — supplier has billed above contract maximum on 3 invoices").
- Use ERROR severity for findings that indicate systematic billing violations.
- Use WARNING for patterns that warrant closer monitoring.
- Use INFO for neutral observations about billing behaviour.
- Keep findings and recommendations concise and professional.
"""


def _format_top_codes(top_codes: list[dict]) -> str:
    if not top_codes:
        return "  No billing data available."
    lines = []
    for row in top_codes[:10]:
        lines.append(
            f"  {row.get('taxonomy_code', 'N/A'):<35} "
            f"${float(row.get('total_billed', 0)):>10,.2f}  "
            f"({row.get('invoice_count', 0)} invoices)"
        )
    return "\n".join(lines)


def _format_exceptions(exception_summary: list[dict]) -> str:
    if not exception_summary:
        return "  No exceptions on record."
    lines = []
    for row in exception_summary[:15]:
        lines.append(
            f"  {row.get('taxonomy_code', 'N/A'):<35} "
            f"{row.get('required_action', 'N/A'):<30} "
            f"count: {row.get('count', 0)}"
        )
    return "\n".join(lines)


def audit_supplier(
    supplier_name: str,
    invoice_summary: list[dict],
    exception_summary: list[dict],
    top_codes: list[dict],
) -> Optional[dict]:
    """
    Call Claude to produce a structured audit report for a supplier.

    Args:
        supplier_name:      Supplier display name.
        invoice_summary:    List of dicts: [{status, count}] — invoice counts by status.
        exception_summary:  List of dicts: [{taxonomy_code, required_action, count}].
        top_codes:          List of dicts: [{taxonomy_code, total_billed, invoice_count}]
                            — top 10 taxonomy codes by spend.

    Returns:
        dict with keys: risk_rating (str), findings (list), recommendations (list)
        OR None if the API key is not set or the call fails.
    """
    client = _get_client()
    if client is None:
        return None

    # Build status counts
    counts_by_status = {row.get("status", ""): row.get("count", 0) for row in invoice_summary}
    total_invoices = sum(counts_by_status.values())
    approved = counts_by_status.get("APPROVED", 0) + counts_by_status.get("EXPORTED", 0)
    review_required = counts_by_status.get("REVIEW_REQUIRED", 0)
    pending = counts_by_status.get("PENDING_CARRIER_REVIEW", 0)
    total_with_exceptions = review_required + counts_by_status.get("SUPPLIER_RESPONDED", 0)
    exception_rate = round(total_with_exceptions / total_invoices * 100, 1) if total_invoices else 0

    user_content = _USER_TEMPLATE.format(
        supplier_name=supplier_name,
        total_invoices=total_invoices,
        approved_count=approved,
        review_required_count=review_required,
        pending_count=pending,
        exception_rate=exception_rate,
        top_codes_block=_format_top_codes(top_codes),
        exception_block=_format_exceptions(exception_summary),
    )

    try:
        model = "claude-haiku-4-5"
        message = _get_client().messages.create(
            model=model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        raw_text = message.content[0].text.strip()

        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            lines = raw_text.splitlines()
            raw_text = "\n".join(lines[1:-1]).strip()

        data = json.loads(raw_text)

        risk_rating = str(data.get("risk_rating", "")).upper()
        if risk_rating not in _VALID_RATINGS:
            risk_rating = "MEDIUM"

        findings = []
        for f in data.get("findings", [])[:8]:  # cap at 8
            severity = str(f.get("severity", "INFO")).upper()
            if severity not in _VALID_SEVERITIES:
                severity = "INFO"
            findings.append({
                "title": str(f.get("title", ""))[:100],
                "detail": str(f.get("detail", ""))[:400],
                "severity": severity,
            })

        recommendations = [
            str(r)[:300] for r in data.get("recommendations", [])
        ][:6]  # cap at 6

        return {
            "risk_rating": risk_rating,
            "findings": findings,
            "recommendations": recommendations,
        }

    except json.JSONDecodeError as exc:
        logger.warning("Supplier auditor returned non-JSON for %r: %s", supplier_name, exc)
        return None
    except Exception as exc:
        logger.warning("Supplier auditor failed for %r: %s", supplier_name, exc)
        return None
