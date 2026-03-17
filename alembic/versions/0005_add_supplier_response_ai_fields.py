"""Add supplier response AI assessment and AI recommendation accuracy tracking.

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-17

New nullable columns on exception_records:
  - ai_response_assessment VARCHAR(16)  — SUFFICIENT | INSUFFICIENT | PARTIAL
  - ai_response_reasoning  TEXT         — carrier-facing explanation
  - ai_recommendation_accepted BOOLEAN  — True if carrier chose AI rec; False if overridden
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "exception_records",
        sa.Column(
            "ai_response_assessment",
            sa.String(16),
            nullable=True,
            comment="AI verdict on supplier response: SUFFICIENT | INSUFFICIENT | PARTIAL",
        ),
    )
    op.add_column(
        "exception_records",
        sa.Column(
            "ai_response_reasoning",
            sa.Text,
            nullable=True,
            comment="AI explanation of the response assessment — displayed to carrier",
        ),
    )
    op.add_column(
        "exception_records",
        sa.Column(
            "ai_recommendation_accepted",
            sa.Boolean,
            nullable=True,
            comment="True if carrier chose the AI recommendation; False if overridden; "
                    "NULL if no AI recommendation existed at resolution time",
        ),
    )


def downgrade() -> None:
    op.drop_column("exception_records", "ai_recommendation_accepted")
    op.drop_column("exception_records", "ai_response_reasoning")
    op.drop_column("exception_records", "ai_response_assessment")
