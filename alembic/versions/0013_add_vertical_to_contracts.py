"""Add vertical_id FK to contracts table for per-vertical AI prompt routing.

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers
revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add nullable vertical_id FK to contracts — NULL = no vertical assigned
    op.add_column(
        "contracts",
        sa.Column(
            "vertical_id",
            UUID(as_uuid=True),
            sa.ForeignKey("verticals.id", ondelete="SET NULL"),
            nullable=True,
            comment="Line-of-business vertical for per-vertical AI prompt routing. NULL = default.",
        ),
    )
    op.create_index("ix_contracts_vertical_id", "contracts", ["vertical_id"])


def downgrade() -> None:
    op.drop_index("ix_contracts_vertical_id", table_name="contracts")
    op.drop_column("contracts", "vertical_id")
