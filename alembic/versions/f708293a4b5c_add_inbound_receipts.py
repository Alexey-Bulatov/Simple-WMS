"""add inbound receipts

Revision ID: f708293a4b5c
Revises: e60718293a4b
"""

from alembic import op
import sqlalchemy as sa


revision = "f708293a4b5c"
down_revision = "e60718293a4b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inbound_receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("uid", sa.String(length=64), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("receipt_kind", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("source_name", sa.String(length=200), nullable=True),
        sa.Column("external_reference", sa.String(length=120), nullable=True),
        sa.Column("planned_date", sa.Date(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("command_hash", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=80), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("posted_stock_document_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"]),
        sa.ForeignKeyConstraint(
            ["posted_stock_document_id"],
            ["stock_documents.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column, unique in (
        ("uid", True),
        ("warehouse_id", False),
        ("receipt_kind", False),
        ("status", False),
        ("external_reference", False),
        ("planned_date", False),
        ("idempotency_key", True),
        ("actor", False),
        ("posted_stock_document_id", True),
    ):
        op.create_index(
            op.f(f"ix_inbound_receipts_{column}"),
            "inbound_receipts",
            [column],
            unique=unique,
        )

    op.create_table(
        "inbound_receipt_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("receipt_id", sa.Integer(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("input_quantity", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("input_uom_id", sa.Integer(), nullable=False),
        sa.Column("packaging_id", sa.Integer(), nullable=True),
        sa.Column(
            "expected_base_quantity",
            sa.Numeric(precision=20, scale=6),
            nullable=False,
        ),
        sa.Column("base_uom_id", sa.Integer(), nullable=False),
        sa.Column("conversion_factor", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("batch_number", sa.String(length=80), nullable=True),
        sa.Column("production_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("serial_number", sa.String(length=120), nullable=True),
        sa.Column("quality_status", sa.String(length=40), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "expiry_date IS NULL OR production_date IS NULL OR expiry_date >= production_date",
            name="ck_inbound_receipt_batch_dates",
        ),
        sa.CheckConstraint(
            "expected_base_quantity > 0",
            name="ck_inbound_receipt_expected_base_quantity",
        ),
        sa.CheckConstraint(
            "conversion_factor > 0",
            name="ck_inbound_receipt_conversion_factor",
        ),
        sa.CheckConstraint(
            "input_quantity > 0",
            name="ck_inbound_receipt_input_quantity",
        ),
        sa.ForeignKeyConstraint(["base_uom_id"], ["units_of_measure.id"]),
        sa.ForeignKeyConstraint(["input_uom_id"], ["units_of_measure.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["stock_owners.id"]),
        sa.ForeignKeyConstraint(["packaging_id"], ["product_packagings.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(
            ["receipt_id"],
            ["inbound_receipts.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "receipt_id",
            "line_no",
            name="uq_inbound_receipt_line_no",
        ),
    )
    for column in (
        "receipt_id",
        "product_id",
        "owner_id",
        "input_uom_id",
        "packaging_id",
        "base_uom_id",
        "batch_number",
        "expiry_date",
        "serial_number",
        "quality_status",
    ):
        op.create_index(
            op.f(f"ix_inbound_receipt_lines_{column}"),
            "inbound_receipt_lines",
            [column],
            unique=False,
        )


def downgrade() -> None:
    op.drop_table("inbound_receipt_lines")
    op.drop_table("inbound_receipts")
