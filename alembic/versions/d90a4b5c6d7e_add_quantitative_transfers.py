"""add quantitative transfers

Revision ID: d90a4b5c6d7e
Revises: c90a4b5c6d7e
"""

from alembic import op
import sqlalchemy as sa


revision = "d90a4b5c6d7e"
down_revision = "c90a4b5c6d7e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("logistic_transfers") as batch_op:
        for name in ("picking", "dispatch", "receiving"):
            batch_op.add_column(
                sa.Column(f"{name}_stock_document_id", sa.Integer(), nullable=True)
            )
            batch_op.add_column(
                sa.Column(f"{name}_idempotency_key", sa.String(120), nullable=True)
            )
            batch_op.add_column(
                sa.Column(f"{name}_command_hash", sa.String(64), nullable=True)
            )
            batch_op.create_foreign_key(
                f"fk_transfer_{name}_document",
                "stock_documents",
                [f"{name}_stock_document_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch_op.create_index(
                f"ix_logistic_transfers_{name}_stock_document_id",
                [f"{name}_stock_document_id"],
                unique=True,
            )
            batch_op.create_index(
                f"ix_logistic_transfers_{name}_idempotency_key",
                [f"{name}_idempotency_key"],
                unique=True,
            )

    op.create_table(
        "logistic_transfer_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("transfer_id", sa.Integer(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("line_uid", sa.String(80), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("input_quantity", sa.Numeric(20, 8), nullable=False),
        sa.Column("input_uom_id", sa.Integer(), nullable=False),
        sa.Column("packaging_id", sa.Integer(), nullable=True),
        sa.Column("requested_base_quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("base_uom_id", sa.Integer(), nullable=False),
        sa.Column("conversion_factor", sa.Numeric(20, 8), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=True),
        sa.Column("serial_number", sa.String(120), nullable=True),
        sa.Column("quality_status", sa.String(40), nullable=False, server_default="released"),
        sa.Column("reservation_result", sa.String(24), nullable=False, server_default="NONE"),
        sa.Column("reserved_base_quantity", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("picked_base_quantity", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("dispatched_base_quantity", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("received_base_quantity", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint("input_quantity > 0", name="ck_transfer_line_input_qty"),
        sa.CheckConstraint("requested_base_quantity > 0", name="ck_transfer_line_base_qty"),
        sa.CheckConstraint("conversion_factor > 0", name="ck_transfer_line_factor"),
        sa.CheckConstraint("reserved_base_quantity >= 0", name="ck_transfer_line_reserved"),
        sa.CheckConstraint("picked_base_quantity >= 0", name="ck_transfer_line_picked"),
        sa.CheckConstraint("dispatched_base_quantity >= 0", name="ck_transfer_line_dispatched"),
        sa.CheckConstraint("received_base_quantity >= 0", name="ck_transfer_line_received"),
        sa.ForeignKeyConstraint(["transfer_id"], ["logistic_transfers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["stock_owners.id"]),
        sa.ForeignKeyConstraint(["input_uom_id"], ["units_of_measure.id"]),
        sa.ForeignKeyConstraint(["packaging_id"], ["product_packagings.id"]),
        sa.ForeignKeyConstraint(["base_uom_id"], ["units_of_measure.id"]),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"]),
        sa.UniqueConstraint("transfer_id", "line_no", name="uq_transfer_line_no"),
        sa.UniqueConstraint("line_uid", name="uq_transfer_line_uid"),
    )
    for name, columns in (
        ("ix_logistic_transfer_lines_transfer_id", ["transfer_id"]),
        ("ix_logistic_transfer_lines_line_uid", ["line_uid"]),
        ("ix_logistic_transfer_lines_product_id", ["product_id"]),
        ("ix_logistic_transfer_lines_owner_id", ["owner_id"]),
        ("ix_logistic_transfer_lines_input_uom_id", ["input_uom_id"]),
        ("ix_logistic_transfer_lines_packaging_id", ["packaging_id"]),
        ("ix_logistic_transfer_lines_base_uom_id", ["base_uom_id"]),
        ("ix_logistic_transfer_lines_batch_id", ["batch_id"]),
        ("ix_logistic_transfer_lines_serial_number", ["serial_number"]),
        ("ix_logistic_transfer_lines_quality_status", ["quality_status"]),
        ("ix_logistic_transfer_lines_reservation_result", ["reservation_result"]),
    ):
        op.create_index(name, "logistic_transfer_lines", columns)

    op.create_table(
        "logistic_transfer_reservation_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("transfer_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("command_hash", sa.String(64), nullable=False),
        sa.Column("full_line_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("partial_line_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing_line_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actor", sa.String(80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["transfer_id"], ["logistic_transfers.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_logistic_transfer_reservation_attempts_transfer_id",
        "logistic_transfer_reservation_attempts",
        ["transfer_id"],
    )
    op.create_index(
        "ix_logistic_transfer_reservation_attempts_idempotency_key",
        "logistic_transfer_reservation_attempts",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_logistic_transfer_reservation_attempts_actor",
        "logistic_transfer_reservation_attempts",
        ["actor"],
    )

    op.create_table(
        "logistic_transfer_allocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("transfer_line_id", sa.Integer(), nullable=False),
        sa.Column("reservation_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("base_uom_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="reserved"),
        sa.Column("transfer_out_location_id", sa.Integer(), nullable=True),
        sa.Column("transfer_in_location_id", sa.Integer(), nullable=True),
        sa.Column("picking_stock_document_id", sa.Integer(), nullable=True),
        sa.Column("dispatch_stock_document_id", sa.Integer(), nullable=True),
        sa.Column("receiving_stock_document_id", sa.Integer(), nullable=True),
        sa.Column("picked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("quantity > 0", name="ck_transfer_allocation_quantity"),
        sa.ForeignKeyConstraint(["transfer_line_id"], ["logistic_transfer_lines.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reservation_id"], ["stock_reservations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["base_uom_id"], ["units_of_measure.id"]),
        sa.ForeignKeyConstraint(["transfer_out_location_id"], ["locations.id"]),
        sa.ForeignKeyConstraint(["transfer_in_location_id"], ["locations.id"]),
        sa.ForeignKeyConstraint(["picking_stock_document_id"], ["stock_documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["dispatch_stock_document_id"], ["stock_documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["receiving_stock_document_id"], ["stock_documents.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("reservation_id", name="uq_transfer_allocation_reservation"),
    )
    for name, columns in (
        ("ix_logistic_transfer_allocations_transfer_line_id", ["transfer_line_id"]),
        ("ix_logistic_transfer_allocations_reservation_id", ["reservation_id"]),
        ("ix_logistic_transfer_allocations_base_uom_id", ["base_uom_id"]),
        ("ix_logistic_transfer_allocations_status", ["status"]),
        ("ix_logistic_transfer_allocations_transfer_out_location_id", ["transfer_out_location_id"]),
        ("ix_logistic_transfer_allocations_transfer_in_location_id", ["transfer_in_location_id"]),
        ("ix_logistic_transfer_allocations_picking_stock_document_id", ["picking_stock_document_id"]),
        ("ix_logistic_transfer_allocations_dispatch_stock_document_id", ["dispatch_stock_document_id"]),
        ("ix_logistic_transfer_allocations_receiving_stock_document_id", ["receiving_stock_document_id"]),
    ):
        op.create_index(name, "logistic_transfer_allocations", columns)


def downgrade() -> None:
    op.drop_table("logistic_transfer_allocations")
    op.drop_table("logistic_transfer_reservation_attempts")
    op.drop_table("logistic_transfer_lines")
    with op.batch_alter_table("logistic_transfers") as batch_op:
        for name in reversed(("picking", "dispatch", "receiving")):
            batch_op.drop_index(f"ix_logistic_transfers_{name}_idempotency_key")
            batch_op.drop_index(f"ix_logistic_transfers_{name}_stock_document_id")
            batch_op.drop_constraint(f"fk_transfer_{name}_document", type_="foreignkey")
            batch_op.drop_column(f"{name}_command_hash")
            batch_op.drop_column(f"{name}_idempotency_key")
            batch_op.drop_column(f"{name}_stock_document_id")
