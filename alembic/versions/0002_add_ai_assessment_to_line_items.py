"""Add ai_description_assessment JSONB column to line_items

Revision ID: 0002
Revises: 0001
Create Date: 2026-02-27

Adds a nullable JSONB column to line_items that stores the AI-generated
description alignment assessment produced during invoice processing.

Shape when populated:
    {
        "score": "ALIGNED" | "PARTIAL" | "MISALIGNED",
        "rationale": "<one sentence explanation>",
        "model": "claude-haiku-4-5"
    }

NULL when:
  - ANTHROPIC_API_KEY is not set in environment
  - The line item was UNRECOGNIZED (no taxonomy code to compare against)
  - The AI call failed (network error, rate limit, etc.)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "line_items",
        sa.Column(
            "ai_description_assessment",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="AI alignment score for raw_description vs taxonomy",
        ),
    )


def downgrade() -> None:
    op.drop_column("line_items", "ai_description_assessment")
