"""
Pydantic schemas for Supplier profile, SupplierDocument, and taxonomy import.
"""

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Supplier Profile ──────────────────────────────────────────────────────────


class SupplierProfileUpdate(BaseModel):
    """PATCH /admin/suppliers/{id}/profile — all fields optional (partial update)."""

    primary_contact_name: Optional[str] = Field(default=None, max_length=256)
    primary_contact_email: Optional[str] = Field(default=None, max_length=256)
    primary_contact_phone: Optional[str] = Field(default=None, max_length=32)
    address_line1: Optional[str] = Field(default=None, max_length=256)
    address_line2: Optional[str] = Field(default=None, max_length=256)
    city: Optional[str] = Field(default=None, max_length=128)
    state_code: Optional[str] = Field(default=None, max_length=2)
    zip_code: Optional[str] = Field(default=None, max_length=10)
    website: Optional[str] = Field(default=None, max_length=256)
    notes: Optional[str] = None


class SupplierProfileResponse(BaseModel):
    """Full supplier row returned by GET /admin/suppliers/{id}/profile."""

    id: uuid.UUID
    name: str
    tax_id: Optional[str]
    onboarding_status: str
    is_active: bool
    primary_contact_name: Optional[str]
    primary_contact_email: Optional[str]
    primary_contact_phone: Optional[str]
    address_line1: Optional[str]
    address_line2: Optional[str]
    city: Optional[str]
    state_code: Optional[str]
    zip_code: Optional[str]
    website: Optional[str]
    notes: Optional[str]
    submitted_at: Optional[datetime]
    approved_at: Optional[datetime]
    approved_by_id: Optional[uuid.UUID]
    contract_count: int
    invoice_count: int
    user_count: int

    model_config = {"from_attributes": True}


# ── SupplierDocument ──────────────────────────────────────────────────────────


class SupplierDocumentResponse(BaseModel):
    """One document row returned by list/upload endpoints."""

    id: uuid.UUID
    supplier_id: uuid.UUID
    document_type: str  # W9 | COI | MSA | OTHER
    filename: str
    storage_path: str
    file_size_bytes: Optional[int]
    uploaded_by_id: Optional[uuid.UUID]
    uploaded_at: datetime
    expires_at: Optional[date]
    notes: Optional[str]

    model_config = {"from_attributes": True}


# ── Taxonomy Import ───────────────────────────────────────────────────────────


class TaxonomyImportRowResult(BaseModel):
    """Result for one CSV row from the bulk taxonomy import."""

    row: int  # 1-indexed row number in CSV (row 1 = header, data starts at 2)
    supplier_code: str
    description: str
    matched_taxonomy_code: Optional[str]  # null = no match found
    confidence: Optional[str]  # HIGH | MEDIUM | LOW | null
    skipped: bool  # true if a rule already existed for this description
    error: Optional[str]  # non-null if this row failed


class TaxonomyImportResult(BaseModel):
    """Response from POST /admin/suppliers/{id}/taxonomy-import."""

    processed: int
    mapped: int
    skipped: int
    unmapped: int
    results: list[TaxonomyImportRowResult]
