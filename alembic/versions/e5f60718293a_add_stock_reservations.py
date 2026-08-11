"""add quantitative stock reservations

Revision ID: e5f60718293a
Revises: d4e5f6071829
Create Date: 2026-08-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f60718293a"
down_revision: Union[str, Sequence[str], None] = "d4e5f6071829"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stock_reservations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("uid", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("stock_position_id", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=True),
        sa.Column("serial_number", sa.String(length=120), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("quality_status", sa.String(length=40), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("base_uom_id", sa.Integer(), nullable=False),
        sa.Column("input_quantity", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("input_uom_id", sa.Integer(), nullable=False),
        sa.Column("conversion_factor", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("logistic_unit_id", sa.Integer(), nullable=True),
        sa.Column("location_id", sa.Integer(), nullable=True),
        sa.Column("logistic_unit_uid", sa.String(length=64), nullable=True),
        sa.Column("location_code", sa.String(length=120), nullable=True),
        sa.Column("reference_type", sa.String(length=40), nullable=False),
        sa.Column("reference_uid", sa.String(length=80), nullable=False),
        sa.Column("reference_line_uid", sa.String(length=80), nullable=True),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("command_hash", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("release_idempotency_key", sa.String(length=120), nullable=True),
        sa.Column("release_command_hash", sa.String(length=64), nullable=True),
        sa.Column("release_actor", sa.String(length=80), nullable=True),
        sa.Column("release_reason", sa.Text(), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_by_document_id", sa.Integer(), nullable=True),
        sa.CheckConstraint("quantity > 0", name="ck_stock_reservation_quantity"),
        sa.CheckConstraint(
            "input_quantity > 0",
            name="ck_stock_reservation_input_quantity",
        ),
        sa.CheckConstraint(
            "conversion_factor > 0",
            name="ck_stock_reservation_conversion_factor",
        ),
        sa.CheckConstraint(
            "NOT (logistic_unit_id IS NOT NULL AND location_id IS NOT NULL)",
            name="ck_stock_reservation_single_holder",
        ),
        sa.CheckConstraint(
            "((logistic_unit_uid IS NOT NULL AND location_code IS NULL) OR "
            "(logistic_unit_uid IS NULL AND location_code IS NOT NULL))",
            name="ck_stock_reservation_holder_snapshot",
        ),
        sa.ForeignKeyConstraint(["base_uom_id"], ["units_of_measure.id"]),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"]),
        sa.ForeignKeyConstraint(
            ["consumed_by_document_id"],
            ["stock_documents.id"],
        ),
        sa.ForeignKeyConstraint(["input_uom_id"], ["units_of_measure.id"]),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["locations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["logistic_unit_id"],
            ["logistic_units.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["stock_owners.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(
            ["stock_position_id"],
            ["stock_positions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "uid",
        "status",
        "stock_position_id",
        "product_id",
        "batch_id",
        "serial_number",
        "owner_id",
        "quality_status",
        "base_uom_id",
        "input_uom_id",
        "logistic_unit_id",
        "location_id",
        "logistic_unit_uid",
        "location_code",
        "reference_type",
        "reference_uid",
        "reference_line_uid",
        "idempotency_key",
        "actor",
        "release_idempotency_key",
        "consumed_by_document_id",
    ):
        op.create_index(
            op.f(f"ix_stock_reservations_{column}"),
            "stock_reservations",
            [column],
            unique=column in {"uid", "idempotency_key", "release_idempotency_key"},
        )


def downgrade() -> None:
    op.drop_table("stock_reservations")
