#!/usr/bin/env python3
"""
run_demo.py — End-to-end demo script for screen recording.

Walks through the full invoice submission → AI classification → carrier review
→ exception resolution → approval → CSV export workflow against the live API.

Usage:
    python scripts/run_demo.py [--supplier IME|ENG|LA] [--url https://...]

Environment variables (override credentials):
    DEMO_API_URL          Base URL (default: https://claims-ebilling-api.onrender.com)
    DEMO_SUPPLIER_EMAIL   e.g. supplier@apexime.com
    DEMO_SUPPLIER_PASS    supplier password
    DEMO_CARRIER_EMAIL    e.g. carrier_admin@demo.com
    DEMO_CARRIER_PASS     carrier admin password
    DEMO_PAUSE            seconds between steps for readability (default: 1.2)
    DEMO_FAST             set to 1 to skip all pauses (CI mode)
"""

import argparse
import os
import sys
import time
import json
import csv
import io
import datetime
from pathlib import Path
from typing import Optional

# ── Try to import requests; advise if missing ─────────────────────────────────

try:
    import requests
except ImportError:
    print("ERROR: 'requests' is not installed. Run: pip install requests")
    sys.exit(1)

# ── Constants ─────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "fixtures"

SUPPLIER_PROFILES = {
    "IME": {
        "label": "Apex IME Services",
        "fixture": FIXTURES / "sample_invoice_ime.csv",
        "invoice_prefix": "DEMO-IME",
        "email_default": "supplier@apexime.com",
        "narrative": "Independent medical examinations — rate overages and travel caps",
    },
    "ENG": {
        "label": "Pacific Coast Engineering Group",
        "fixture": FIXTURES / "sample_invoice_eng.csv",
        "invoice_prefix": "DEMO-ENG",
        "email_default": "billing@vectoreng.demo",
        "narrative": "Engineering & forensic services — pass-through and billing-increment checks",
    },
    "LA": {
        "label": "Ladder Assist Pro",
        "fixture": FIXTURES / "sample_invoice_la.csv",
        "invoice_prefix": "DEMO-LA",
        "email_default": "billing@peakaccess.demo",
        "narrative": "Ladder assist / roof access — code exclusivity and rate validation",
    },
}

RESOLUTION_LABELS = {
    "APPROVE": "Approved",
    "ACCEPT_REDUCTION": "Accepted carrier reduction",
    "REQUEST_RECLASSIFICATION": "Sent for reclassification",
    "ESTABLISH_CONTRACT_RATE": "Flagged — add to contract",
    "REUPLOAD": "Requested re-upload",
    "ATTACH_DOC": "Requested supporting document",
    "DENY": "Denied",
    "NONE": "No action required",
}

# ── Colours / formatting (ANSI — degrade gracefully on Windows) ───────────────

_TTY = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    if not _TTY:
        return text
    return f"\033[{code}m{text}\033[0m"


def blue(t):   return _c("94", t)
def green(t):  return _c("92", t)
def yellow(t): return _c("93", t)
def red(t):    return _c("91", t)
def bold(t):   return _c("1", t)
def dim(t):    return _c("2", t)
def cyan(t):   return _c("96", t)
def magenta(t): return _c("95", t)


def hr(char="─", width=70):
    print(dim(char * width))


def section(title: str):
    print()
    hr("═")
    print(bold(f"  {title}"))
    hr("═")


def step(msg: str):
    print(f"\n{cyan('▶')} {bold(msg)}")


def ok(msg: str):
    print(f"  {green('✓')} {msg}")


def info(msg: str):
    print(f"  {dim('·')} {msg}")


def warn(msg: str):
    print(f"  {yellow('⚠')} {msg}")


def err(msg: str):
    print(f"  {red('✗')} {msg}", file=sys.stderr)


# ── Config ────────────────────────────────────────────────────────────────────

def get_config(args) -> dict:
    profile = SUPPLIER_PROFILES[args.supplier]
    base_url = (
        args.url
        or os.environ.get("DEMO_API_URL", "https://claims-ebilling-api.onrender.com")
    ).rstrip("/")
    pause = float(os.environ.get("DEMO_PAUSE", "1.2"))
    fast = os.environ.get("DEMO_FAST", "") == "1" or args.fast
    if fast:
        pause = 0.0
    return {
        "base_url": base_url,
        "supplier_email": os.environ.get("DEMO_SUPPLIER_EMAIL", profile["email_default"]),
        "supplier_pass": os.environ.get("DEMO_SUPPLIER_PASS", ""),
        "carrier_email": os.environ.get("DEMO_CARRIER_EMAIL", "carrier_admin@demo.com"),
        "carrier_pass": os.environ.get("DEMO_CARRIER_PASS", ""),
        "pause": pause,
        "profile": profile,
        "supplier_key": args.supplier,
    }


# ── HTTP helpers ──────────────────────────────────────────────────────────────

class APIClient:
    def __init__(self, base_url: str, pause: float):
        self.base_url = base_url
        self.pause = pause
        self.session = requests.Session()
        self.session.headers["Accept"] = "application/json"

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _pause(self):
        if self.pause > 0:
            time.sleep(self.pause)

    def login(self, email: str, password: str) -> str:
        """Exchange credentials for a JWT; set Authorization header. Returns token."""
        resp = self.session.post(
            self._url("/auth/token"),
            data={"username": email, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Login failed for {email}: {resp.status_code} {resp.text[:200]}"
            )
        token = resp.json()["access_token"]
        self.session.headers["Authorization"] = f"Bearer {token}"
        self._pause()
        return token

    def get(self, path: str, params: dict = None) -> dict:
        resp = self.session.get(self._url(path), params=params)
        resp.raise_for_status()
        self._pause()
        return resp.json()

    def post(self, path: str, json_body=None, files=None, data=None) -> dict:
        kwargs = {}
        if json_body is not None:
            kwargs["json"] = json_body
        if files is not None:
            kwargs["files"] = files
        if data is not None:
            kwargs["data"] = data
        resp = self.session.post(self._url(path), **kwargs)
        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"POST {path} → {resp.status_code}: {resp.text[:300]}"
            )
        self._pause()
        return resp.json()

    def patch(self, path: str, json_body: dict) -> dict:
        resp = self.session.patch(self._url(path), json=json_body)
        resp.raise_for_status()
        self._pause()
        return resp.json()

    def get_raw(self, path: str) -> bytes:
        resp = self.session.get(self._url(path))
        resp.raise_for_status()
        self._pause()
        return resp.content


# ── Credential prompts ────────────────────────────────────────────────────────

def _prompt_pass(label: str, env_key: str) -> str:
    val = os.environ.get(env_key, "")
    if val:
        return val
    import getpass
    return getpass.getpass(f"  Enter password for {label}: ")


# ── Demo steps ────────────────────────────────────────────────────────────────

def step_supplier_login(client: APIClient, cfg: dict) -> str:
    step("SUPPLIER LOGIN")
    profile = cfg["profile"]
    email = cfg["supplier_email"]
    info(f"Supplier: {profile['label']}")
    info(f"Email:    {email}")
    password = _prompt_pass(email, "DEMO_SUPPLIER_PASS") if not cfg["supplier_pass"] else cfg["supplier_pass"]
    client.login(email, password)
    me = client.get("/auth/me")
    ok(f"Logged in — role={me['role']}  supplier_id={me.get('supplier_id', 'n/a')}")
    return me.get("supplier_id", "")


def step_get_contract(client: APIClient) -> dict:
    step("FETCH ACTIVE CONTRACT")
    contracts = client.get("/supplier/contracts")
    if not contracts:
        raise RuntimeError("No active contracts found for this supplier. Run seed scripts first.")
    contract = contracts[0]
    ok(f"Contract: {contract['name']}")
    info(f"  id={contract['id']}")
    info(f"  effective_from={contract['effective_from']}")
    info(f"  rate_cards={len(contract.get('rate_cards', []))}  guidelines={len(contract.get('guidelines', []))}")
    return contract


def step_create_invoice(client: APIClient, contract_id: str, prefix: str) -> dict:
    step("CREATE INVOICE RECORD")
    today = datetime.date.today().strftime("%Y-%m-%d")
    ts = datetime.datetime.now().strftime("%H%M%S")
    invoice_number = f"{prefix}-{ts}"
    payload = {
        "contract_id": contract_id,
        "invoice_number": invoice_number,
        "invoice_date": today,
        "submission_notes": "Demo submission — automated end-to-end test",
    }
    invoice = client.post("/supplier/invoices", json_body=payload)
    ok(f"Invoice created: {invoice_number}")
    info(f"  id={invoice['id']}  status={invoice['status']}")
    return invoice


def step_upload_csv(client: APIClient, invoice_id: str, fixture_path: Path) -> dict:
    step("UPLOAD INVOICE CSV")
    if not fixture_path.exists():
        raise RuntimeError(f"Fixture not found: {fixture_path}")
    csv_bytes = fixture_path.read_bytes()
    info(f"File: {fixture_path.name}  ({len(csv_bytes):,} bytes)")
    # Parse row count for display
    rows = list(csv.DictReader(io.StringIO(csv_bytes.decode())))
    info(f"Line items: {len(rows)}")

    files = {"file": (fixture_path.name, csv_bytes, "text/csv")}
    result = client.post(f"/supplier/invoices/{invoice_id}/upload", files=files)
    ok(f"Upload accepted — parse_status={result.get('parse_status', 'processing')}")
    return result


def step_wait_for_pipeline(client: APIClient, invoice_id: str, max_wait: int = 60) -> dict:
    step("WAITING FOR PIPELINE PROCESSING")
    terminal_statuses = {
        "APPROVED", "REVIEW_REQUIRED", "PENDING_CARRIER_REVIEW",
        "REJECTED", "CANCELLED",
    }
    start = time.time()
    dots = 0
    while True:
        elapsed = time.time() - start
        if elapsed > max_wait:
            raise RuntimeError(f"Pipeline did not finish within {max_wait}s. Check worker logs.")

        invoice = client.get(f"/supplier/invoices/{invoice_id}")
        status = invoice["status"]

        if status in terminal_statuses:
            print()  # newline after dots
            ok(f"Pipeline complete — status={bold(status)}  ({elapsed:.1f}s)")
            summary = invoice.get("validation_summary") or {}
            if summary:
                info(f"  Total lines:      {summary.get('total_lines', '?')}")
                info(f"  Lines validated:  {summary.get('lines_validated', '?')}")
                info(f"  With exceptions:  {summary.get('lines_with_exceptions', '?')}")
                info(f"  Total billed:    ${summary.get('total_billed', '?')}")
                info(f"  Total payable:   ${summary.get('total_payable', '?')}")
            return invoice

        # Still processing
        dots = (dots + 1) % 4
        print(f"\r  {dim('·')} Processing{'.' * (dots + 1)}{' ' * (3 - dots)}  [{elapsed:.0f}s]", end="", flush=True)
        time.sleep(1.5)


def step_carrier_login(client: APIClient, cfg: dict) -> dict:
    step("CARRIER ADMIN LOGIN")
    email = cfg["carrier_email"]
    info(f"Email: {email}")
    password = _prompt_pass(email, "DEMO_CARRIER_PASS") if not cfg["carrier_pass"] else cfg["carrier_pass"]
    client.login(email, password)
    me = client.get("/auth/me")
    ok(f"Logged in — role={me['role']}  carrier_id={me.get('carrier_id', 'n/a')}")
    return me


def step_show_invoice_queue(client: APIClient, invoice_id: str) -> dict:
    step("INVOICE REVIEW QUEUE")
    # Show queue summary first
    queue = client.get("/admin/invoices", params={"status": "REVIEW_REQUIRED,PENDING_CARRIER_REVIEW"})
    items = queue if isinstance(queue, list) else queue.get("items", [])
    info(f"Invoices awaiting review: {len(items)}")

    # Fetch our specific invoice with full line detail
    lines = client.get(f"/admin/invoices/{invoice_id}/lines")
    invoice = client.get(f"/admin/invoices/{invoice_id}") if hasattr(client, "_last_invoice") else None

    # Print lines table
    hr()
    print(f"  {'#':<3}  {'Taxonomy Code':<35}  {'Billed':>8}  {'Payable':>8}  {'Status':<18}  Exceptions")
    hr()
    exception_ids = []
    for i, line in enumerate(lines, 1):
        status = line.get("status", "?")
        billed = f"${float(line.get('raw_amount', 0)):,.2f}"
        payable = f"${float(line.get('expected_amount') or 0):,.2f}" if line.get("expected_amount") else dim("  —")
        taxonomy = line.get("taxonomy_code") or dim("<unclassified>")
        exc_list = line.get("exceptions", [])
        exc_summary = ""
        if exc_list:
            types = ", ".join(e.get("required_action", "?") for e in exc_list[:2])
            if len(exc_list) > 2:
                types += f" +{len(exc_list)-2}"
            exc_summary = yellow(f"⚠ {types}")
            exception_ids.extend(e["exception_id"] for e in exc_list)
        status_fmt = (
            green(status) if status in ("VALIDATED", "APPROVED")
            else yellow(status) if status == "REVIEW_REQUIRED"
            else red(status) if status == "DENIED"
            else dim(status)
        )
        print(f"  {i:<3}  {str(taxonomy):<35}  {billed:>8}  {str(payable):>8}  {status_fmt:<28}  {exc_summary}")
    hr()
    ok(f"{len(lines)} lines shown  |  {len(exception_ids)} open exception(s)")
    return {"lines": lines, "exception_ids": exception_ids}


def step_show_exceptions(client: APIClient, lines: list) -> list:
    step("EXCEPTION DETAIL")
    exceptions = []
    for line in lines:
        for exc in line.get("exceptions", []):
            exceptions.append(exc)
            action = exc.get("required_action", "NONE")
            severity = exc.get("severity", "?")
            sev_fmt = red(severity) if severity == "ERROR" else yellow(severity)
            print(f"\n  {bold(line.get('taxonomy_code', '<unclassified>'))}")
            print(f"    Severity:  {sev_fmt}")
            print(f"    Action:    {bold(action)}")
            print(f"    Message:   {exc.get('message', '')}")
            if exc.get("ai_recommendation"):
                ai_rec = exc["ai_recommendation"]
                ai_label = RESOLUTION_LABELS.get(ai_rec, ai_rec)
                print(f"    {magenta('✦ AI suggests:')} {bold(ai_label)}")
                if exc.get("ai_reasoning"):
                    # Word-wrap at 70 chars
                    reasoning = exc["ai_reasoning"]
                    words = reasoning.split()
                    line_buf, lines_out = [], []
                    for w in words:
                        line_buf.append(w)
                        if len(" ".join(line_buf)) > 64:
                            lines_out.append(" ".join(line_buf[:-1]))
                            line_buf = [w]
                    if line_buf:
                        lines_out.append(" ".join(line_buf))
                    for ln in lines_out:
                        print(f"      {dim(ln)}")
    if not exceptions:
        ok("No exceptions found on this invoice.")
    return exceptions


def step_resolve_exceptions(client: APIClient, exceptions: list, auto: bool = True) -> None:
    step("RESOLVE EXCEPTIONS")
    if not exceptions:
        info("Nothing to resolve.")
        return

    for exc in exceptions:
        exc_id = exc["exception_id"]
        action = exc.get("required_action", "NONE")
        ai_rec = exc.get("ai_recommendation")

        # Demo resolution logic:
        # - Use AI recommendation if present
        # - ESTABLISH_CONTRACT_RATE → skip (carrier action needed, not resolution)
        # - ACCEPT_REDUCTION for rate overages
        # - APPROVE for warnings

        if action == "ESTABLISH_CONTRACT_RATE":
            warn(f"Exception {exc_id[:8]}… — {action}: contract rate missing, skipping")
            continue

        resolution_action = ai_rec if ai_rec else (
            "ACCEPT_REDUCTION" if action == "ACCEPT_REDUCTION"
            else "APPROVE"
        )
        notes = (
            "AI-recommended resolution accepted during demo"
            if ai_rec
            else "Auto-resolved in demo workflow"
        )

        try:
            client.post(
                f"/admin/exceptions/{exc_id}/resolve",
                json_body={"resolution_action": resolution_action, "notes": notes},
            )
            label = RESOLUTION_LABELS.get(resolution_action, resolution_action)
            ok(f"Exception {exc_id[:8]}… → {bold(label)}")
        except Exception as e:
            warn(f"Exception {exc_id[:8]}… resolution failed: {e}")


def step_approve_invoice(client: APIClient, invoice_id: str) -> dict:
    step("APPROVE INVOICE")
    result = client.post(f"/admin/invoices/{invoice_id}/approve", json_body={})
    new_status = result.get("status", "?")
    ok(f"Invoice approved — status={bold(new_status)}")
    return result


def step_export_csv(client: APIClient, invoice_id: str, out_dir: Path) -> Optional[Path]:
    step("EXPORT APPROVED LINES TO CSV")
    try:
        raw = client.get_raw(f"/admin/invoices/{invoice_id}/export")
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = out_dir / f"approved_export_{ts}.csv"
        out_path.write_bytes(raw)
        # Count rows
        rows = list(csv.DictReader(io.StringIO(raw.decode(errors="replace"))))
        ok(f"Exported {len(rows)} lines → {out_path}")
        if rows:
            info(f"  Columns: {', '.join(rows[0].keys())}")
        return out_path
    except Exception as e:
        warn(f"Export failed (invoice may still be in review): {e}")
        return None


def step_run_supplier_audit(client: APIClient, supplier_id: str) -> None:
    step("AI SUPPLIER AUDIT REPORT")
    info(f"Running on-demand audit for supplier_id={supplier_id[:8]}…")
    try:
        result = client.post(f"/admin/suppliers/{supplier_id}/audit")
        risk = result.get("risk_rating", "UNKNOWN")
        risk_fmt = (
            red(risk) if risk in ("HIGH", "CRITICAL")
            else yellow(risk) if risk == "MEDIUM"
            else green(risk)
        )
        print(f"\n  Risk Rating: {bold(risk_fmt)}\n")
        for finding in result.get("findings", []):
            print(f"  {yellow('•')} {finding}")
        recs = result.get("recommendations", [])
        if recs:
            print(f"\n  {bold('Recommendations:')}")
            for rec in recs:
                print(f"    {cyan('→')} {rec}")
    except Exception as e:
        warn(f"Audit unavailable (AI key not configured?): {e}")


def step_show_analytics(client: APIClient) -> None:
    step("ANALYTICS SNAPSHOT")
    try:
        summary = client.get("/admin/analytics/summary")
        print(f"\n  {'Metric':<30}  Value")
        hr()
        for key, value in summary.items():
            if isinstance(value, (int, float, str)):
                print(f"  {str(key).replace('_', ' ').title():<30}  {value}")
        hr()
    except Exception as e:
        warn(f"Analytics unavailable: {e}")


# ── Final summary banner ──────────────────────────────────────────────────────

def print_summary(invoice_id: str, invoice_number: str, export_path: Optional[Path]):
    section("DEMO COMPLETE ✅")
    print(f"  Invoice Number:  {bold(invoice_number)}")
    print(f"  Invoice ID:      {dim(invoice_id)}")
    if export_path:
        print(f"  Export:          {export_path}")
    print()
    print(dim("  Full workflow demonstrated:"))
    steps = [
        "Supplier login + contract fetch",
        "Invoice creation + CSV upload",
        "AI classification pipeline (taxonomy mapping, rate validation, guideline checks)",
        "Carrier admin review queue",
        "Exception inspection (with AI recommendations)",
        "Exception resolution",
        "Invoice approval",
        "CSV export of approved lines",
        "On-demand supplier audit",
        "Analytics snapshot",
    ]
    for s in steps:
        print(f"    {green('✓')} {s}")
    print()
    hr()
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Run a full end-to-end demo of the claims eBilling platform.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--supplier", choices=["IME", "ENG", "LA"], default="IME",
        help="Which supplier profile to demo (default: IME)",
    )
    parser.add_argument(
        "--url", default=None,
        help="API base URL (overrides DEMO_API_URL env var)",
    )
    parser.add_argument(
        "--fast", action="store_true",
        help="Skip inter-step pauses (CI mode)",
    )
    parser.add_argument(
        "--skip-audit", action="store_true",
        help="Skip the on-demand supplier audit step",
    )
    parser.add_argument(
        "--skip-analytics", action="store_true",
        help="Skip the analytics snapshot step",
    )
    parser.add_argument(
        "--export-dir", default="demo_exports",
        help="Directory to write the approved-lines CSV export (default: demo_exports/)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    cfg = get_config(args)
    profile = cfg["profile"]

    # ── Intro banner ──────────────────────────────────────────────────────────
    section(f"CLAIMS eBILLING — END-TO-END DEMO  ({args.supplier})")
    print(f"  Supplier profile: {bold(profile['label'])}")
    print(f"  Scenario:         {dim(profile['narrative'])}")
    print(f"  API:              {cfg['base_url']}")
    print(f"  Fixture:          {profile['fixture'].name}")
    print()

    client = APIClient(cfg["base_url"], cfg["pause"])
    export_dir = Path(args.export_dir)

    # ── Supplier workflow ─────────────────────────────────────────────────────
    try:
        supplier_id = step_supplier_login(client, cfg)
        contract    = step_get_contract(client)
        invoice     = step_create_invoice(client, contract["id"], profile["invoice_prefix"])
        invoice_id  = invoice["id"]
        invoice_num = invoice["invoice_number"]

        step_upload_csv(client, invoice_id, profile["fixture"])
        invoice     = step_wait_for_pipeline(client, invoice_id)

    except RuntimeError as e:
        err(str(e))
        sys.exit(1)
    except requests.exceptions.ConnectionError as e:
        err(f"Cannot reach API at {cfg['base_url']}: {e}")
        sys.exit(1)

    # ── Carrier admin workflow ────────────────────────────────────────────────
    try:
        step_carrier_login(client, cfg)
        result      = step_show_invoice_queue(client, invoice_id)
        lines       = result["lines"]

        exceptions  = step_show_exceptions(client, lines)
        step_resolve_exceptions(client, exceptions)

        # Re-fetch and check whether all errors are resolved before approving
        updated_lines = client.get(f"/admin/invoices/{invoice_id}/lines")
        open_errors = [
            e for ln in updated_lines
            for e in ln.get("exceptions", [])
            if e.get("severity") == "ERROR" and not e.get("resolution_action")
        ]
        if open_errors:
            warn(f"{len(open_errors)} unresolved ERROR exception(s) remain — invoice may land in REVIEW_REQUIRED")

        step_approve_invoice(client, invoice_id)
        export_path = step_export_csv(client, invoice_id, export_dir)

        if not args.skip_audit and supplier_id:
            step_run_supplier_audit(client, supplier_id)

        if not args.skip_analytics:
            step_show_analytics(client)

    except RuntimeError as e:
        err(str(e))
        sys.exit(1)
    except requests.exceptions.ConnectionError as e:
        err(f"API connection lost: {e}")
        sys.exit(1)

    print_summary(invoice_id, invoice_num, export_path if not args.skip_audit else None)


if __name__ == "__main__":
    main()
