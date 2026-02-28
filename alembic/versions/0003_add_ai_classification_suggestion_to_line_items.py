"""add ai_classification_suggestion to line_items

Revision ID: 0003
Revises: 0002
Create Date: 2026-02-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "line_items",
        sa.Column(
            "ai_classification_suggestion",
            JSONB,
            nullable=True,
            comment="AI classification suggestion for UNRECOGNIZED line items",
        ),
    )


def downgrade() -> None:
    op.drop_column("line_items", "ai_classification_suggestion")
