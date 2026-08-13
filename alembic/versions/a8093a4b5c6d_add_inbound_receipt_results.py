"""add inbound receipt results

Revision ID: a8093a4b5c6d
Revises: f708293a4b5c
"""

from alembic import op
import sqlalchemy as sa


revision = "a8093a4b5c6d"
down_revision = "f708293a4b5c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("inbound_receipts") as batch_op:
        batch_op.add_column(
            sa.Column("posting_idempotency_key", sa.String(length=120), nullable=True)
        )
        batch_op.add_column(
            sa.Column("posting_command_hash", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_index(
            op.f("ix_inbound_receipts_posting_idempotency_key"),
            ["posting_idempotency_key"],
            unique=False,
        )

    op.create_table(
        "inbound_receipt_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("receipt_line_id", sa.Integer(), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("stock_movement_id", sa.Integer(), nullable=False),
        sa.Column("input_quantity", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("input_uom_id", sa.Integer(), nullable=False),
        sa.Column("packaging_id", sa.Integer(), nullable=True),
        sa.Column(
            "received_base_quantity",
            sa.Numeric(precision=20, scale=6),
            nullable=False,
        ),
        sa.Column("base_uom_id", sa.Integer(), nullable=False),
        sa.Column("conversion_factor", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=True),
        sa.Column("serial_number", sa.String(length=120), nullable=True),
        sa.Column("quality_status", sa.String(length=40), nullable=False),
        sa.Column("destination_logistic_unit_id", sa.Integer(), nullable=True),
        sa.Column("destination_location_id", sa.Integer(), nullable=True),
        sa.Column("destination_scan", sa.String(length=120), nullable=False),
        sa.Column("item_scan", sa.String(length=120), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "received_base_quantity > 0",
            name="ck_inbound_result_base_quantity",
        ),
        sa.CheckConstraint(
            "conversion_factor > 0",
            name="ck_inbound_result_conversion_factor",
        ),
        sa.CheckConstraint(
            "input_quantity > 0",
            name="ck_inbound_result_input_quantity",
        ),
        sa.CheckConstraint(
            "(destination_logistic_unit_id IS NOT NULL AND destination_location_id IS NULL) OR "
            "(destination_logistic_unit_id IS NULL AND destination_location_id IS NOT NULL)",
            name="ck_inbound_result_single_destination",
        ),
        sa.ForeignKeyConstraint(["base_uom_id"], ["units_of_measure.id"]),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"]),
        sa.ForeignKeyConstraint(
            ["destination_location_id"],
            ["locations.id"],
        ),
        sa.ForeignKeyConstraint(
            ["destination_logistic_unit_id"],
            ["logistic_units.id"],
        ),
        sa.ForeignKeyConstraint(["input_uom_id"], ["units_of_measure.id"]),
        sa.ForeignKeyConstraint(["packaging_id"], ["product_packagings.id"]),
        sa.ForeignKeyConstraint(
            ["receipt_line_id"],
            ["inbound_receipt_lines.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["stock_movement_id"],
            ["stock_movements.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column, unique in (
        ("receipt_line_id", False),
        ("stock_movement_id", True),
        ("input_uom_id", False),
        ("packaging_id", False),
        ("base_uom_id", False),
        ("batch_id", False),
        ("serial_number", False),
        ("quality_status", False),
        ("destination_logistic_unit_id", False),
        ("destination_location_id", False),
    ):
        op.create_index(
            op.f(f"ix_inbound_receipt_results_{column}"),
            "inbound_receipt_results",
            [column],
            unique=unique,
        )


def downgrade() -> None:
    op.drop_table("inbound_receipt_results")
    with op.batch_alter_table("inbound_receipts") as batch_op:
        batch_op.drop_index(op.f("ix_inbound_receipts_posting_idempotency_key"))
        batch_op.drop_column("reversed_at")
        batch_op.drop_column("posting_command_hash")
        batch_op.drop_column("posting_idempotency_key")
