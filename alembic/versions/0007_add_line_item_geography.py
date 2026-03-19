"""Add service_state and service_zip to line_items table.

Revision ID: 0007
Revises: 0006
Create Date: 2026-03-19

Adds two optional geographic context columns to line_items so suppliers
can indicate where a service was physically performed:

  service_state  — 2-character US state code (e.g. "CA", "TX")
  service_zip    — ZIP / postal code (e.g. "90210")

Both columns are nullable — invoices submitted without location data
are unaffected. When present, these fields drive the geographic spend
analytics map and zip-level concentration reports.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "line_items",
        sa.Column(
            "service_state",
            sa.String(2),
            nullable=True,
            comment="2-char US state code where the service was performed, e.g. 'CA'",
        ),
    )
    op.add_column(
        "line_items",
        sa.Column(
            "service_zip",
            sa.String(10),
            nullable=True,
            comment="ZIP/postal code where the service was performed",
        ),
    )
    op.create_index(
        "ix_line_items_service_state", "line_items", ["service_state"], unique=False
    )
    op.create_index(
        "ix_line_items_service_zip", "line_items", ["service_zip"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_line_items_service_zip", table_name="line_items")
    op.drop_index("ix_line_items_service_state", table_name="line_items")
    op.drop_column("line_items", "service_zip")
    op.drop_column("line_items", "service_state")
