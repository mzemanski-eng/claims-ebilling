"""Auth schemas — login, token response."""

import uuid
from typing import Optional

from pydantic import EmailStr, Field

from app.schemas.common import BaseSchema


class LoginRequest(BaseSchema):
    email: EmailStr
    password: str = Field(..., min_length=1)


class TokenResponse(BaseSchema):
    access_token: str
    token_type: str = "bearer"
    role: str
    supplier_id: str | None = None
    carrier_id: str | None = None


class TokenPayload(BaseSchema):
    """Decoded JWT payload."""

    sub: str  # user email
    role: str
    user_id: str
    supplier_id: str | None = None
    carrier_id: str | None = None


class UserMeResponse(BaseSchema):
    """Current authenticated user — returned by GET /auth/me."""

    id: uuid.UUID
    email: str
    role: str
    is_active: bool
    supplier_id: Optional[uuid.UUID] = None
    supplier_name: Optional[str] = None
    carrier_id: Optional[uuid.UUID] = None
    carrier_name: Optional[str] = None
