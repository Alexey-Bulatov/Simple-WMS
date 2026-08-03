"""add logistic unit instances

Revision ID: f3a91d7c5e42
Revises: e8b6f2c4d901
Create Date: 2026-07-27 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3a91d7c5e42"
down_revision: Union[str, Sequence[str], None] = "e8b6f2c4d901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "logistic_units",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("uid", sa.String(length=64), nullable=False),
        sa.Column("type_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "OPEN",
                "CLOSED",
                "AVAILABLE",
                "RESERVED",
                "PICKING",
                "EXPEDITION",
                "LOADED",
                "IN_TRANSIT",
                "QUARANTINE",
                "BLOCKED",
                "DISASSEMBLED",
                "WRITTEN_OFF",
                "SHIPPED",
                name="logisticunitstatus",
            ),
            nullable=False,
        ),
        sa.Column("parent_unit_id", sa.Integer(), nullable=True),
        sa.Column("current_location_id", sa.Integer(), nullable=True),
        sa.Column("measured_gross_weight", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("weight_uom_id", sa.Integer(), nullable=True),
        sa.Column("length_mm", sa.Integer(), nullable=True),
        sa.Column("width_mm", sa.Integer(), nullable=True),
        sa.Column("height_mm", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "measured_gross_weight IS NULL OR measured_gross_weight > 0",
            name="ck_logistic_unit_gross_weight",
        ),
        sa.CheckConstraint("height_mm IS NULL OR height_mm > 0", name="ck_logistic_unit_height"),
        sa.CheckConstraint("length_mm IS NULL OR length_mm > 0", name="ck_logistic_unit_length"),
        sa.CheckConstraint(
            "parent_unit_id IS NULL OR parent_unit_id <> id",
            name="ck_logistic_unit_no_self_parent",
        ),
        sa.CheckConstraint("width_mm IS NULL OR width_mm > 0", name="ck_logistic_unit_width"),
        sa.ForeignKeyConstraint(["current_location_id"], ["locations.id"]),
        sa.ForeignKeyConstraint(["parent_unit_id"], ["logistic_units.id"]),
        sa.ForeignKeyConstraint(["type_id"], ["logistic_unit_types.id"]),
        sa.ForeignKeyConstraint(["weight_uom_id"], ["units_of_measure.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_logistic_units_current_location_id"), "logistic_units", ["current_location_id"])
    op.create_index(op.f("ix_logistic_units_parent_unit_id"), "logistic_units", ["parent_unit_id"])
    op.create_index(op.f("ix_logistic_units_status"), "logistic_units", ["status"])
    op.create_index(op.f("ix_logistic_units_type_id"), "logistic_units", ["type_id"])
    op.create_index(op.f("ix_logistic_units_uid"), "logistic_units", ["uid"], unique=True)

    op.create_table(
        "logistic_unit_contents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("logistic_unit_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("uom_id", sa.Integer(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_logistic_unit_content_quantity"),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"]),
        sa.ForeignKeyConstraint(
            ["logistic_unit_id"],
            ["logistic_units.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["uom_id"], ["units_of_measure.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "logistic_unit_id",
            "product_id",
            "batch_id",
            "uom_id",
            name="uq_logistic_unit_content_line",
        ),
    )
    op.create_index(op.f("ix_logistic_unit_contents_batch_id"), "logistic_unit_contents", ["batch_id"])
    op.create_index(
        op.f("ix_logistic_unit_contents_logistic_unit_id"),
        "logistic_unit_contents",
        ["logistic_unit_id"],
    )
    op.create_index(op.f("ix_logistic_unit_contents_product_id"), "logistic_unit_contents", ["product_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_logistic_unit_contents_product_id"), table_name="logistic_unit_contents")
    op.drop_index(
        op.f("ix_logistic_unit_contents_logistic_unit_id"),
        table_name="logistic_unit_contents",
    )
    op.drop_index(op.f("ix_logistic_unit_contents_batch_id"), table_name="logistic_unit_contents")
    op.drop_table("logistic_unit_contents")

    op.drop_index(op.f("ix_logistic_units_uid"), table_name="logistic_units")
    op.drop_index(op.f("ix_logistic_units_type_id"), table_name="logistic_units")
    op.drop_index(op.f("ix_logistic_units_status"), table_name="logistic_units")
    op.drop_index(op.f("ix_logistic_units_parent_unit_id"), table_name="logistic_units")
    op.drop_index(op.f("ix_logistic_units_current_location_id"), table_name="logistic_units")
    op.drop_table("logistic_units")
    if op.get_bind().dialect.name == "postgresql":
        sa.Enum(name="logisticunitstatus").drop(op.get_bind(), checkfirst=True)
