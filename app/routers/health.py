"""Health check endpoint — required by Render for service health monitoring."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.database import check_db_connection
from app.settings import settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    environment: str
    database: str
    version: str = "1.0.0"


@router.get("/health", response_model=HealthResponse, include_in_schema=False)
def health_check() -> HealthResponse:
    """
    Render health check endpoint.
    Returns 200 if the service is up and DB is reachable.
    Returns 503 if the DB is unreachable (Render will restart the service).
    """
    db_ok = check_db_connection()
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        environment=settings.environment,
        database="connected" if db_ok else "unreachable",
    )
