"""Add settings JSONB to carriers — per-carrier pipeline configuration.

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "carriers",
        sa.Column(
            "settings",
            JSONB,
            nullable=False,
            server_default="{}",
            comment=(
                "Per-carrier pipeline and processing configuration. "
                "Keys: auto_approve_clean_invoices (bool), "
                "auto_approve_max_amount (float|null), "
                "require_review_above_amount (float|null), "
                "risk_tolerance (strict|standard|relaxed), "
                "ai_classification_mode (auto|supervised)."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("carriers", "settings")
