"""
Seed script — ENG (Engineering & Forensic) and LA (Ladder Assist) suppliers.

Creates two suppliers with realistic contracts, rate cards, and guidelines.
Designed to match the sample fixtures:
  fixtures/sample_invoice_eng.csv
  fixtures/sample_invoice_la.csv

Usage (local or Render Shell):
    python scripts/seed_eng_la.py

Idempotent — safe to re-run; skips records that already exist.

Users are optional: if users already exist in the DB the script won't error.
Pass --skip-users to bypass the interactive prompts entirely (useful for CI).
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

# ── CLI flag ───────────────────────────────────────────────────────────────────

SKIP_USERS = "--skip-users" in sys.argv

# ── Contract constants ─────────────────────────────────────────────────────────

CONTRACT_EFFECTIVE_FROM = date(2025, 1, 1)

# ══════════════════════════════════════════════════════════════════════════════
# ENG — Pacific Coast Engineering Group
# ══════════════════════════════════════════════════════════════════════════════

ENG_SUPPLIER_NAME = "Pacific Coast Engineering Group"
ENG_SUPPLIER_TAX_ID = "XX-ENG0001"  # masked placeholder
ENG_CONTRACT_NAME = "Pacific Coast Engineering Group Services Agreement 2025"

# (taxonomy_code, contracted_rate, max_units, is_all_inclusive, notes)
ENG_RATE_CARDS = [
    # ── Fire Origin and Cause (FOC) ────────────────────────────────────────
    ("ENG.FOC.L1", Decimal("275.00"), None, False, "Principal Engineer — per hour"),
    ("ENG.FOC.L2", Decimal("225.00"), None, False, "Senior Engineer — per hour"),
    ("ENG.FOC.L3", Decimal("175.00"), None, False, "Staff Engineer — per hour"),
    # ── Damage Assessment (DA) ─────────────────────────────────────────────
    ("ENG.DA.L1", Decimal("275.00"), None, False, "Principal Engineer — per hour"),
    ("ENG.DA.L2", Decimal("225.00"), None, False, "Senior Engineer — per hour"),
    ("ENG.DA.L3", Decimal("175.00"), None, False, "Staff Engineer — per hour"),
    ("ENG.DA.L4", Decimal("135.00"), None, False, "Associate Engineer — per hour"),
    # ── Engineering Cause and Origin (CAO) ────────────────────────────────
    ("ENG.CAO.L1", Decimal("275.00"), None, False, "Principal Engineer — per hour"),
    ("ENG.CAO.L2", Decimal("225.00"), None, False, "Senior Engineer — per hour"),
    ("ENG.CAO.L3", Decimal("175.00"), None, False, "Staff Engineer — per hour"),
    # ── Engineering Analysis (EA) ─────────────────────────────────────────
    ("ENG.EA.L1", Decimal("275.00"), None, False, "Principal Engineer — per hour"),
    ("ENG.EA.L2", Decimal("225.00"), None, False, "Senior Engineer — per hour"),
    ("ENG.EA.L3", Decimal("175.00"), None, False, "Staff Engineer — per hour"),
    # ── Expert Witness / Deposition (EWD) ─────────────────────────────────
    (
        "ENG.EWD.L1",
        Decimal("275.00"),
        Decimal("8"),
        False,
        "Principal Engineer — 8hr max per claim",
    ),
    (
        "ENG.EWD.L2",
        Decimal("225.00"),
        Decimal("8"),
        False,
        "Senior Engineer — 8hr max per claim",
    ),
    # ── Peer Review (PR) ──────────────────────────────────────────────────
    ("ENG.PR.L1", Decimal("275.00"), None, False, "Principal Engineer — per hour"),
    ("ENG.PR.L2", Decimal("225.00"), None, False, "Senior Engineer — per hour"),
    ("ENG.PR.L3", Decimal("175.00"), None, False, "Staff Engineer — per hour"),
    # ── Reporting (RPT) ───────────────────────────────────────────────────
    ("ENG.RPT.L2", Decimal("225.00"), None, False, "Senior Engineer — per hour"),
    ("ENG.RPT.L3", Decimal("175.00"), None, False, "Staff Engineer — per hour"),
    ("ENG.RPT.L4", Decimal("135.00"), None, False, "Associate Engineer — per hour"),
    # ── Project Management (PM) ───────────────────────────────────────────
    ("ENG.PM.L2", Decimal("225.00"), None, False, "Senior Engineer — per hour"),
    ("ENG.PM.L3", Decimal("175.00"), None, False, "Staff Engineer — per hour"),
    ("ENG.PM.L4", Decimal("135.00"), None, False, "Associate Engineer — per hour"),
    # ── Admin and Office Support (AOS) ────────────────────────────────────
    ("ENG.AOS.L5", Decimal("95.00"), None, False, "Junior Technician — per hour"),
    ("ENG.AOS.L6", Decimal("65.00"), None, False, "Admin/Support Staff — per hour"),
]

# (rule_type, taxonomy_code, narrative, rule_params)
ENG_GUIDELINES = [
    (
        "max_units",
        "ENG.EWD.L1",
        "Expert witness and deposition hours capped at 8 hours per claim for Principal Engineer",
        {"max": 8, "period": "per_claim"},
    ),
    (
        "max_units",
        "ENG.EWD.L2",
        "Expert witness and deposition hours capped at 8 hours per claim for Senior Engineer",
        {"max": 8, "period": "per_claim"},
    ),
    (
        "max_units",
        "ENG.AOS.L6",
        "Administrative support capped at 10 hours per invoice",
        {"max": 10, "period": "per_invoice"},
    ),
]

# ══════════════════════════════════════════════════════════════════════════════
# LA — Summit Ladder Assist Inc.
# ══════════════════════════════════════════════════════════════════════════════

LA_SUPPLIER_NAME = "Summit Ladder Assist Inc."
LA_SUPPLIER_TAX_ID = "XX-LA00001"  # masked placeholder
LA_CONTRACT_NAME = "Summit Ladder Assist Services Agreement 2025"

LA_RATE_CARDS = [
    (
        "LA.LADDER_ACCESS.FLAT_FEE",
        Decimal("125.00"),
        Decimal("1"),
        False,
        "Per-occurrence ladder placement",
    ),
    (
        "LA.ROOF_INSPECT.FLAT_FEE",
        Decimal("175.00"),
        Decimal("1"),
        False,
        "Per-occurrence standard roof inspection",
    ),
    (
        "LA.ROOF_INSPECT_HARNESS.FLAT_FEE",
        Decimal("225.00"),
        Decimal("1"),
        False,
        "Per-occurrence harness-required inspection",
    ),
    (
        "LA.TARP_COVER.FLAT_FEE",
        Decimal("350.00"),
        Decimal("1"),
        False,
        "Per-occurrence emergency tarp application",
    ),
    (
        "LA.CANCEL.CANCEL_FEE",
        Decimal("75.00"),
        Decimal("1"),
        False,
        "< 24hr cancellation notice",
    ),
    (
        "LA.TRIP_CHARGE.TRIP_FEE",
        Decimal("65.00"),
        Decimal("1"),
        False,
        "Site arrival, unable to complete service",
    ),
]

LA_GUIDELINES = [
    (
        "max_units",
        "LA.LADDER_ACCESS.FLAT_FEE",
        "Maximum 2 ladder access charges per claim per visit date",
        {"max": 2, "period": "per_day"},
    ),
    (
        "max_units",
        "LA.TARP_COVER.FLAT_FEE",
        "Maximum 1 tarp application per claim unless prior approval obtained",
        {"max": 1, "period": "per_claim"},
    ),
    (
        "max_units",
        "LA.CANCEL.CANCEL_FEE",
        "Maximum 1 cancellation fee per claim",
        {"max": 1, "period": "per_claim"},
    ),
]


# ── Helpers ────────────────────────────────────────────────────────────────────


def _seed_supplier(
    db, carrier, supplier_name, tax_id, contract_name, rate_cards, guidelines, notes
):
    """Create (or skip) one supplier + contract + rate cards + guidelines."""
    supplier = db.query(Supplier).filter(Supplier.name == supplier_name).first()
    if supplier:
        print(f"  ✓ Supplier '{supplier_name}' already exists — skipping.")
    else:
        supplier = Supplier(name=supplier_name, tax_id=tax_id)
        db.add(supplier)
        db.flush()
        print(f"  ✓ Supplier '{supplier_name}' created (id={supplier.id})")

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
        print(f"  ✓ Contract '{contract_name}' already exists — skipping rate cards.")
    else:
        contract = Contract(
            supplier_id=supplier.id,
            carrier_id=carrier.id,
            name=contract_name,
            effective_from=CONTRACT_EFFECTIVE_FROM,
            effective_to=None,
            geography_scope=GeographyScope.NATIONAL,
            notes=notes,
            is_active=True,
        )
        db.add(contract)
        db.flush()
        print(f"  ✓ Contract '{contract_name}' created (id={contract.id})")

        for taxonomy_code, rate, max_units, all_inclusive, rc_notes in rate_cards:
            rc = RateCard(
                contract_id=contract.id,
                taxonomy_code=taxonomy_code,
                contracted_rate=rate,
                max_units=max_units,
                is_all_inclusive=all_inclusive,
                effective_from=CONTRACT_EFFECTIVE_FROM,
                notes=rc_notes,
            )
            db.add(rc)
        print(f"    ✓ {len(rate_cards)} rate cards added")

        for rule_type, taxonomy_code, narrative, rule_params in guidelines:
            g = Guideline(
                contract_id=contract.id,
                taxonomy_code=taxonomy_code,
                rule_type=rule_type,
                narrative_source=narrative,
                rule_params=rule_params,
                is_active=True,
            )
            db.add(g)
        print(f"    ✓ {len(guidelines)} guidelines added")

    return supplier


def _prompt_user(db, supplier, role, default_email, role_label):
    """Interactively create a supplier user if it doesn't exist."""
    print(f"\n── {role_label} ──────────────────────────────────────────────")
    email = input(f"Email [{default_email}]: ").strip() or default_email

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        print(f"  ✓ User '{email}' already exists — skipping.")
        return

    password = getpass("Password (min 8 chars): ")
    if len(password) < 8:
        print("ERROR: password must be at least 8 characters.")
        sys.exit(1)
    confirm = getpass("Confirm password: ")
    if password != confirm:
        print("ERROR: passwords do not match.")
        sys.exit(1)

    kwargs = {
        "email": email,
        "hashed_password": hash_password(password),
        "role": role,
        "is_active": True,
    }
    if role == UserRole.SUPPLIER:
        kwargs["supplier_id"] = supplier.id
    user = User(**kwargs)
    db.add(user)
    print(f"  ✓ User '{email}' created (role={role})")


# ── Main ───────────────────────────────────────────────────────────────────────


def main() -> None:
    print("\n=== Claims eBilling — ENG & LA Seed ===\n")

    db = SessionLocal()
    try:
        carrier = db.query(Carrier).first()
        if not carrier:
            print("ERROR: No carrier found. Run bootstrap.py first.")
            sys.exit(1)
        print(f"✓ Using carrier: {carrier.name} ({carrier.short_code})\n")

        # ── ENG supplier ───────────────────────────────────────────────────────
        print("── Engineering supplier ──────────────────────────────────────────")
        eng_supplier = _seed_supplier(
            db,
            carrier,
            ENG_SUPPLIER_NAME,
            ENG_SUPPLIER_TAX_ID,
            ENG_CONTRACT_NAME,
            ENG_RATE_CARDS,
            ENG_GUIDELINES,
            "Demo contract — Engineering & Forensic services, national scope.",
        )

        # ── LA supplier ────────────────────────────────────────────────────────
        print("\n── Ladder Assist supplier ────────────────────────────────────────")
        la_supplier = _seed_supplier(
            db,
            carrier,
            LA_SUPPLIER_NAME,
            LA_SUPPLIER_TAX_ID,
            LA_CONTRACT_NAME,
            LA_RATE_CARDS,
            LA_GUIDELINES,
            "Demo contract — Ladder Assist & Roof Access services, national scope.",
        )

        # ── User accounts (optional) ───────────────────────────────────────────
        if not SKIP_USERS:
            _prompt_user(
                db,
                eng_supplier,
                UserRole.SUPPLIER,
                "supplier@pacificcoasteng.com",
                "ENG supplier user (Pacific Coast Engineering Group)",
            )
            _prompt_user(
                db,
                la_supplier,
                UserRole.SUPPLIER,
                "supplier@summitladderassist.com",
                "LA supplier user (Summit Ladder Assist Inc.)",
            )
        else:
            print("\n── Skipping user creation (--skip-users flag set) ────────────")

        db.commit()

        print("\n✅ ENG & LA seed complete.\n")
        print("Next steps:")
        print("  1. Log in as ENG supplier → fixtures/sample_invoice_eng.csv")
        print("  2. Log in as LA supplier  → fixtures/sample_invoice_la.csv")
        print("  3. Submit each via the supplier portal (New Invoice)")
        print("  4. Monitor the carrier review queue\n")

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
