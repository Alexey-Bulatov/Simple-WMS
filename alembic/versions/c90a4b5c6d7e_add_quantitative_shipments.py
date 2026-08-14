"""add quantitative shipments

Revision ID: c90a4b5c6d7e
Revises: b90a4b5c6d7e
"""

from alembic import op
import sqlalchemy as sa


revision = "c90a4b5c6d7e"
down_revision = "b90a4b5c6d7e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("logistic_shipments") as batch_op:
        batch_op.add_column(sa.Column("picking_stock_document_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("picking_idempotency_key", sa.String(120), nullable=True))
        batch_op.add_column(sa.Column("picking_command_hash", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("loading_stock_document_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("loading_idempotency_key", sa.String(120), nullable=True))
        batch_op.add_column(sa.Column("loading_command_hash", sa.String(64), nullable=True))
        batch_op.create_foreign_key(
            "fk_shipment_pick_document",
            "stock_documents",
            ["picking_stock_document_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_shipment_load_document",
            "stock_documents",
            ["loading_stock_document_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_logistic_shipments_picking_stock_document_id", ["picking_stock_document_id"], unique=True)
        batch_op.create_index("ix_logistic_shipments_picking_idempotency_key", ["picking_idempotency_key"], unique=True)
        batch_op.create_index("ix_logistic_shipments_loading_stock_document_id", ["loading_stock_document_id"], unique=True)
        batch_op.create_index("ix_logistic_shipments_loading_idempotency_key", ["loading_idempotency_key"], unique=True)

    op.create_table(
        "logistic_shipment_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shipment_id", sa.Integer(), nullable=False),
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
        sa.Column("loaded_base_quantity", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint("input_quantity > 0", name="ck_shipment_line_input_qty"),
        sa.CheckConstraint("requested_base_quantity > 0", name="ck_shipment_line_base_qty"),
        sa.CheckConstraint("conversion_factor > 0", name="ck_shipment_line_factor"),
        sa.CheckConstraint("reserved_base_quantity >= 0", name="ck_shipment_line_reserved"),
        sa.CheckConstraint("picked_base_quantity >= 0", name="ck_shipment_line_picked"),
        sa.CheckConstraint("loaded_base_quantity >= 0", name="ck_shipment_line_loaded"),
        sa.ForeignKeyConstraint(["shipment_id"], ["logistic_shipments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["stock_owners.id"]),
        sa.ForeignKeyConstraint(["input_uom_id"], ["units_of_measure.id"]),
        sa.ForeignKeyConstraint(["packaging_id"], ["product_packagings.id"]),
        sa.ForeignKeyConstraint(["base_uom_id"], ["units_of_measure.id"]),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"]),
        sa.UniqueConstraint("shipment_id", "line_no", name="uq_shipment_line_no"),
        sa.UniqueConstraint("line_uid", name="uq_shipment_line_uid"),
    )
    for name, columns in (
        ("ix_logistic_shipment_lines_shipment_id", ["shipment_id"]),
        ("ix_logistic_shipment_lines_line_uid", ["line_uid"]),
        ("ix_logistic_shipment_lines_product_id", ["product_id"]),
        ("ix_logistic_shipment_lines_owner_id", ["owner_id"]),
        ("ix_logistic_shipment_lines_input_uom_id", ["input_uom_id"]),
        ("ix_logistic_shipment_lines_packaging_id", ["packaging_id"]),
        ("ix_logistic_shipment_lines_base_uom_id", ["base_uom_id"]),
        ("ix_logistic_shipment_lines_batch_id", ["batch_id"]),
        ("ix_logistic_shipment_lines_serial_number", ["serial_number"]),
        ("ix_logistic_shipment_lines_quality_status", ["quality_status"]),
        ("ix_logistic_shipment_lines_reservation_result", ["reservation_result"]),
    ):
        op.create_index(name, "logistic_shipment_lines", columns)

    op.create_table(
        "logistic_shipment_reservation_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shipment_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("command_hash", sa.String(64), nullable=False),
        sa.Column("full_line_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("partial_line_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing_line_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actor", sa.String(80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["shipment_id"], ["logistic_shipments.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_logistic_shipment_reservation_attempts_shipment_id", "logistic_shipment_reservation_attempts", ["shipment_id"])
    op.create_index("ix_logistic_shipment_reservation_attempts_idempotency_key", "logistic_shipment_reservation_attempts", ["idempotency_key"], unique=True)
    op.create_index("ix_logistic_shipment_reservation_attempts_actor", "logistic_shipment_reservation_attempts", ["actor"])

    op.create_table(
        "logistic_shipment_allocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shipment_line_id", sa.Integer(), nullable=False),
        sa.Column("reservation_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("base_uom_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="reserved"),
        sa.Column("expedition_location_id", sa.Integer(), nullable=True),
        sa.Column("picking_stock_document_id", sa.Integer(), nullable=True),
        sa.Column("loading_stock_document_id", sa.Integer(), nullable=True),
        sa.Column("picked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("quantity > 0", name="ck_shipment_allocation_quantity"),
        sa.ForeignKeyConstraint(["shipment_line_id"], ["logistic_shipment_lines.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reservation_id"], ["stock_reservations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["base_uom_id"], ["units_of_measure.id"]),
        sa.ForeignKeyConstraint(["expedition_location_id"], ["locations.id"]),
        sa.ForeignKeyConstraint(["picking_stock_document_id"], ["stock_documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["loading_stock_document_id"], ["stock_documents.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("reservation_id", name="uq_shipment_allocation_reservation"),
    )
    for name, columns in (
        ("ix_logistic_shipment_allocations_shipment_line_id", ["shipment_line_id"]),
        ("ix_logistic_shipment_allocations_reservation_id", ["reservation_id"]),
        ("ix_logistic_shipment_allocations_base_uom_id", ["base_uom_id"]),
        ("ix_logistic_shipment_allocations_status", ["status"]),
        ("ix_logistic_shipment_allocations_expedition_location_id", ["expedition_location_id"]),
        ("ix_logistic_shipment_allocations_picking_stock_document_id", ["picking_stock_document_id"]),
        ("ix_logistic_shipment_allocations_loading_stock_document_id", ["loading_stock_document_id"]),
    ):
        op.create_index(name, "logistic_shipment_allocations", columns)


def downgrade() -> None:
    op.drop_table("logistic_shipment_allocations")
    op.drop_table("logistic_shipment_reservation_attempts")
    op.drop_table("logistic_shipment_lines")
    with op.batch_alter_table("logistic_shipments") as batch_op:
        batch_op.drop_index("ix_logistic_shipments_loading_idempotency_key")
        batch_op.drop_index("ix_logistic_shipments_loading_stock_document_id")
        batch_op.drop_index("ix_logistic_shipments_picking_idempotency_key")
        batch_op.drop_index("ix_logistic_shipments_picking_stock_document_id")
        batch_op.drop_constraint("fk_shipment_load_document", type_="foreignkey")
        batch_op.drop_constraint("fk_shipment_pick_document", type_="foreignkey")
        batch_op.drop_column("loading_command_hash")
        batch_op.drop_column("loading_idempotency_key")
        batch_op.drop_column("loading_stock_document_id")
        batch_op.drop_column("picking_command_hash")
        batch_op.drop_column("picking_idempotency_key")
        batch_op.drop_column("picking_stock_document_id")
