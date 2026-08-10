"""add immutable stock documents and movements

Revision ID: d4e5f6071829
Revises: c3d4e5f60718
Create Date: 2026-08-10 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6071829"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f60718"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OPENING_DOCUMENT_UID = "OPENING-C3D4E5F60718"


def _create_opening_movements() -> None:
    connection = op.get_bind()
    position_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM stock_positions")
    ).scalar_one()
    if position_count == 0:
        return

    connection.execute(
        sa.text(
            """
            INSERT INTO stock_documents (
                uid,
                document_type,
                status,
                reference_type,
                reference_uid,
                idempotency_key,
                reversal_of_id,
                actor,
                reason,
                attributes,
                created_at,
                posted_at,
                reversed_at
            ) VALUES (
                :uid,
                'opening_balance',
                'POSTED',
                'migration',
                'c3d4e5f60718',
                'migration:d4e5f6071829:opening',
                NULL,
                'migration',
                'Начальный остаток перед запуском журнала движений',
                '{"migration":"d4e5f6071829"}',
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                NULL
            )
            """
        ),
        {"uid": OPENING_DOCUMENT_UID},
    )
    document_id = connection.execute(
        sa.text("SELECT id FROM stock_documents WHERE uid = :uid"),
        {"uid": OPENING_DOCUMENT_UID},
    ).scalar_one()
    connection.execute(
        sa.text(
            """
            INSERT INTO stock_movements (
                document_id,
                sequence_no,
                product_id,
                batch_id,
                serial_number,
                owner_id,
                source_quality_status,
                destination_quality_status,
                quantity,
                base_uom_id,
                input_quantity,
                input_uom_id,
                conversion_factor,
                source_logistic_unit_id,
                source_location_id,
                destination_logistic_unit_id,
                destination_location_id,
                occurred_at
            )
            SELECT
                :document_id,
                ROW_NUMBER() OVER (ORDER BY position.id),
                position.product_id,
                position.batch_id,
                position.serial_number,
                position.owner_id,
                NULL,
                position.quality_status,
                position.quantity,
                product.base_uom_id,
                position.quantity,
                product.base_uom_id,
                1,
                NULL,
                NULL,
                position.logistic_unit_id,
                position.location_id,
                position.created_at
            FROM stock_positions AS position
            JOIN products AS product ON product.id = position.product_id
            ORDER BY position.id
            """
        ),
        {"document_id": document_id},
    )


def upgrade() -> None:
    op.create_table(
        "stock_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("uid", sa.String(length=64), nullable=False),
        sa.Column("document_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("reference_type", sa.String(length=40), nullable=True),
        sa.Column("reference_uid", sa.String(length=80), nullable=True),
        sa.Column("idempotency_key", sa.String(length=120), nullable=True),
        sa.Column("reversal_of_id", sa.Integer(), nullable=True),
        sa.Column("actor", sa.String(length=80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["reversal_of_id"], ["stock_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column, unique in (
        ("uid", True),
        ("document_type", False),
        ("status", False),
        ("reference_type", False),
        ("reference_uid", False),
        ("idempotency_key", True),
        ("reversal_of_id", True),
        ("actor", False),
    ):
        op.create_index(
            op.f(f"ix_stock_documents_{column}"),
            "stock_documents",
            [column],
            unique=unique,
        )

    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=True),
        sa.Column("serial_number", sa.String(length=120), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("source_quality_status", sa.String(length=40), nullable=True),
        sa.Column("destination_quality_status", sa.String(length=40), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("base_uom_id", sa.Integer(), nullable=False),
        sa.Column("input_quantity", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("input_uom_id", sa.Integer(), nullable=False),
        sa.Column("conversion_factor", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("source_logistic_unit_id", sa.Integer(), nullable=True),
        sa.Column("source_location_id", sa.Integer(), nullable=True),
        sa.Column("destination_logistic_unit_id", sa.Integer(), nullable=True),
        sa.Column("destination_location_id", sa.Integer(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_stock_movement_quantity"),
        sa.CheckConstraint("input_quantity > 0", name="ck_stock_movement_input_quantity"),
        sa.CheckConstraint("conversion_factor > 0", name="ck_stock_movement_conversion_factor"),
        sa.CheckConstraint(
            "serial_number IS NULL OR quantity = 1",
            name="ck_stock_movement_serial_quantity",
        ),
        sa.CheckConstraint(
            "NOT (source_logistic_unit_id IS NOT NULL AND source_location_id IS NOT NULL)",
            name="ck_stock_movement_single_source",
        ),
        sa.CheckConstraint(
            "NOT (destination_logistic_unit_id IS NOT NULL AND destination_location_id IS NOT NULL)",
            name="ck_stock_movement_single_destination",
        ),
        sa.CheckConstraint(
            "source_logistic_unit_id IS NOT NULL OR source_location_id IS NOT NULL OR "
            "destination_logistic_unit_id IS NOT NULL OR destination_location_id IS NOT NULL",
            name="ck_stock_movement_has_holder",
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
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["stock_documents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["input_uom_id"], ["units_of_measure.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["stock_owners.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["source_location_id"], ["locations.id"]),
        sa.ForeignKeyConstraint(["source_logistic_unit_id"], ["logistic_units.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "sequence_no",
            name="uq_stock_movement_document_sequence",
        ),
    )
    for column in (
        "document_id",
        "product_id",
        "batch_id",
        "serial_number",
        "owner_id",
        "source_quality_status",
        "destination_quality_status",
        "base_uom_id",
        "input_uom_id",
        "source_logistic_unit_id",
        "source_location_id",
        "destination_logistic_unit_id",
        "destination_location_id",
        "occurred_at",
    ):
        op.create_index(
            op.f(f"ix_stock_movements_{column}"),
            "stock_movements",
            [column],
            unique=False,
        )
    _create_opening_movements()


def downgrade() -> None:
    op.drop_table("stock_movements")
    op.drop_table("stock_documents")
