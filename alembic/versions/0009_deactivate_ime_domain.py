"""Deactivate IME taxonomy domain — replaced by focused P&C ALAE categories.

IME (Independent Medical Examination) codes are no longer part of the
Veridian ALAE taxonomy. Existing DB rows are soft-deactivated (is_active=False)
rather than deleted to preserve historical invoice references.

Revision ID: 0009
Revises: 0008
Create Date: 2026-03-28
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE taxonomy_items SET is_active = FALSE WHERE domain = 'IME'"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE taxonomy_items SET is_active = TRUE WHERE domain = 'IME'"
        )
    )
