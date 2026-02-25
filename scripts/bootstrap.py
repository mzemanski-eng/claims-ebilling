"""
Bootstrap script — create the first carrier and admin user.

Usage (local):
    python scripts/bootstrap.py

Usage (Render Shell):
    python scripts/bootstrap.py

Prompts for carrier name, short code, admin email, and password.
Idempotent — safe to re-run; skips records that already exist.
"""

import sys
import os

# Ensure the project root is on the path when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from getpass import getpass

from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models.supplier import Carrier, User, UserRole
from app.routers.auth import hash_password


def prompt(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


def main() -> None:
    print("\n=== Claims eBilling — Bootstrap ===\n")

    # ── Carrier ───────────────────────────────────────────────────────────────
    print("── Carrier ──────────────────────────────")
    carrier_name = prompt("Carrier name", "Demo Carrier")
    carrier_code = prompt("Short code (e.g. DEMO)", "DEMO").upper()

    # ── Admin user ────────────────────────────────────────────────────────────
    print("\n── Admin user ───────────────────────────")
    admin_email = prompt("Admin email")
    if not admin_email:
        print("ERROR: email is required.")
        sys.exit(1)

    admin_password = getpass("Admin password (min 8 chars): ")
    if len(admin_password) < 8:
        print("ERROR: password must be at least 8 characters.")
        sys.exit(1)

    confirm = getpass("Confirm password: ")
    if admin_password != confirm:
        print("ERROR: passwords do not match.")
        sys.exit(1)

    # ── Write to DB ───────────────────────────────────────────────────────────
    db = SessionLocal()
    try:
        # Carrier — skip if short_code already exists
        carrier = db.query(Carrier).filter(Carrier.short_code == carrier_code).first()
        if carrier:
            print(f"\n✓ Carrier '{carrier_code}' already exists (id={carrier.id}) — skipping.")
        else:
            carrier = Carrier(name=carrier_name, short_code=carrier_code)
            db.add(carrier)
            db.flush()  # get the id before commit
            print(f"\n✓ Carrier '{carrier_name}' ({carrier_code}) created (id={carrier.id})")

        # Admin user — skip if email already exists
        existing = db.query(User).filter(User.email == admin_email).first()
        if existing:
            print(f"✓ User '{admin_email}' already exists (role={existing.role}) — skipping.")
        else:
            user = User(
                email=admin_email,
                hashed_password=hash_password(admin_password),
                role=UserRole.SYSTEM_ADMIN,
                carrier_id=carrier.id,
                is_active=True,
            )
            db.add(user)
            print(f"✓ Admin user '{admin_email}' created (role=SYSTEM_ADMIN)")

        db.commit()
        print("\n✅ Bootstrap complete. You can now log in at /auth/token\n")

    except IntegrityError as e:
        db.rollback()
        print(f"\nERROR: Database integrity error — {e.orig}")
        sys.exit(1)
    except Exception as e:
        db.rollback()
        print(f"\nERROR: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
