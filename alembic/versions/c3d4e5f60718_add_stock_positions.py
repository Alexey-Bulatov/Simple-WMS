"""add stock owners and canonical stock positions

Revision ID: c3d4e5f60718
Revises: 8a7b9c1d2e3f
Create Date: 2026-08-10 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f60718"
down_revision: Union[str, Sequence[str], None] = "8a7b9c1d2e3f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _migrate_logistic_unit_contents() -> None:
    connection = op.get_bind()
    invalid = connection.execute(
        sa.text(
            """
            SELECT content.id
            FROM logistic_unit_contents AS content
            JOIN products AS product ON product.id = content.product_id
            WHERE product.base_uom_id IS NULL
               OR content.uom_id <> product.base_uom_id
            LIMIT 1
            """
        )
    ).scalar_one_or_none()
    if invalid is not None:
        raise RuntimeError(
            "logistic_unit_contents row "
            f"{invalid} is not normalized to the product base unit"
        )

    owner_id = connection.execute(
        sa.text("SELECT id FROM stock_owners WHERE code = 'INTERNAL'")
    ).scalar_one()
    connection.execute(
        sa.text(
            """
            WITH RECURSIVE unit_tree AS (
                SELECT id, parent_unit_id, status AS root_status
                FROM logistic_units
                WHERE parent_unit_id IS NULL

                UNION ALL

                SELECT child.id, child.parent_unit_id, parent.root_status
                FROM logistic_units AS child
                JOIN unit_tree AS parent ON parent.id = child.parent_unit_id
            )
            INSERT INTO stock_positions (
                product_id,
                batch_id,
                owner_id,
                quality_status,
                serial_number,
                quantity,
                logistic_unit_id,
                location_id,
                created_at,
                updated_at
            )
            SELECT
                content.product_id,
                content.batch_id,
                :owner_id,
                COALESCE(batch.quality_status, 'released'),
                NULL,
                content.quantity,
                content.logistic_unit_id,
                NULL,
                content.added_at,
                content.added_at
            FROM logistic_unit_contents AS content
            JOIN unit_tree ON unit_tree.id = content.logistic_unit_id
            LEFT JOIN batches AS batch ON batch.id = content.batch_id
            WHERE unit_tree.root_status NOT IN ('SHIPPED', 'WRITTEN_OFF', 'DISASSEMBLED')
            """
        ),
        {"owner_id": owner_id},
    )


def upgrade() -> None:
    op.create_table(
        "stock_owners",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("is_internal", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_stock_owners_code"), "stock_owners", ["code"], unique=True)
    op.create_index(
        op.f("ix_stock_owners_is_internal"),
        "stock_owners",
        ["is_internal"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stock_owners_is_active"),
        "stock_owners",
        ["is_active"],
        unique=False,
    )
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            INSERT INTO stock_owners (code, name, is_internal, is_active, created_at)
            VALUES ('INTERNAL', 'Собственная организация', true, true, CURRENT_TIMESTAMP)
            """
        )
    )

    op.create_table(
        "stock_positions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("quality_status", sa.String(length=40), nullable=False),
        sa.Column("serial_number", sa.String(length=120), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("logistic_unit_id", sa.Integer(), nullable=True),
        sa.Column("location_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_stock_position_quantity"),
        sa.CheckConstraint(
            "serial_number IS NULL OR quantity = 1",
            name="ck_stock_position_serial_quantity",
        ),
        sa.CheckConstraint(
            "((logistic_unit_id IS NOT NULL AND location_id IS NULL) OR "
            "(logistic_unit_id IS NULL AND location_id IS NOT NULL))",
            name="ck_stock_position_single_holder",
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.ForeignKeyConstraint(
            ["logistic_unit_id"],
            ["logistic_units.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["stock_owners.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "product_id",
        "batch_id",
        "owner_id",
        "quality_status",
        "serial_number",
        "logistic_unit_id",
        "location_id",
    ):
        op.create_index(
            op.f(f"ix_stock_positions_{column}"),
            "stock_positions",
            [column],
            unique=False,
        )
    op.create_index(
        "uq_stock_position_unit_batch",
        "stock_positions",
        ["logistic_unit_id", "product_id", "batch_id", "owner_id", "quality_status"],
        unique=True,
        sqlite_where=sa.text(
            "logistic_unit_id IS NOT NULL AND batch_id IS NOT NULL AND serial_number IS NULL"
        ),
        postgresql_where=sa.text(
            "logistic_unit_id IS NOT NULL AND batch_id IS NOT NULL AND serial_number IS NULL"
        ),
    )
    op.create_index(
        "uq_stock_position_unit_no_batch",
        "stock_positions",
        ["logistic_unit_id", "product_id", "owner_id", "quality_status"],
        unique=True,
        sqlite_where=sa.text(
            "logistic_unit_id IS NOT NULL AND batch_id IS NULL AND serial_number IS NULL"
        ),
        postgresql_where=sa.text(
            "logistic_unit_id IS NOT NULL AND batch_id IS NULL AND serial_number IS NULL"
        ),
    )
    op.create_index(
        "uq_stock_position_location_batch",
        "stock_positions",
        ["location_id", "product_id", "batch_id", "owner_id", "quality_status"],
        unique=True,
        sqlite_where=sa.text(
            "location_id IS NOT NULL AND batch_id IS NOT NULL AND serial_number IS NULL"
        ),
        postgresql_where=sa.text(
            "location_id IS NOT NULL AND batch_id IS NOT NULL AND serial_number IS NULL"
        ),
    )
    op.create_index(
        "uq_stock_position_location_no_batch",
        "stock_positions",
        ["location_id", "product_id", "owner_id", "quality_status"],
        unique=True,
        sqlite_where=sa.text(
            "location_id IS NOT NULL AND batch_id IS NULL AND serial_number IS NULL"
        ),
        postgresql_where=sa.text(
            "location_id IS NOT NULL AND batch_id IS NULL AND serial_number IS NULL"
        ),
    )
    op.create_index(
        "uq_stock_position_product_serial_owner",
        "stock_positions",
        ["product_id", "serial_number", "owner_id"],
        unique=True,
        sqlite_where=sa.text("serial_number IS NOT NULL"),
        postgresql_where=sa.text("serial_number IS NOT NULL"),
    )
    _migrate_logistic_unit_contents()


def downgrade() -> None:
    op.drop_table("stock_positions")
    op.drop_table("stock_owners")
