"""
Central settings module.

All configuration comes from environment variables (or .env in local dev).
Never import settings directly from this file — always use the `settings`
singleton at the bottom so the entire app shares one instance.
"""

import json

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # silently ignore unrecognised env vars
        case_sensitive=False,
    )

    # ── Environment ────────────────────────────────────────────────────────
    environment: str = "development"
    log_level: str = "INFO"

    # ── Security ───────────────────────────────────────────────────────────
    secret_key: str = "CHANGE_ME_IN_PRODUCTION"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480  # 8 hours

    # ── Database ───────────────────────────────────────────────────────────
    database_url: str = "postgresql://postgres:dev@localhost:5432/claims_ebilling"

    # ── Redis / Worker ─────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379"
    rq_queue_name: str = "invoice-pipeline"

    # ── File Storage ───────────────────────────────────────────────────────
    storage_backend: str = "local"  # local | s3
    local_storage_path: str = "/tmp/claims_uploads"

    # S3-compatible (unused in v1; wired for v2 upgrade)
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_endpoint_url: str = ""  # non-AWS providers (Backblaze, etc.)

    # ── CORS ───────────────────────────────────────────────────────────────
    # Allowed origins for staging/production. Accepts:
    #   - A JSON array:          '["https://foo.com","https://bar.com"]'
    #   - Comma-separated:       "https://foo.com,https://bar.com"
    #   - Single URL:            "https://foo.com"
    # Ignored in development (allow_origins=["*"] is used instead).
    allowed_origins: list[str] = []

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v: object) -> list[str]:
        if isinstance(v, list):
            return v
        if not isinstance(v, str) or not v.strip():
            return []
        raw = v.strip()
        # Try JSON array first
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(x) for x in parsed]
            except json.JSONDecodeError:
                pass
        # Fall back to comma-separated string
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    # ── Derived helpers ────────────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


# Singleton — import this everywhere
settings = Settings()
