"""add product packagings and normalize logistic unit content

Revision ID: 8a7b9c1d2e3f
Revises: 6c0037a4f16a
Create Date: 2026-08-09 12:00:00.000000

"""
from decimal import Decimal
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8a7b9c1d2e3f"
down_revision: Union[str, Sequence[str], None] = "6c0037a4f16a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _decimal(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _normalize_logistic_unit_content() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT
                content.id,
                content.logistic_unit_id,
                content.product_id,
                content.batch_id,
                content.quantity,
                content.uom_id,
                product.base_uom_id,
                source_uom.dimension AS source_dimension,
                source_uom.factor_to_base AS source_factor,
                base_uom.dimension AS base_dimension,
                base_uom.factor_to_base AS base_factor,
                base_uom.decimal_precision AS base_precision
            FROM logistic_unit_contents AS content
            JOIN products AS product ON product.id = content.product_id
            JOIN units_of_measure AS source_uom ON source_uom.id = content.uom_id
            LEFT JOIN units_of_measure AS base_uom ON base_uom.id = product.base_uom_id
            ORDER BY content.id
            """
        )
    ).mappings()

    groups: dict[tuple[int, int, int | None, int], list[tuple[int, Decimal]]] = {}
    for row in rows:
        target_uom_id = row["base_uom_id"] or row["uom_id"]
        quantity = _decimal(row["quantity"])
        if row["base_uom_id"] is not None:
            if row["source_dimension"] != row["base_dimension"]:
                raise RuntimeError(
                    "logistic_unit_contents row "
                    f"{row['id']} has an incompatible product base unit"
                )
            converted = (
                quantity
                * _decimal(row["source_factor"])
                / _decimal(row["base_factor"])
            )
            quantum = Decimal("1").scaleb(-int(row["base_precision"]))
            quantity = converted.quantize(quantum)
            if quantity != converted:
                raise RuntimeError(
                    "logistic_unit_contents row "
                    f"{row['id']} cannot be represented in the product base unit"
                )
        key = (
            row["logistic_unit_id"],
            row["product_id"],
            row["batch_id"],
            target_uom_id,
        )
        groups.setdefault(key, []).append((row["id"], quantity))

    for (*_, target_uom_id), items in groups.items():
        keeper_id = items[0][0]
        total = sum((quantity for _, quantity in items), Decimal("0"))
        for redundant_id, _ in items[1:]:
            connection.execute(
                sa.text("DELETE FROM logistic_unit_contents WHERE id = :id"),
                {"id": redundant_id},
            )
        connection.execute(
            sa.text(
                """
                UPDATE logistic_unit_contents
                SET quantity = :quantity, uom_id = :uom_id
                WHERE id = :id
                """
            ),
            {"quantity": str(total), "uom_id": target_uom_id, "id": keeper_id},
        )


def upgrade() -> None:
    op.create_table(
        "product_packagings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("uom_id", sa.Integer(), nullable=False),
        sa.Column("base_quantity", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("barcode", sa.String(length=120), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("base_quantity > 0", name="ck_product_packaging_base_quantity"),
        sa.CheckConstraint("quantity > 0", name="ck_product_packaging_quantity"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["uom_id"], ["units_of_measure.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "code", name="uq_product_packaging_code"),
    )
    op.create_index(
        op.f("ix_product_packagings_barcode"),
        "product_packagings",
        ["barcode"],
        unique=True,
    )
    op.create_index(
        op.f("ix_product_packagings_code"),
        "product_packagings",
        ["code"],
        unique=False,
    )
    op.create_index(
        op.f("ix_product_packagings_is_active"),
        "product_packagings",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        op.f("ix_product_packagings_product_id"),
        "product_packagings",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_product_packagings_uom_id"),
        "product_packagings",
        ["uom_id"],
        unique=False,
    )
    _normalize_logistic_unit_content()


def downgrade() -> None:
    op.drop_index(op.f("ix_product_packagings_uom_id"), table_name="product_packagings")
    op.drop_index(op.f("ix_product_packagings_product_id"), table_name="product_packagings")
    op.drop_index(op.f("ix_product_packagings_is_active"), table_name="product_packagings")
    op.drop_index(op.f("ix_product_packagings_code"), table_name="product_packagings")
    op.drop_index(op.f("ix_product_packagings_barcode"), table_name="product_packagings")
    op.drop_table("product_packagings")
