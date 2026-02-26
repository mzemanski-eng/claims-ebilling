"""Initial schema — all tables for v1

Revision ID: 0001
Revises:
Create Date: 2026-02-25

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── taxonomy_items ────────────────────────────────────────────────────────
    op.create_table(
        "taxonomy_items",
        sa.Column("code", sa.String(64), primary_key=True),
        sa.Column("domain", sa.String(16), nullable=False),
        sa.Column("service_item", sa.String(32), nullable=False),
        sa.Column("billing_component", sa.String(32), nullable=False),
        sa.Column("unit_model", sa.String(32), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
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
    )
    op.create_index("ix_taxonomy_items_domain", "taxonomy_items", ["domain"])

    # ── carriers ──────────────────────────────────────────────────────────────
    op.create_table(
        "carriers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("short_code", sa.String(16), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
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
    )

    # ── suppliers ─────────────────────────────────────────────────────────────
    op.create_table(
        "suppliers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("tax_id", sa.String(32), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
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
    )

    # ── users ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(256), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(256), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column(
            "supplier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "carrier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("carriers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
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
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_supplier_id", "users", ["supplier_id"])
    op.create_index("ix_users_carrier_id", "users", ["carrier_id"])

    # ── contracts ─────────────────────────────────────────────────────────────
    op.create_table(
        "contracts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "supplier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "carrier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("carriers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date, nullable=True),
        sa.Column("geography_scope", sa.String(16), nullable=False),
        sa.Column("state_codes", postgresql.JSONB, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
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
        sa.UniqueConstraint(
            "supplier_id", "carrier_id", "effective_from", name="uq_contract_effective"
        ),
    )
    op.create_index("ix_contracts_supplier_id", "contracts", ["supplier_id"])
    op.create_index("ix_contracts_carrier_id", "contracts", ["carrier_id"])

    # ── rate_cards ────────────────────────────────────────────────────────────
    op.create_table(
        "rate_cards",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contracts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "taxonomy_code",
            sa.String(64),
            sa.ForeignKey("taxonomy_items.code", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("contracted_rate", sa.Numeric(12, 4), nullable=False),
        sa.Column("max_units", sa.Numeric(10, 4), nullable=True),
        sa.Column(
            "is_all_inclusive", sa.Boolean, nullable=False, server_default="false"
        ),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
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
    )
    op.create_index("ix_rate_cards_contract_id", "rate_cards", ["contract_id"])
    op.create_index("ix_rate_cards_taxonomy_code", "rate_cards", ["taxonomy_code"])

    # ── guidelines ────────────────────────────────────────────────────────────
    op.create_table(
        "guidelines",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contracts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "taxonomy_code",
            sa.String(64),
            sa.ForeignKey("taxonomy_items.code", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("domain", sa.String(16), nullable=True),
        sa.Column("rule_type", sa.String(32), nullable=False),
        sa.Column("rule_params", postgresql.JSONB, nullable=False),
        sa.Column("severity", sa.String(16), nullable=False, server_default="ERROR"),
        sa.Column("narrative_source", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
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
    )
    op.create_index("ix_guidelines_contract_id", "guidelines", ["contract_id"])
    op.create_index("ix_guidelines_taxonomy_code", "guidelines", ["taxonomy_code"])

    # ── invoices ──────────────────────────────────────────────────────────────
    op.create_table(
        "invoices",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "supplier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contracts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("invoice_number", sa.String(128), nullable=False),
        sa.Column("invoice_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("raw_file_path", sa.String(512), nullable=True),
        sa.Column("file_format", sa.String(8), nullable=True),
        sa.Column("current_version", sa.Integer, nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submission_notes", sa.Text, nullable=True),
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
    )
    op.create_index("ix_invoices_supplier_id", "invoices", ["supplier_id"])
    op.create_index("ix_invoices_contract_id", "invoices", ["contract_id"])
    op.create_index("ix_invoices_invoice_number", "invoices", ["invoice_number"])
    op.create_index("ix_invoices_status", "invoices", ["status"])

    # ── invoice_versions ──────────────────────────────────────────────────────
    op.create_table(
        "invoice_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("raw_file_path", sa.String(512), nullable=False),
        sa.Column("file_format", sa.String(8), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
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
        sa.UniqueConstraint("invoice_id", "version_number", name="uq_invoice_version"),
    )
    op.create_index(
        "ix_invoice_versions_invoice_id", "invoice_versions", ["invoice_id"]
    )

    # ── mapping_rules (self-referential FK added after table creation) ─────────
    op.create_table(
        "mapping_rules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "supplier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("match_type", sa.String(32), nullable=False),
        sa.Column("match_pattern", sa.Text, nullable=False),
        sa.Column(
            "taxonomy_code",
            sa.String(64),
            sa.ForeignKey("taxonomy_items.code", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("billing_component", sa.String(32), nullable=False),
        sa.Column("confidence_weight", sa.Float, nullable=False),
        sa.Column("confidence_label", sa.String(8), nullable=False),
        sa.Column("confirmed_by", sa.String(32), nullable=False),
        sa.Column(
            "confirmed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "supersedes_rule_id", postgresql.UUID(as_uuid=True), nullable=True
        ),  # FK added below
        sa.Column("notes", sa.Text, nullable=True),
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
    )
    # Self-referential FK added after table exists
    op.create_foreign_key(
        "fk_mapping_rules_supersedes",
        "mapping_rules",
        "mapping_rules",
        ["supersedes_rule_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_mapping_rules_supplier_id", "mapping_rules", ["supplier_id"])
    op.create_index(
        "ix_mapping_rules_taxonomy_code", "mapping_rules", ["taxonomy_code"]
    )

    # ── line_items ────────────────────────────────────────────────────────────
    op.create_table(
        "line_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("invoice_version", sa.Integer, nullable=False),
        sa.Column("line_number", sa.Integer, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("raw_description", sa.Text, nullable=False),
        sa.Column("raw_code", sa.String(64), nullable=True),
        sa.Column("raw_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("raw_quantity", sa.Numeric(10, 4), nullable=False),
        sa.Column("raw_unit", sa.String(32), nullable=True),
        sa.Column("claim_number", sa.String(64), nullable=True),
        sa.Column("service_date", sa.Date, nullable=True),
        sa.Column(
            "taxonomy_code",
            sa.String(64),
            sa.ForeignKey("taxonomy_items.code", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("billing_component", sa.String(32), nullable=True),
        sa.Column("mapped_unit_model", sa.String(32), nullable=True),
        sa.Column("mapping_confidence", sa.String(8), nullable=True),
        sa.Column(
            "mapping_rule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mapping_rules.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("mapped_rate", sa.Numeric(12, 4), nullable=True),
        sa.Column("expected_amount", sa.Numeric(12, 2), nullable=True),
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
    )
    op.create_index("ix_line_items_invoice_id", "line_items", ["invoice_id"])
    op.create_index("ix_line_items_status", "line_items", ["status"])
    op.create_index("ix_line_items_taxonomy_code", "line_items", ["taxonomy_code"])
    op.create_index("ix_line_items_claim_number", "line_items", ["claim_number"])

    # ── raw_extraction_artifacts ──────────────────────────────────────────────
    op.create_table(
        "raw_extraction_artifacts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "invoice_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoice_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer, nullable=True),
        sa.Column("raw_text", sa.Text, nullable=False),
        sa.Column("extraction_method", sa.String(32), nullable=False),
        sa.Column("extraction_metadata", postgresql.JSONB, nullable=True),
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
    )
    op.create_index(
        "ix_raw_extraction_artifacts_invoice_version_id",
        "raw_extraction_artifacts",
        ["invoice_version_id"],
    )

    # ── validation_results ────────────────────────────────────────────────────
    op.create_table(
        "validation_results",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "line_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("line_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("validation_type", sa.String(32), nullable=False),
        sa.Column(
            "rate_card_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rate_cards.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "guideline_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guidelines.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("expected_value", sa.String(256), nullable=True),
        sa.Column("actual_value", sa.String(256), nullable=True),
        sa.Column("required_action", sa.String(32), nullable=False),
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
    )
    op.create_index(
        "ix_validation_results_line_item_id", "validation_results", ["line_item_id"]
    )

    # ── exception_records ─────────────────────────────────────────────────────
    op.create_table(
        "exception_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "line_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("line_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "validation_result_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("validation_results.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("supplier_response", sa.Text, nullable=True),
        sa.Column("supporting_doc_path", sa.String(512), nullable=True),
        sa.Column("resolution_action", sa.String(32), nullable=True),
        sa.Column("resolution_notes", sa.Text, nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "resolved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
    )
    op.create_index(
        "ix_exception_records_line_item_id", "exception_records", ["line_item_id"]
    )
    op.create_index("ix_exception_records_status", "exception_records", ["status"])

    # ── audit_events ──────────────────────────────────────────────────────────
    op.create_table(
        "audit_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_audit_events_entity_type", "audit_events", ["entity_type"])
    op.create_index("ix_audit_events_entity_id", "audit_events", ["entity_id"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("audit_events")
    op.drop_table("exception_records")
    op.drop_table("validation_results")
    op.drop_table("raw_extraction_artifacts")
    op.drop_table("line_items")
    op.drop_constraint(
        "fk_mapping_rules_supersedes", "mapping_rules", type_="foreignkey"
    )
    op.drop_table("mapping_rules")
    op.drop_table("invoice_versions")
    op.drop_table("invoices")
    op.drop_table("guidelines")
    op.drop_table("rate_cards")
    op.drop_table("contracts")
    op.drop_table("users")
    op.drop_table("suppliers")
    op.drop_table("carriers")
    op.drop_table("taxonomy_items")
