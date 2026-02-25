"""Shared schema primitives."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class IDSchema(BaseSchema):
    id: uuid.UUID


class TimestampedSchema(IDSchema):
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseSchema):
    message: str


class ErrorDetail(BaseSchema):
    field: str | None = None
    message: str


class ErrorResponse(BaseSchema):
    error: str
    details: list[ErrorDetail] = []
