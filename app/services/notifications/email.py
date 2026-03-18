"""
Supplier notification email service.

Sends transactional emails to all active users attached to a supplier when
invoice or exception status changes occur. Uses Python's built-in smtplib —
no external dependencies required.

Configuration (via environment variables / .env):
    SMTP_HOST        SMTP server hostname           (default: disabled)
    SMTP_PORT        SMTP port                      (default: 587)
    SMTP_USER        SMTP login username            (default: "")
    SMTP_PASSWORD    SMTP login password            (default: "")
    SMTP_FROM        Sender address                 (default: SMTP_USER)
    SMTP_USE_TLS     Use STARTTLS                   (default: true)

Compatible with any SMTP provider (Postmark, SendGrid, Gmail, etc.).
If SMTP_HOST is not set, notifications are silently skipped — the pipeline
continues normally without email delivery.

Trigger points:
    notify_invoice_flagged()    → REVIEW_REQUIRED — exceptions found
    notify_invoice_approved()   → APPROVED / PENDING_CARRIER_REVIEW
    notify_exception_resolved() → exception resolved by carrier
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from app.settings import settings

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _build_message(
    to_addresses: list[str],
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = ", ".join(to_addresses)
    msg.attach(MIMEText(body_text, "plain"))
    if body_html:
        msg.attach(MIMEText(body_html, "html"))
    return msg


def _send(
    to_addresses: list[str],
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
) -> None:
    """
    Send a single email. Silently no-ops if SMTP_HOST is not configured.
    Logs errors but never raises — callers must never fail because of email.
    """
    if not settings.smtp_host:
        logger.debug("SMTP not configured — skipping notification: %s", subject)
        return
    if not to_addresses:
        logger.debug("No recipients — skipping notification: %s", subject)
        return

    try:
        msg = _build_message(to_addresses, subject, body_text, body_html)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(msg["From"], to_addresses, msg.as_string())
        logger.info("Email sent to %d recipient(s): %s", len(to_addresses), subject)
    except Exception as exc:
        # Never propagate — email failure must not break invoice processing
        logger.error("Email delivery failed for '%s': %s", subject, exc)


def _supplier_emails(db, supplier_id: str) -> list[str]:
    """Return email addresses for all active users linked to this supplier."""
    from app.models.supplier import User

    users = (
        db.query(User.email)
        .filter(User.supplier_id == supplier_id, User.is_active.is_(True))
        .all()
    )
    return [row.email for row in users]


# ── Public notification functions ─────────────────────────────────────────────


def notify_invoice_flagged(db, invoice) -> None:
    """
    Notify supplier users that their invoice has exceptions requiring attention.
    Fires when invoice status transitions to REVIEW_REQUIRED.
    """
    recipients = _supplier_emails(db, str(invoice.supplier_id))
    if not recipients:
        return

    invoice_ref = invoice.invoice_number or str(invoice.id)[:8].upper()
    subject = f"Action Required: Invoice {invoice_ref} has exceptions"

    body_text = f"""\
Hi,

Invoice {invoice_ref} has been reviewed and requires your attention.

One or more line items could not be validated against the contracted rates
or billing guidelines. Please log in to the billing portal to review the
flagged exceptions and take the required action.

Invoice: {invoice_ref}
Status: Flagged for Review

Please review and respond as soon as possible to avoid payment delays.

This is an automated notification from the eBilling platform.
"""

    body_html = f"""\
<html><body style="font-family:Arial,sans-serif;color:#111;max-width:600px">
  <h2 style="color:#DC2626">⚠ Action Required: Invoice {invoice_ref}</h2>
  <p>Invoice <strong>{invoice_ref}</strong> has been reviewed and requires your attention.</p>
  <p>One or more line items could not be validated against the contracted rates
  or billing guidelines.</p>
  <p><strong>Please log in to the billing portal</strong> to review the flagged
  exceptions and take the required action.</p>
  <table style="border-collapse:collapse;width:100%;margin:16px 0">
    <tr><td style="padding:8px;background:#F3F4F6;font-weight:bold">Invoice</td>
        <td style="padding:8px">{invoice_ref}</td></tr>
    <tr><td style="padding:8px;background:#F3F4F6;font-weight:bold">Status</td>
        <td style="padding:8px;color:#DC2626">Flagged for Review</td></tr>
  </table>
  <p style="color:#6B7280;font-size:12px">This is an automated notification from the eBilling platform.</p>
</body></html>
"""
    _send(recipients, subject, body_text, body_html)


def notify_invoice_approved(db, invoice) -> None:
    """
    Notify supplier users that their invoice has been approved.
    Fires when invoice status transitions to APPROVED.
    """
    recipients = _supplier_emails(db, str(invoice.supplier_id))
    if not recipients:
        return

    invoice_ref = invoice.invoice_number or str(invoice.id)[:8].upper()
    subject = f"Invoice {invoice_ref} Approved"

    body_text = f"""\
Hi,

Good news — Invoice {invoice_ref} has been reviewed and approved.

Payment will be processed according to the contracted terms.

Invoice: {invoice_ref}
Status: Approved

Thank you for your submission.

This is an automated notification from the eBilling platform.
"""

    body_html = f"""\
<html><body style="font-family:Arial,sans-serif;color:#111;max-width:600px">
  <h2 style="color:#16A34A">✓ Invoice {invoice_ref} Approved</h2>
  <p>Invoice <strong>{invoice_ref}</strong> has been reviewed and approved.</p>
  <p>Payment will be processed according to the contracted terms.</p>
  <table style="border-collapse:collapse;width:100%;margin:16px 0">
    <tr><td style="padding:8px;background:#F3F4F6;font-weight:bold">Invoice</td>
        <td style="padding:8px">{invoice_ref}</td></tr>
    <tr><td style="padding:8px;background:#F3F4F6;font-weight:bold">Status</td>
        <td style="padding:8px;color:#16A34A">Approved</td></tr>
  </table>
  <p style="color:#6B7280;font-size:12px">This is an automated notification from the eBilling platform.</p>
</body></html>
"""
    _send(recipients, subject, body_text, body_html)


def notify_invoice_pending_approval(db, invoice) -> None:
    """
    Notify supplier users that their invoice is under carrier review.
    Fires when invoice status transitions to PENDING_CARRIER_REVIEW.
    """
    recipients = _supplier_emails(db, str(invoice.supplier_id))
    if not recipients:
        return

    invoice_ref = invoice.invoice_number or str(invoice.id)[:8].upper()
    subject = f"Invoice {invoice_ref} Under Review"

    body_text = f"""\
Hi,

Invoice {invoice_ref} has passed automated validation and is now pending
carrier approval. No action is required from you at this time.

You will receive a further notification when the invoice is approved.

Invoice: {invoice_ref}
Status: Pending Carrier Approval

This is an automated notification from the eBilling platform.
"""

    body_html = f"""\
<html><body style="font-family:Arial,sans-serif;color:#111;max-width:600px">
  <h2 style="color:#2563EB">Invoice {invoice_ref} — Pending Approval</h2>
  <p>Invoice <strong>{invoice_ref}</strong> has passed automated validation
  and is now pending carrier approval.</p>
  <p>No action is required from you at this time. You will be notified when
  the invoice is approved.</p>
  <table style="border-collapse:collapse;width:100%;margin:16px 0">
    <tr><td style="padding:8px;background:#F3F4F6;font-weight:bold">Invoice</td>
        <td style="padding:8px">{invoice_ref}</td></tr>
    <tr><td style="padding:8px;background:#F3F4F6;font-weight:bold">Status</td>
        <td style="padding:8px;color:#2563EB">Pending Carrier Approval</td></tr>
  </table>
  <p style="color:#6B7280;font-size:12px">This is an automated notification from the eBilling platform.</p>
</body></html>
"""
    _send(recipients, subject, body_text, body_html)


def notify_exception_resolved(
    db, invoice, line_item, exception, resolution_action: str
) -> None:
    """
    Notify supplier users that a specific exception on their invoice has been resolved.
    Fires when a carrier resolves an exception (any resolution action).
    """
    recipients = _supplier_emails(db, str(invoice.supplier_id))
    if not recipients:
        return

    invoice_ref = invoice.invoice_number or str(invoice.id)[:8].upper()
    code = line_item.taxonomy_code or "N/A"

    _RESOLUTION_LABELS = {
        "WAIVED": "Waived — billed amount accepted",
        "ACCEPTED_REDUCTION": "Accepted — amount adjusted to contracted rate",
        "HELD_CONTRACT_RATE": "Contract rate enforced — payment capped at contracted amount",
        "RECLASSIFIED": "Line reclassified — billing accepted under corrected code",
        "DENIED": "Denied — line item rejected",
    }
    resolution_label = _RESOLUTION_LABELS.get(resolution_action, resolution_action)
    is_denied = resolution_action == "DENIED"

    subject = f"Invoice {invoice_ref} — Exception {'Denied' if is_denied else 'Resolved'} ({code})"

    body_text = f"""\
Hi,

An exception on Invoice {invoice_ref} has been {"denied" if is_denied else "resolved"} by the carrier.

Invoice:    {invoice_ref}
Line Item:  {code}
Resolution: {resolution_label}

{"Please log in to the billing portal to review this decision and resubmit if required." if is_denied else "No further action is required for this line item."}

This is an automated notification from the eBilling platform.
"""

    status_color = "#DC2626" if is_denied else "#16A34A"
    body_html = f"""\
<html><body style="font-family:Arial,sans-serif;color:#111;max-width:600px">
  <h2 style="color:{status_color}">
    Invoice {invoice_ref} — Exception {"Denied" if is_denied else "Resolved"}
  </h2>
  <p>An exception on Invoice <strong>{invoice_ref}</strong> has been
  {"denied" if is_denied else "resolved"} by the carrier.</p>
  <table style="border-collapse:collapse;width:100%;margin:16px 0">
    <tr><td style="padding:8px;background:#F3F4F6;font-weight:bold">Invoice</td>
        <td style="padding:8px">{invoice_ref}</td></tr>
    <tr><td style="padding:8px;background:#F3F4F6;font-weight:bold">Line Item</td>
        <td style="padding:8px;font-family:monospace">{code}</td></tr>
    <tr><td style="padding:8px;background:#F3F4F6;font-weight:bold">Resolution</td>
        <td style="padding:8px;color:{status_color}">{resolution_label}</td></tr>
  </table>
  {"<p><strong>Please log in to the billing portal</strong> to review this decision and resubmit if required.</p>" if is_denied else "<p>No further action is required for this line item.</p>"}
  <p style="color:#6B7280;font-size:12px">This is an automated notification from the eBilling platform.</p>
</body></html>
"""
    _send(recipients, subject, body_text, body_html)
