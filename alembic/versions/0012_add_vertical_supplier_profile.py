"""Add Vertical table, vertical_id FK on taxonomy_items, supplier profile columns, and supplier_documents table.

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Create verticals table ─────────────────────────────────────────────
    op.create_table(
        "verticals",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=text("gen_random_uuid()"),
        ),
        sa.Column("slug", sa.String(32), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            default=True,
            server_default="true",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("slug", name="uq_verticals_slug"),
    )

    # ── 2. Seed the three initial verticals ───────────────────────────────────
    op.execute(
        """
        INSERT INTO verticals (slug, name, is_active)
        VALUES
            ('ale', 'ALE', true),
            ('restoration', 'Restoration', true),
            ('legal', 'Legal', true)
        ON CONFLICT DO NOTHING
        """
    )

    # ── 3. Add vertical_id FK to taxonomy_items (nullable, SET NULL on delete) ─
    op.add_column(
        "taxonomy_items",
        sa.Column(
            "vertical_id",
            UUID(as_uuid=True),
            sa.ForeignKey("verticals.id", ondelete="SET NULL"),
            nullable=True,
            comment="Line-of-business vertical. NULL = not yet assigned.",
        ),
    )
    op.create_index(
        "ix_taxonomy_items_vertical_id", "taxonomy_items", ["vertical_id"]
    )

    # ── 4. Add onboarding_status to suppliers (VARCHAR, server_default='DRAFT') ─
    op.add_column(
        "suppliers",
        sa.Column(
            "onboarding_status",
            sa.String(32),
            nullable=False,
            server_default="DRAFT",
            comment="DRAFT | PENDING_REVIEW | ACTIVE | SUSPENDED",
        ),
    )

    # ── 5. Add profile columns to suppliers (all nullable) ────────────────────
    op.add_column(
        "suppliers",
        sa.Column("primary_contact_name", sa.String(256), nullable=True),
    )
    op.add_column(
        "suppliers",
        sa.Column("primary_contact_email", sa.String(256), nullable=True),
    )
    op.add_column(
        "suppliers",
        sa.Column("primary_contact_phone", sa.String(32), nullable=True),
    )
    op.add_column(
        "suppliers", sa.Column("address_line1", sa.String(256), nullable=True)
    )
    op.add_column(
        "suppliers", sa.Column("address_line2", sa.String(256), nullable=True)
    )
    op.add_column(
        "suppliers", sa.Column("city", sa.String(128), nullable=True)
    )
    op.add_column(
        "suppliers", sa.Column("state_code", sa.String(2), nullable=True)
    )
    op.add_column(
        "suppliers", sa.Column("zip_code", sa.String(10), nullable=True)
    )
    op.add_column(
        "suppliers", sa.Column("website", sa.String(256), nullable=True)
    )
    op.add_column("suppliers", sa.Column("notes", sa.Text, nullable=True))
    op.add_column(
        "suppliers",
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "suppliers",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "suppliers",
        sa.Column(
            "approved_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # ── 6. Backfill onboarding_status from is_active ──────────────────────────
    # Existing active suppliers → ACTIVE; inactive → SUSPENDED
    op.execute(
        """
        UPDATE suppliers
        SET onboarding_status = CASE
            WHEN is_active = true THEN 'ACTIVE'
            ELSE 'SUSPENDED'
        END
        """
    )

    # ── 7. Create supplier_documents table ────────────────────────────────────
    op.create_table(
        "supplier_documents",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=text("gen_random_uuid()"),
        ),
        sa.Column(
            "supplier_id",
            UUID(as_uuid=True),
            sa.ForeignKey("suppliers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_type",
            sa.String(16),
            nullable=False,
            comment="W9 | COI | MSA | OTHER",
        ),
        sa.Column("filename", sa.String(256), nullable=False),
        sa.Column("storage_path", sa.String(512), nullable=False),
        sa.Column("file_size_bytes", sa.Integer, nullable=True),
        sa.Column(
            "uploaded_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.Date, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_supplier_documents_supplier_id",
        "supplier_documents",
        ["supplier_id"],
    )
    op.create_index(
        "ix_supplier_documents_document_type",
        "supplier_documents",
        ["document_type"],
    )


def downgrade() -> None:
    op.drop_table("supplier_documents")

    op.drop_column("suppliers", "approved_by_id")
    op.drop_column("suppliers", "approved_at")
    op.drop_column("suppliers", "submitted_at")
    op.drop_column("suppliers", "notes")
    op.drop_column("suppliers", "website")
    op.drop_column("suppliers", "zip_code")
    op.drop_column("suppliers", "state_code")
    op.drop_column("suppliers", "city")
    op.drop_column("suppliers", "address_line2")
    op.drop_column("suppliers", "address_line1")
    op.drop_column("suppliers", "primary_contact_phone")
    op.drop_column("suppliers", "primary_contact_email")
    op.drop_column("suppliers", "primary_contact_name")
    op.drop_column("suppliers", "onboarding_status")

    op.drop_index("ix_taxonomy_items_vertical_id", table_name="taxonomy_items")
    op.drop_column("taxonomy_items", "vertical_id")

    op.drop_table("verticals")
