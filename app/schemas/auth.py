"""Auth schemas — login, token response."""

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
    sub: str          # user email
    role: str
    user_id: str
    supplier_id: str | None = None
    carrier_id: str | None = None
