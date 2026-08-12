"""add logistic unit warehouse

Revision ID: c60718293a4b
Revises: b60718293a4b
"""

from alembic import op
import sqlalchemy as sa


revision = "c60718293a4b"
down_revision = "b60718293a4b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("logistic_units") as batch_op:
        batch_op.add_column(sa.Column("warehouse_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_logistic_units_warehouse_id_warehouses",
            "warehouses",
            ["warehouse_id"],
            ["id"],
        )
        batch_op.create_index("ix_logistic_units_warehouse_id", ["warehouse_id"])

    op.execute(
        sa.text(
            """
            UPDATE logistic_units
            SET warehouse_id = (
                SELECT locations.warehouse_id
                FROM locations
                WHERE locations.id = logistic_units.current_location_id
            )
            WHERE current_location_id IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE logistic_units
            SET warehouse_id = (SELECT MIN(id) FROM warehouses)
            WHERE warehouse_id IS NULL
              AND (SELECT COUNT(*) FROM warehouses) = 1
            """
        )
    )
    op.execute(
        sa.text(
            """
            WITH RECURSIVE unit_warehouses(id, warehouse_id) AS (
                SELECT id, warehouse_id
                FROM logistic_units
                WHERE parent_unit_id IS NULL
                UNION ALL
                SELECT child.id, COALESCE(child.warehouse_id, parent.warehouse_id)
                FROM logistic_units AS child
                JOIN unit_warehouses AS parent ON parent.id = child.parent_unit_id
            )
            UPDATE logistic_units
            SET warehouse_id = (
                SELECT unit_warehouses.warehouse_id
                FROM unit_warehouses
                WHERE unit_warehouses.id = logistic_units.id
            )
            WHERE id IN (
                SELECT id FROM unit_warehouses WHERE warehouse_id IS NOT NULL
            )
            """
        )
    )

    with op.batch_alter_table("stock_movements") as batch_op:
        batch_op.add_column(sa.Column("source_warehouse_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("destination_warehouse_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_stock_movements_source_warehouse_id_warehouses",
            "warehouses",
            ["source_warehouse_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_stock_movements_destination_warehouse_id_warehouses",
            "warehouses",
            ["destination_warehouse_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_stock_movements_source_warehouse_id",
            ["source_warehouse_id"],
        )
        batch_op.create_index(
            "ix_stock_movements_destination_warehouse_id",
            ["destination_warehouse_id"],
        )

    for side in ("source", "destination"):
        op.execute(
            sa.text(
                f"""
                UPDATE stock_movements
                SET {side}_warehouse_id = COALESCE(
                    (
                        SELECT locations.warehouse_id
                        FROM locations
                        WHERE locations.id = stock_movements.{side}_location_id
                    ),
                    (
                        SELECT COALESCE(
                            logistic_units.warehouse_id,
                            unit_locations.warehouse_id
                        )
                        FROM logistic_units
                        LEFT JOIN locations AS unit_locations
                            ON unit_locations.id = logistic_units.current_location_id
                        WHERE logistic_units.id = stock_movements.{side}_logistic_unit_id
                    )
                )
                """
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("stock_movements") as batch_op:
        batch_op.drop_index("ix_stock_movements_destination_warehouse_id")
        batch_op.drop_index("ix_stock_movements_source_warehouse_id")
        batch_op.drop_constraint(
            "fk_stock_movements_destination_warehouse_id_warehouses",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_stock_movements_source_warehouse_id_warehouses",
            type_="foreignkey",
        )
        batch_op.drop_column("destination_warehouse_id")
        batch_op.drop_column("source_warehouse_id")

    with op.batch_alter_table("logistic_units") as batch_op:
        batch_op.drop_index("ix_logistic_units_warehouse_id")
        batch_op.drop_constraint(
            "fk_logistic_units_warehouse_id_warehouses",
            type_="foreignkey",
        )
        batch_op.drop_column("warehouse_id")
