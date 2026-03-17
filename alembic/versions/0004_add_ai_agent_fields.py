"""Add AI agent fields — exception resolver + invoice triage

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-17

Adds four nullable columns to support the three AI agents introduced in this
release:

exception_records:
  ai_recommendation  VARCHAR(32)  — AI-suggested resolution action
  ai_reasoning       TEXT         — AI explanation shown to carrier in UI

invoices:
  triage_risk_level  VARCHAR(16)  — LOW | MEDIUM | HIGH | CRITICAL (indexed)
  triage_notes       TEXT         — newline-separated risk factors from triage
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── exception_records ─────────────────────────────────────────────────────
    op.add_column(
        "exception_records",
        sa.Column(
            "ai_recommendation",
            sa.String(32),
            nullable=True,
            comment="AI-suggested resolution action (a ResolutionAction constant)",
        ),
    )
    op.add_column(
        "exception_records",
        sa.Column(
            "ai_reasoning",
            sa.Text(),
            nullable=True,
            comment="AI explanation for the recommendation — displayed to carrier in UI",
        ),
    )

    # ── invoices ──────────────────────────────────────────────────────────────
    op.add_column(
        "invoices",
        sa.Column(
            "triage_risk_level",
            sa.String(16),
            nullable=True,
            comment="AI triage risk level: LOW | MEDIUM | HIGH | CRITICAL",
        ),
    )
    op.create_index(
        "ix_invoices_triage_risk_level",
        "invoices",
        ["triage_risk_level"],
        unique=False,
    )
    op.add_column(
        "invoices",
        sa.Column(
            "triage_notes",
            sa.Text(),
            nullable=True,
            comment="Newline-separated AI risk factors from triage assessment",
        ),
    )


def downgrade() -> None:
    op.drop_column("invoices", "triage_notes")
    op.drop_index("ix_invoices_triage_risk_level", table_name="invoices")
    op.drop_column("invoices", "triage_risk_level")
    op.drop_column("exception_records", "ai_reasoning")
    op.drop_column("exception_records", "ai_recommendation")
