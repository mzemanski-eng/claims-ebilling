"""Add processed_at to invoices — records when AI pipeline finished.

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-04
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when AI pipeline finished processing this invoice",
        ),
    )


def downgrade() -> None:
    op.drop_column("invoices", "processed_at")
