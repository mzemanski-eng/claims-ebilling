"""
Demo seed script — create a realistic Supplier, Contract, Rate Cards,
Guidelines, and a Supplier user for end-to-end testing.

Designed to match the sample fixture: fixtures/sample_invoice_ime.csv

Usage (local or Render Shell):
    python scripts/seed_demo.py

Idempotent — safe to re-run; skips records that already exist.
"""

import os
import sys
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from getpass import getpass

from app.database import SessionLocal
from app.models.supplier import (
    Carrier,
    Contract,
    GeographyScope,
    Guideline,
    RateCard,
    Supplier,
    User,
    UserRole,
)
from app.routers.auth import hash_password

# ── Demo data constants ────────────────────────────────────────────────────────

SUPPLIER_NAME = "Apex IME Services"
SUPPLIER_TAX_ID = "XX-XXXXXXX"  # masked placeholder

CONTRACT_NAME = "Apex IME Services Agreement 2025"
CONTRACT_EFFECTIVE_FROM = date(2025, 1, 1)

# Rate cards keyed by taxonomy_code → (contracted_rate, max_units, is_all_inclusive, notes)
RATE_CARDS = [
    # IME professional fees
    (
        "IME.PHY_EXAM.PROF_FEE",
        Decimal("600.00"),
        Decimal("1"),
        False,
        "Standard single-specialty IME",
    ),
    (
        "IME.MULTI_SPECIALTY.PROF_FEE",
        Decimal("950.00"),
        Decimal("1"),
        False,
        "Multi-specialty panel — 2 physicians max",
    ),
    (
        "IME.ADDENDUM.PROF_FEE",
        Decimal("125.00"),
        Decimal("2"),
        False,
        "Addendum per claim cap: 2",
    ),
    (
        "IME.RECORDS_REVIEW.PROF_FEE",
        Decimal("350.00"),
        Decimal("1"),
        False,
        "Records review without exam",
    ),
    (
        "IME.CANCELLATION.CANCEL_FEE",
        Decimal("150.00"),
        Decimal("1"),
        False,
        "< 48hr cancellation",
    ),
    (
        "IME.NO_SHOW.NO_SHOW_FEE",
        Decimal("100.00"),
        Decimal("1"),
        False,
        "Claimant no-show",
    ),
    (
        "IME.PEER_REVIEW.PROF_FEE",
        Decimal("250.00"),
        Decimal("1"),
        False,
        "Peer review of treatment plan",
    ),
    (
        "IME.ADMIN.SCHEDULING_FEE",
        Decimal("50.00"),
        Decimal("1"),
        False,
        "Admin scheduling coordination",
    ),
    # Travel — billed separately on this contract
    (
        "IME.PHY_EXAM.TRAVEL_TRANSPORT",
        Decimal("400.00"),
        None,
        False,
        "Airfare cap $400",
    ),
    (
        "IME.PHY_EXAM.MILEAGE",
        Decimal("0.67"),
        Decimal("100"),
        False,
        "IRS rate; 100 mile round-trip cap",
    ),
    (
        "IME.PHY_EXAM.TRAVEL_LODGING",
        Decimal("175.00"),
        Decimal("1"),
        False,
        "1 night max per exam",
    ),
    (
        "IME.PHY_EXAM.TRAVEL_MEALS",
        Decimal("60.00"),
        Decimal("1"),
        False,
        "Per diem cap $60/day",
    ),
]

# Guidelines: (rule_type, taxonomy_code_or_None, narrative, rule_params)
GUIDELINES = [
    (
        "max_units",
        "IME.ADDENDUM.PROF_FEE",
        "Maximum 2 addendum reports per claim",
        {"max": 2, "period": "per_claim"},
    ),
    (
        "cap_amount",
        "IME.PHY_EXAM.TRAVEL_TRANSPORT",
        "Airfare reimbursement capped at $400 per exam",
        {"max_amount": 400.00},
    ),
    (
        "max_units",
        "IME.PHY_EXAM.MILEAGE",
        "Mileage reimbursement capped at 100 miles round-trip",
        {"max": 100, "period": "per_exam"},
    ),
    (
        "cap_amount",
        "IME.PHY_EXAM.TRAVEL_MEALS",
        "Meals per diem capped at $60 per travel day",
        {"max_amount": 60.00},
    ),
]


def main() -> None:
    print("\n=== Claims eBilling — Demo Seed ===\n")

    db = SessionLocal()
    try:
        # ── Find carrier (must exist — run bootstrap.py first) ─────────────────
        carrier = db.query(Carrier).first()
        if not carrier:
            print("ERROR: No carrier found. Run bootstrap.py first.")
            sys.exit(1)
        print(f"✓ Using carrier: {carrier.name} ({carrier.short_code})")

        # ── Supplier ───────────────────────────────────────────────────────────
        supplier = db.query(Supplier).filter(Supplier.name == SUPPLIER_NAME).first()
        if supplier:
            print(f"✓ Supplier '{SUPPLIER_NAME}' already exists — skipping.")
        else:
            supplier = Supplier(name=SUPPLIER_NAME, tax_id=SUPPLIER_TAX_ID)
            db.add(supplier)
            db.flush()
            print(f"✓ Supplier '{SUPPLIER_NAME}' created (id={supplier.id})")

        # ── Contract ───────────────────────────────────────────────────────────
        contract = (
            db.query(Contract)
            .filter(
                Contract.supplier_id == supplier.id,
                Contract.carrier_id == carrier.id,
                Contract.effective_from == CONTRACT_EFFECTIVE_FROM,
            )
            .first()
        )
        if contract:
            print(f"✓ Contract '{CONTRACT_NAME}' already exists — skipping rate cards.")
        else:
            contract = Contract(
                supplier_id=supplier.id,
                carrier_id=carrier.id,
                name=CONTRACT_NAME,
                effective_from=CONTRACT_EFFECTIVE_FROM,
                effective_to=None,
                geography_scope=GeographyScope.NATIONAL,
                notes="Demo contract — covers all IME service lines nationally.",
                is_active=True,
            )
            db.add(contract)
            db.flush()
            print(f"✓ Contract '{CONTRACT_NAME}' created (id={contract.id})")

            # ── Rate cards ─────────────────────────────────────────────────────
            for taxonomy_code, rate, max_units, all_inclusive, notes in RATE_CARDS:
                rc = RateCard(
                    contract_id=contract.id,
                    taxonomy_code=taxonomy_code,
                    contracted_rate=rate,
                    max_units=max_units,
                    is_all_inclusive=all_inclusive,
                    effective_from=CONTRACT_EFFECTIVE_FROM,
                    notes=notes,
                )
                db.add(rc)
            print(f"  ✓ {len(RATE_CARDS)} rate cards added")

            # ── Guidelines ─────────────────────────────────────────────────────
            for rule_type, taxonomy_code, narrative, rule_params in GUIDELINES:
                g = Guideline(
                    contract_id=contract.id,
                    taxonomy_code=taxonomy_code,
                    rule_type=rule_type,
                    narrative_source=narrative,
                    rule_params=rule_params,
                    is_active=True,
                )
                db.add(g)
            print(f"  ✓ {len(GUIDELINES)} guidelines added")

        # ── Supplier user ──────────────────────────────────────────────────────
        print("\n── Supplier user (for testing the supplier side) ────────────")
        supplier_email = input("Supplier user email [supplier@apexime.com]: ").strip()
        supplier_email = supplier_email or "supplier@apexime.com"

        existing = db.query(User).filter(User.email == supplier_email).first()
        if existing:
            print(f"✓ User '{supplier_email}' already exists — skipping.")
        else:
            supplier_password = getpass("Supplier password (min 8 chars): ")
            if len(supplier_password) < 8:
                print("ERROR: password must be at least 8 characters.")
                sys.exit(1)
            confirm = getpass("Confirm password: ")
            if supplier_password != confirm:
                print("ERROR: passwords do not match.")
                sys.exit(1)

            user = User(
                email=supplier_email,
                hashed_password=hash_password(supplier_password),
                role=UserRole.SUPPLIER,
                supplier_id=supplier.id,
                is_active=True,
            )
            db.add(user)
            print(f"✓ Supplier user '{supplier_email}' created (role=SUPPLIER)")

        db.commit()

        print("\n✅ Demo seed complete.\n")
        print("Next steps:")
        print("  1. Log in as admin   → POST /auth/token  (your bootstrap email)")
        print(f"  2. Log in as supplier → POST /auth/token  ({supplier_email})")
        print(
            "  3. Upload fixture     → POST /supplier/invoices  then  POST /supplier/invoices/{id}/upload"
        )
        print("  4. Upload file: fixtures/sample_invoice_ime.csv")
        print("  5. Watch the pipeline classify + validate in the admin queue\n")

    except Exception as e:
        db.rollback()
        print(f"\nERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
