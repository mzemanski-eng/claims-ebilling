"""add classification queue

Adds the classification_queue_items table which holds invoice line items
whose AI classification confidence fell below the auto-proceed threshold.

A carrier reviewer resolves items via the Classification Review screen.
Approval creates a CARRIER_CONFIRMED MappingRule so future similar lines
auto-classify without re-entering the queue.

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "classification_queue_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        # ── Subject ───────────────────────────────────────────────────────────
        sa.Column("line_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("raw_description", sa.Text(), nullable=False),
        sa.Column("raw_amount", sa.Numeric(12, 2), nullable=False),
        # ── AI proposal ───────────────────────────────────────────────────────
        sa.Column("ai_proposed_code", sa.String(64), nullable=True),
        sa.Column("ai_proposed_billing_component", sa.String(32), nullable=True),
        sa.Column("ai_confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("ai_reasoning", sa.Text(), nullable=True),
        sa.Column("ai_alternatives", postgresql.JSONB(), nullable=True),
        # ── Review ────────────────────────────────────────────────────────────
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("reviewed_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_code", sa.String(64), nullable=True),
        sa.Column("approved_billing_component", sa.String(32), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        # ── Outcome ───────────────────────────────────────────────────────────
        sa.Column(
            "created_mapping_rule_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        # ── Timestamps ────────────────────────────────────────────────────────
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # ── Constraints ───────────────────────────────────────────────────────
        sa.ForeignKeyConstraint(
            ["line_item_id"],
            ["line_items.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ai_proposed_code"],
            ["taxonomy_items.code"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["approved_code"],
            ["taxonomy_items.code"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_mapping_rule_id"],
            ["mapping_rules.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("line_item_id", name="uq_classification_queue_line_item"),
    )

    # ── Indexes ───────────────────────────────────────────────────────────────
    # Primary access patterns:
    #   - list all PENDING items for a supplier  (Classification Review screen)
    #   - list all PENDING items (carrier-wide queue)
    #   - lookup by line_item_id (already covered by the unique constraint)
    op.create_index(
        "ix_classification_queue_items_supplier_id",
        "classification_queue_items",
        ["supplier_id"],
    )
    op.create_index(
        "ix_classification_queue_items_status",
        "classification_queue_items",
        ["status"],
    )
    op.create_index(
        "ix_classification_queue_items_line_item_id",
        "classification_queue_items",
        ["line_item_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_classification_queue_items_line_item_id",
        table_name="classification_queue_items",
    )
    op.drop_index(
        "ix_classification_queue_items_status",
        table_name="classification_queue_items",
    )
    op.drop_index(
        "ix_classification_queue_items_supplier_id",
        table_name="classification_queue_items",
    )
    op.drop_table("classification_queue_items")
