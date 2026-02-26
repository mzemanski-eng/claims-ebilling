"""
FastAPI application factory.

Uses lifespan context manager (preferred over on_event decorators in FastAPI 0.93+)
to handle startup/shutdown tasks cleanly.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import health, auth, supplier, admin, carrier
from app.settings import settings

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    logger.info("Starting Claims eBilling API [env=%s]", settings.environment)

    # Verify DB connectivity on startup (fail fast)
    from app.database import check_db_connection

    if not check_db_connection():
        logger.error("Database is not reachable on startup — check DATABASE_URL")
    else:
        logger.info("Database connection verified")

    # Ensure local storage directory exists
    if settings.storage_backend == "local":
        import os

        os.makedirs(settings.local_storage_path, exist_ok=True)
        logger.info("Local storage path: %s", settings.local_storage_path)

    yield  # ── Application runs here ──

    logger.info("Shutting down Claims eBilling API")


# ── App factory ───────────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title="Claims ALAE eBilling Platform",
        description=(
            "Purpose-built eBilling platform for Claims ALAE vendor services. "
            "Automates invoice ingestion, classification, rate and guideline validation, "
            "and exception resolution for IME, Engineering, IA, Investigation, "
            "and Record Retrieval services."
        ),
        version="1.0.0",
        lifespan=lifespan,
        # Disable docs in production (enable for internal use or with auth)
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Dev: allow all origins. Staging/prod: explicit allowlist from ALLOWED_ORIGINS env var.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.is_development else settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(supplier.router)
    app.include_router(admin.router)
    app.include_router(carrier.router)

    return app


app = create_app()
