"""Add category_scope and supplier_scope to users table.

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-18

Adds two nullable JSONB columns to the users table to support auditor
assignment within a carrier:

  category_scope  — list of taxonomy domain prefixes (e.g. ["ENG", "LA"])
                    that this user is responsible for reviewing.
                    NULL means the user sees all domains.

  supplier_scope  — list of supplier UUIDs (as strings) this user is
                    assigned to. NULL means the user sees all suppliers.

These fields are only meaningful for CARRIER_ADMIN and CARRIER_REVIEWER
roles. SUPPLIER users and SYSTEM_ADMIN ignore them.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "category_scope",
            JSONB,
            nullable=True,
            comment="Taxonomy domain prefixes this auditor is responsible for. NULL = all domains.",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "supplier_scope",
            JSONB,
            nullable=True,
            comment="Supplier UUIDs (strings) this auditor is assigned to. NULL = all suppliers.",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "supplier_scope")
    op.drop_column("users", "category_scope")
