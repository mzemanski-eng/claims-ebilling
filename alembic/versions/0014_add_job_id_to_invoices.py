"""Add job_id and job_queued_at to invoices for async RQ processing.

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-06
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column(
            "job_id",
            sa.String(length=128),
            nullable=True,
            comment="RQ job ID for async processing; used for DLQ lookups",
        ),
    )
    op.add_column(
        "invoices",
        sa.Column(
            "job_queued_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when the invoice was enqueued for processing",
        ),
    )
    op.create_index("ix_invoices_job_id", "invoices", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_invoices_job_id", table_name="invoices")
    op.drop_column("invoices", "job_queued_at")
    op.drop_column("invoices", "job_id")
