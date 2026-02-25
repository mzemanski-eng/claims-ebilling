"""
SQLAlchemy engine and session setup.

Usage in FastAPI route handlers:
    from app.database import get_db
    def my_route(db: Session = Depends(get_db)): ...

Usage in RQ worker jobs (synchronous):
    from app.database import SessionLocal
    with SessionLocal() as db:
        ...
"""

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.settings import settings

# ── Engine ─────────────────────────────────────────────────────────────────
# pool_pre_ping=True: validates connections before use — important for
# long-lived worker processes that may outlive a Postgres connection.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=settings.is_development,  # log SQL in dev only
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    class_=Session,
)


# ── FastAPI dependency ──────────────────────────────────────────────────────
def get_db() -> Generator[Session, None, None]:
    """Yield a database session, ensuring it is closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Health check helper ─────────────────────────────────────────────────────
def check_db_connection() -> bool:
    """Return True if the database is reachable. Used by /health endpoint."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
