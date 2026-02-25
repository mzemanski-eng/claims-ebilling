"""
Test fixtures and shared setup.

Uses a separate test database (claims_ebilling_test).
All tests run in transactions that are rolled back after each test —
so the DB is always clean without needing to truncate tables.
"""

import os
import pytest
from decimal import Decimal
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# ── Override settings BEFORE importing app modules ────────────────────────────
os.environ.setdefault(
    "DATABASE_URL", "postgresql://postgres:test@localhost/claims_ebilling_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("LOCAL_STORAGE_PATH", "/tmp/claims_test_uploads")

from app.main import app
from app.database import get_db
from app.models.base import Base
from app.models import *  # noqa — ensures all models registered
from app.taxonomy.seed import seed_taxonomy


# ── Test engine ───────────────────────────────────────────────────────────────
TEST_DATABASE_URL = os.environ["DATABASE_URL"]
test_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
TestSessionLocal = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)


@pytest.fixture(scope="session")
def create_test_tables():
    """
    Create all tables once per test session.
    NOT autouse — only runs for tests that need DB fixtures.
    DB-independent tests (classifier, CSV parser) run without this.
    """
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="session")
def seed_test_taxonomy(create_test_tables):
    """Seed taxonomy once per session (idempotent)."""
    with TestSessionLocal() as session:
        seed_taxonomy(session)


@pytest.fixture
def db(seed_test_taxonomy) -> Session:
    """
    Provide a DB session that is rolled back after each test.
    Depends on seed_test_taxonomy which ensures tables exist + taxonomy seeded.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db: Session) -> TestClient:
    """
    FastAPI test client with DB dependency overridden to use the test session.
    """

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── Data builder fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def sample_carrier(db: Session):
    from app.models.supplier import Carrier

    carrier = Carrier(name="Test Carrier Inc.", short_code="TCI")
    db.add(carrier)
    db.flush()
    return carrier


@pytest.fixture
def sample_supplier(db: Session):
    from app.models.supplier import Supplier

    supplier = Supplier(name="Test IME Services LLC", tax_id="12-3456789")
    db.add(supplier)
    db.flush()
    return supplier


@pytest.fixture
def sample_contract(db: Session, sample_carrier, sample_supplier):
    from app.models.supplier import Contract

    contract = Contract(
        supplier_id=sample_supplier.id,
        carrier_id=sample_carrier.id,
        name="Test IME Contract 2024",
        effective_from=date(2024, 1, 1),
        geography_scope="national",
    )
    db.add(contract)
    db.flush()
    return contract


@pytest.fixture
def sample_rate_cards(db: Session, sample_contract):
    from app.models.supplier import RateCard

    rates = [
        RateCard(
            contract_id=sample_contract.id,
            taxonomy_code="IME.PHY_EXAM.PROF_FEE",
            contracted_rate=Decimal("600.00"),
            effective_from=date(2024, 1, 1),
        ),
        RateCard(
            contract_id=sample_contract.id,
            taxonomy_code="IME.PHY_EXAM.MILEAGE",
            contracted_rate=Decimal("0.67"),
            effective_from=date(2024, 1, 1),
        ),
        RateCard(
            contract_id=sample_contract.id,
            taxonomy_code="IME.ADDENDUM.PROF_FEE",
            contracted_rate=Decimal("125.00"),
            effective_from=date(2024, 1, 1),
        ),
        RateCard(
            contract_id=sample_contract.id,
            taxonomy_code="IME.NO_SHOW.NO_SHOW_FEE",
            contracted_rate=Decimal("100.00"),
            effective_from=date(2024, 1, 1),
        ),
        RateCard(
            contract_id=sample_contract.id,
            taxonomy_code="IME.CANCELLATION.CANCEL_FEE",
            contracted_rate=Decimal("150.00"),
            effective_from=date(2024, 1, 1),
        ),
    ]
    for r in rates:
        db.add(r)
    db.flush()
    return rates


@pytest.fixture
def sample_invoice(db: Session, sample_supplier, sample_contract):
    from app.models.invoice import Invoice, SubmissionStatus

    invoice = Invoice(
        supplier_id=sample_supplier.id,
        contract_id=sample_contract.id,
        invoice_number="INV-TEST-001",
        invoice_date=date(2024, 11, 15),
        status=SubmissionStatus.DRAFT,
        current_version=1,
    )
    db.add(invoice)
    db.flush()
    return invoice


@pytest.fixture
def sample_csv_bytes() -> bytes:
    """The canonical test fixture CSV — covers all exception types."""
    path = os.path.join(
        os.path.dirname(__file__), "..", "fixtures", "sample_invoice_ime.csv"
    )
    with open(path, "rb") as f:
        return f.read()
