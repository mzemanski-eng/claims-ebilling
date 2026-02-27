"""
Integration tests for the /carrier router.

Covers:
  - Carrier-scoped data isolation (carriers only see their own invoices)
  - Role guards (CARRIER_REVIEWER cannot call write endpoints)
  - Invoice lifecycle: request-changes, approve, export
  - Exception resolution with typed actions
  - Edge cases: wrong carrier, already-resolved exceptions, wrong invoice status

Requires DB — run with a live Postgres instance (provided by CI or docker-compose).
"""

import pytest
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.models.invoice import Invoice, LineItem, LineItemStatus, SubmissionStatus
from app.models.validation import (
    ExceptionRecord,
    ExceptionStatus,
    ValidationResult,
    ValidationType,
    ValidationStatus,
    ValidationSeverity,
    RequiredAction,
    ResolutionAction,
)
from app.routers.auth import create_access_token


pytestmark = pytest.mark.usefixtures("db")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _auth_header(user) -> dict:
    """Build Authorization header with a fresh JWT for the given user."""
    token = create_access_token(
        {
            "sub": user.email,
            "user_id": str(user.id),
            "role": user.role,
            "supplier_id": str(user.supplier_id) if user.supplier_id else None,
            "carrier_id": str(user.carrier_id) if user.carrier_id else None,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def _make_pending_invoice(db, supplier, contract, invoice_number="INV-CAR-001"):
    """Create an invoice in PENDING_CARRIER_REVIEW with one line item."""
    invoice = Invoice(
        supplier_id=supplier.id,
        contract_id=contract.id,
        invoice_number=invoice_number,
        invoice_date=date(2025, 2, 15),
        status=SubmissionStatus.PENDING_CARRIER_REVIEW,
        current_version=1,
    )
    db.add(invoice)
    db.flush()

    li = LineItem(
        invoice_id=invoice.id,
        invoice_version=1,
        line_number=1,
        raw_description="IME Physician Examination - Orthopedic",
        raw_amount=Decimal("600.00"),
        raw_quantity=Decimal("1"),
        raw_unit="report",
        claim_number="CLM-CAR-001",
        service_date=date(2025, 2, 15),
        taxonomy_code="IME.PHY_EXAM.PROF_FEE",
        billing_component="PROF_FEE",
        mapping_confidence="HIGH",
        status=LineItemStatus.VALIDATED,
    )
    db.add(li)
    db.flush()
    return invoice, li


def _add_open_exception(db, line_item):
    """Add an OPEN exception to a line item (rate validation failure)."""
    vr = ValidationResult(
        line_item_id=line_item.id,
        validation_type=ValidationType.RATE,
        status=ValidationStatus.FAIL,
        severity=ValidationSeverity.ERROR,
        message="Billed amount exceeds contracted rate.",
        required_action=RequiredAction.ACCEPT_REDUCTION,
    )
    db.add(vr)
    db.flush()

    exc = ExceptionRecord(
        line_item_id=line_item.id,
        validation_result_id=vr.id,
        status=ExceptionStatus.OPEN,
    )
    db.add(exc)
    db.flush()
    return exc


# ── Carrier scoping ───────────────────────────────────────────────────────────


class TestCarrierScoping:
    def test_list_invoices_scoped_to_carrier(
        self,
        client: TestClient,
        db,
        sample_supplier,
        sample_contract,
        carrier_admin_user,
    ):
        """Carrier only sees invoices under their own contracts."""
        # Invoice belonging to sample_carrier (via sample_contract)
        inv, _ = _make_pending_invoice(db, sample_supplier, sample_contract)

        # A second carrier + contract + invoice that should NOT appear
        from app.models.supplier import Carrier, Contract

        other_carrier = Carrier(name="Other Carrier", short_code="OTH")
        db.add(other_carrier)
        db.flush()

        other_contract = Contract(
            supplier_id=sample_supplier.id,
            carrier_id=other_carrier.id,
            name="Other Contract",
            effective_from=date(2025, 1, 1),
            geography_scope="national",
        )
        db.add(other_contract)
        db.flush()

        other_inv, _ = _make_pending_invoice(
            db, sample_supplier, other_contract, "INV-OTHER-001"
        )

        resp = client.get(
            "/carrier/invoices",
            headers=_auth_header(carrier_admin_user),
        )
        assert resp.status_code == 200
        ids = [i["id"] for i in resp.json()]
        assert str(inv.id) in ids
        assert str(other_inv.id) not in ids

    def test_get_invoice_wrong_carrier_returns_403(
        self, client: TestClient, db, sample_supplier, carrier_admin_user
    ):
        """A carrier cannot fetch an invoice belonging to a different carrier."""
        from app.models.supplier import Carrier, Contract

        other_carrier = Carrier(name="Outsider Carrier", short_code="OSC")
        db.add(other_carrier)
        db.flush()

        other_contract = Contract(
            supplier_id=sample_supplier.id,
            carrier_id=other_carrier.id,
            name="Outsider Contract",
            effective_from=date(2025, 1, 1),
            geography_scope="national",
        )
        db.add(other_contract)
        db.flush()

        other_inv, _ = _make_pending_invoice(
            db, sample_supplier, other_contract, "INV-OUTSIDER-001"
        )

        resp = client.get(
            f"/carrier/invoices/{other_inv.id}",
            headers=_auth_header(carrier_admin_user),
        )
        assert resp.status_code == 403


# ── Role guards ───────────────────────────────────────────────────────────────


class TestCarrierRoleGuards:
    def test_reviewer_cannot_approve(
        self,
        client: TestClient,
        db,
        sample_supplier,
        sample_contract,
        carrier_reviewer_user,
    ):
        """CARRIER_REVIEWER must get 403 on the approve endpoint."""
        inv, _ = _make_pending_invoice(
            db, sample_supplier, sample_contract, "INV-RREV-001"
        )
        resp = client.post(
            f"/carrier/invoices/{inv.id}/approve",
            json={"notes": "Approved"},
            headers=_auth_header(carrier_reviewer_user),
        )
        assert resp.status_code == 403

    def test_reviewer_cannot_request_changes(
        self,
        client: TestClient,
        db,
        sample_supplier,
        sample_contract,
        carrier_reviewer_user,
    ):
        """CARRIER_REVIEWER must get 403 on the request-changes endpoint."""
        inv, _ = _make_pending_invoice(
            db, sample_supplier, sample_contract, "INV-RREV-002"
        )
        resp = client.post(
            f"/carrier/invoices/{inv.id}/request-changes",
            json={"carrier_notes": "Please fix line 1"},
            headers=_auth_header(carrier_reviewer_user),
        )
        assert resp.status_code == 403

    def test_reviewer_can_read_invoices(
        self,
        client: TestClient,
        db,
        sample_supplier,
        sample_contract,
        carrier_reviewer_user,
    ):
        """CARRIER_REVIEWER can access read endpoints."""
        _make_pending_invoice(db, sample_supplier, sample_contract, "INV-RREV-003")
        resp = client.get(
            "/carrier/invoices",
            headers=_auth_header(carrier_reviewer_user),
        )
        assert resp.status_code == 200


# ── Request Changes ───────────────────────────────────────────────────────────


class TestRequestChanges:
    def test_request_changes_transitions_to_review_required(
        self,
        client: TestClient,
        db,
        sample_supplier,
        sample_contract,
        carrier_admin_user,
    ):
        """request-changes transitions PENDING_CARRIER_REVIEW → REVIEW_REQUIRED."""
        inv, _ = _make_pending_invoice(
            db, sample_supplier, sample_contract, "INV-RC-001"
        )

        resp = client.post(
            f"/carrier/invoices/{inv.id}/request-changes",
            json={"carrier_notes": "Line 1 amount is incorrect, please resubmit."},
            headers=_auth_header(carrier_admin_user),
        )
        assert resp.status_code == 200

        db.refresh(inv)
        assert inv.status == SubmissionStatus.REVIEW_REQUIRED

    def test_request_changes_returns_notes_in_response(
        self,
        client: TestClient,
        db,
        sample_supplier,
        sample_contract,
        carrier_admin_user,
    ):
        """The response body should echo the carrier notes."""
        inv, _ = _make_pending_invoice(
            db, sample_supplier, sample_contract, "INV-RC-002"
        )
        notes = "Please correct the neurology exam rate."

        resp = client.post(
            f"/carrier/invoices/{inv.id}/request-changes",
            json={"carrier_notes": notes},
            headers=_auth_header(carrier_admin_user),
        )
        assert resp.status_code == 200
        assert resp.json()["carrier_notes"] == notes

    def test_request_changes_invalid_status_returns_409(
        self,
        client: TestClient,
        db,
        sample_supplier,
        sample_contract,
        carrier_admin_user,
    ):
        """request-changes on a non-PENDING_CARRIER_REVIEW invoice returns 409."""
        inv, _ = _make_pending_invoice(
            db, sample_supplier, sample_contract, "INV-RC-003"
        )
        inv.status = SubmissionStatus.APPROVED
        db.flush()

        resp = client.post(
            f"/carrier/invoices/{inv.id}/request-changes",
            json={"carrier_notes": "Too late."},
            headers=_auth_header(carrier_admin_user),
        )
        assert resp.status_code == 409


# ── Approve Invoice ───────────────────────────────────────────────────────────


class TestApproveInvoice:
    def test_approve_transitions_invoice_to_approved(
        self,
        client: TestClient,
        db,
        sample_supplier,
        sample_contract,
        carrier_admin_user,
    ):
        """approve sets invoice status to APPROVED."""
        inv, _ = _make_pending_invoice(
            db, sample_supplier, sample_contract, "INV-APP-001"
        )

        resp = client.post(
            f"/carrier/invoices/{inv.id}/approve",
            json={"notes": None},
            headers=_auth_header(carrier_admin_user),
        )
        assert resp.status_code == 200

        db.refresh(inv)
        assert inv.status == SubmissionStatus.APPROVED

    def test_approve_waives_open_exceptions(
        self,
        client: TestClient,
        db,
        sample_supplier,
        sample_contract,
        carrier_admin_user,
    ):
        """approve force-waives all OPEN exceptions before approving."""
        inv, li = _make_pending_invoice(
            db, sample_supplier, sample_contract, "INV-APP-002"
        )
        li.status = LineItemStatus.EXCEPTION
        exc = _add_open_exception(db, li)
        db.flush()

        resp = client.post(
            f"/carrier/invoices/{inv.id}/approve",
            json={"notes": "Approving with waiver"},
            headers=_auth_header(carrier_admin_user),
        )
        assert resp.status_code == 200

        db.refresh(exc)
        assert exc.status == ExceptionStatus.WAIVED
        assert exc.resolution_action == ResolutionAction.WAIVED

        db.refresh(li)
        assert li.status == LineItemStatus.APPROVED

    def test_approve_wrong_status_returns_409(
        self,
        client: TestClient,
        db,
        sample_supplier,
        sample_contract,
        carrier_admin_user,
    ):
        """approve on a DRAFT invoice returns 409."""
        inv, _ = _make_pending_invoice(
            db, sample_supplier, sample_contract, "INV-APP-003"
        )
        inv.status = SubmissionStatus.DRAFT
        db.flush()

        resp = client.post(
            f"/carrier/invoices/{inv.id}/approve",
            json={},
            headers=_auth_header(carrier_admin_user),
        )
        assert resp.status_code == 409


# ── Resolve Exception ─────────────────────────────────────────────────────────


class TestResolveException:
    def test_resolve_exception_sets_resolved_status(
        self,
        client: TestClient,
        db,
        sample_supplier,
        sample_contract,
        carrier_admin_user,
    ):
        """Resolving with HELD_CONTRACT_RATE sets status to RESOLVED."""
        _, li = _make_pending_invoice(
            db, sample_supplier, sample_contract, "INV-EXC-001"
        )
        exc = _add_open_exception(db, li)

        resp = client.post(
            f"/carrier/exceptions/{exc.id}/resolve",
            json={
                "resolution_action": "HELD_CONTRACT_RATE",
                "resolution_notes": "Payment limited to contracted rate of $600.",
            },
            headers=_auth_header(carrier_admin_user),
        )
        assert resp.status_code == 200

        db.refresh(exc)
        assert exc.status == ExceptionStatus.RESOLVED
        assert exc.resolution_action == ResolutionAction.HELD_CONTRACT_RATE

    def test_resolve_waived_action_sets_waived_status(
        self,
        client: TestClient,
        db,
        sample_supplier,
        sample_contract,
        carrier_admin_user,
    ):
        """Resolving with WAIVED action sets status to WAIVED (not RESOLVED)."""
        _, li = _make_pending_invoice(
            db, sample_supplier, sample_contract, "INV-EXC-002"
        )
        exc = _add_open_exception(db, li)

        resp = client.post(
            f"/carrier/exceptions/{exc.id}/resolve",
            json={
                "resolution_action": "WAIVED",
                "resolution_notes": "One-time waiver.",
            },
            headers=_auth_header(carrier_admin_user),
        )
        assert resp.status_code == 200

        db.refresh(exc)
        assert exc.status == ExceptionStatus.WAIVED

    def test_resolve_exception_wrong_carrier_returns_403(
        self,
        client: TestClient,
        db,
        sample_supplier,
        carrier_admin_user,
    ):
        """Carrier cannot resolve an exception on another carrier's invoice."""
        from app.models.supplier import Carrier, Contract

        other_carrier = Carrier(name="Other Carrier 2", short_code="OT2")
        db.add(other_carrier)
        db.flush()

        other_contract = Contract(
            supplier_id=sample_supplier.id,
            carrier_id=other_carrier.id,
            name="Other Contract 2",
            effective_from=date(2025, 1, 1),
            geography_scope="national",
        )
        db.add(other_contract)
        db.flush()

        other_inv, other_li = _make_pending_invoice(
            db, sample_supplier, other_contract, "INV-EXC-003"
        )
        exc = _add_open_exception(db, other_li)

        resp = client.post(
            f"/carrier/exceptions/{exc.id}/resolve",
            json={"resolution_action": "WAIVED"},
            headers=_auth_header(carrier_admin_user),
        )
        assert resp.status_code == 403


# ── Export ────────────────────────────────────────────────────────────────────


class TestExportInvoice:
    def test_export_sets_exported_status(
        self,
        client: TestClient,
        db,
        sample_supplier,
        sample_contract,
        carrier_admin_user,
    ):
        """Exporting an APPROVED invoice transitions it to EXPORTED."""
        inv, li = _make_pending_invoice(
            db, sample_supplier, sample_contract, "INV-EXP-001"
        )
        inv.status = SubmissionStatus.APPROVED
        li.status = LineItemStatus.APPROVED
        db.flush()

        resp = client.get(
            f"/carrier/invoices/{inv.id}/export",
            headers=_auth_header(carrier_admin_user),
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

        db.refresh(inv)
        assert inv.status == SubmissionStatus.EXPORTED

    def test_export_requires_approved_status(
        self,
        client: TestClient,
        db,
        sample_supplier,
        sample_contract,
        carrier_admin_user,
    ):
        """Exporting a non-APPROVED invoice returns 409."""
        inv, _ = _make_pending_invoice(
            db, sample_supplier, sample_contract, "INV-EXP-002"
        )
        # Status is PENDING_CARRIER_REVIEW — not yet approved

        resp = client.get(
            f"/carrier/invoices/{inv.id}/export",
            headers=_auth_header(carrier_admin_user),
        )
        assert resp.status_code == 409


# ── Deny Exception ────────────────────────────────────────────────────────────


class TestDenyException:
    def test_deny_exception_sets_line_item_denied(
        self,
        client: TestClient,
        db,
        sample_supplier,
        sample_contract,
        carrier_admin_user,
    ):
        """DENIED resolution sets exception→RESOLVED and line item→DENIED."""
        _, li = _make_pending_invoice(
            db, sample_supplier, sample_contract, "INV-DEN-001"
        )
        li.status = LineItemStatus.EXCEPTION
        exc = _add_open_exception(db, li)

        resp = client.post(
            f"/carrier/exceptions/{exc.id}/resolve",
            json={
                "resolution_action": "DENIED",
                "resolution_notes": "Service not covered under this contract.",
            },
            headers=_auth_header(carrier_admin_user),
        )
        assert resp.status_code == 200

        db.refresh(exc)
        assert exc.status == ExceptionStatus.RESOLVED
        assert exc.resolution_action == ResolutionAction.DENIED

        db.refresh(li)
        assert li.status == LineItemStatus.DENIED

    def test_approve_invoice_skips_denied_lines(
        self,
        client: TestClient,
        db,
        sample_supplier,
        sample_contract,
        carrier_admin_user,
    ):
        """Approval leaves DENIED lines untouched; only VALIDATED line → APPROVED."""
        inv, li_validated = _make_pending_invoice(
            db, sample_supplier, sample_contract, "INV-DEN-002"
        )
        # Second line — will be DENIED
        li_denied = LineItem(
            invoice_id=inv.id,
            invoice_version=1,
            line_number=2,
            raw_description="Non-covered service",
            raw_amount=Decimal("200.00"),
            raw_quantity=Decimal("1"),
            raw_unit="report",
            claim_number="CLM-DEN-002",
            service_date=date(2025, 2, 15),
            taxonomy_code="IME.PHY_EXAM.PROF_FEE",
            billing_component="PROF_FEE",
            mapping_confidence="HIGH",
            status=LineItemStatus.EXCEPTION,
        )
        db.add(li_denied)
        db.flush()

        exc = _add_open_exception(db, li_denied)

        # Resolve the exception as DENIED → li_denied.status = DENIED
        client.post(
            f"/carrier/exceptions/{exc.id}/resolve",
            json={"resolution_action": "DENIED", "resolution_notes": "Not covered."},
            headers=_auth_header(carrier_admin_user),
        )

        # Now approve the invoice
        resp = client.post(
            f"/carrier/invoices/{inv.id}/approve",
            json={"notes": None},
            headers=_auth_header(carrier_admin_user),
        )
        assert resp.status_code == 200

        db.refresh(inv)
        assert inv.status == SubmissionStatus.APPROVED

        db.refresh(li_validated)
        assert li_validated.status == LineItemStatus.APPROVED  # normal line approved

        db.refresh(li_denied)
        assert li_denied.status == LineItemStatus.DENIED  # denied line untouched

    def test_deny_already_resolved_exception_returns_409(
        self,
        client: TestClient,
        db,
        sample_supplier,
        sample_contract,
        carrier_admin_user,
    ):
        """Resolving an already-RESOLVED exception returns 409 CONFLICT."""
        _, li = _make_pending_invoice(
            db, sample_supplier, sample_contract, "INV-DEN-003"
        )
        li.status = LineItemStatus.EXCEPTION
        exc = _add_open_exception(db, li)

        # First resolution — succeeds
        client.post(
            f"/carrier/exceptions/{exc.id}/resolve",
            json={"resolution_action": "DENIED"},
            headers=_auth_header(carrier_admin_user),
        )

        # Second resolution attempt — should fail with 409
        resp = client.post(
            f"/carrier/exceptions/{exc.id}/resolve",
            json={"resolution_action": "WAIVED"},
            headers=_auth_header(carrier_admin_user),
        )
        assert resp.status_code == 409
