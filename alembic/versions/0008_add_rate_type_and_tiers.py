"""Add rate_type and rate_tiers to rate_cards for tiered billing support.

Revision ID: 0008
Revises: 0007
Create Date: 2026-03-20

rate_type values:
  flat       — single contracted_rate × quantity  (default, backwards-compatible)
  tiered     — rate_tiers JSONB bands applied to quantity
  hourly     — contracted_rate × hours
  mileage    — contracted_rate × miles
  per_diem   — contracted_rate × days

rate_tiers format (when rate_type = 'tiered'):
  [
    {"from_unit": 1,  "to_unit": 20,   "rate": "0.85"},
    {"from_unit": 21, "to_unit": null, "rate": "0.55"}
  ]
  to_unit: null means "unlimited / all remaining units"
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # rate_type: defaults to 'flat' — all existing rate cards stay valid
    op.add_column(
        "rate_cards",
        sa.Column(
            "rate_type",
            sa.String(16),
            nullable=False,
            server_default="flat",
            comment="flat | tiered | hourly | mileage | per_diem",
        ),
    )
    # rate_tiers: NULL for non-tiered rate cards; JSONB array for tiered
    op.add_column(
        "rate_cards",
        sa.Column(
            "rate_tiers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Band array for tiered rates: [{from_unit, to_unit|null, rate}]",
        ),
    )
    # contracted_rate can now be NULL for tiered rate cards (rate is in tiers)
    op.alter_column("rate_cards", "contracted_rate", nullable=True)


def downgrade() -> None:
    op.alter_column("rate_cards", "contracted_rate", nullable=False)
    op.drop_column("rate_cards", "rate_tiers")
    op.drop_column("rate_cards", "rate_type")
