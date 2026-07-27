"""add logistic inventory

Revision ID: d95a7b3e41c2
Revises: c84f05a726d3
Create Date: 2026-07-27 23:05:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d95a7b3e41c2"
down_revision: Union[str, Sequence[str], None] = "c84f05a726d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "logistic_inventories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("inventory_uid", sa.String(length=40), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("scope_parameters", sa.JSON(), nullable=False),
        sa.Column("current_location_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "OPEN",
                "COMPLETED",
                name="logisticinventorystatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("actor", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["current_location_id"], ["locations.id"]),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_logistic_inventories_inventory_uid"),
        "logistic_inventories",
        ["inventory_uid"],
        unique=True,
    )
    op.create_index(
        op.f("ix_logistic_inventories_scope_type"),
        "logistic_inventories",
        ["scope_type"],
    )
    op.create_index(
        op.f("ix_logistic_inventories_status"),
        "logistic_inventories",
        ["status"],
    )
    op.create_index(
        op.f("ix_logistic_inventories_warehouse_id"),
        "logistic_inventories",
        ["warehouse_id"],
    )

    op.create_table(
        "logistic_inventory_locations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("inventory_id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("expected_unit_count", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "UNCHECKED",
                "CHECKED",
                "PROBLEM",
                name="logisticinventorylocationstatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checked_by", sa.String(length=80), nullable=True),
        sa.ForeignKeyConstraint(["inventory_id"], ["logistic_inventories.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "inventory_id",
            "location_id",
            name="uq_logistic_inventory_location",
        ),
    )
    op.create_index(
        op.f("ix_logistic_inventory_locations_inventory_id"),
        "logistic_inventory_locations",
        ["inventory_id"],
    )
    op.create_index(
        op.f("ix_logistic_inventory_locations_location_id"),
        "logistic_inventory_locations",
        ["location_id"],
    )
    op.create_index(
        op.f("ix_logistic_inventory_locations_status"),
        "logistic_inventory_locations",
        ["status"],
    )

    op.create_table(
        "logistic_inventory_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("inventory_id", sa.Integer(), nullable=False),
        sa.Column("logistic_unit_id", sa.Integer(), nullable=False),
        sa.Column("expected_location_id", sa.Integer(), nullable=True),
        sa.Column("actual_location_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "EXPECTED",
                "SCANNED",
                "MISSING",
                "EXTRA",
                "WRONG_LOCATION",
                name="logisticinventorylinestatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_action", sa.String(length=40), nullable=True),
        sa.Column("resolution_actor", sa.String(length=80), nullable=True),
        sa.Column("resolution_reason", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["actual_location_id"], ["locations.id"]),
        sa.ForeignKeyConstraint(["expected_location_id"], ["locations.id"]),
        sa.ForeignKeyConstraint(["inventory_id"], ["logistic_inventories.id"]),
        sa.ForeignKeyConstraint(["logistic_unit_id"], ["logistic_units.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "inventory_id",
            "logistic_unit_id",
            name="uq_logistic_inventory_unit",
        ),
    )
    op.create_index(
        op.f("ix_logistic_inventory_lines_actual_location_id"),
        "logistic_inventory_lines",
        ["actual_location_id"],
    )
    op.create_index(
        op.f("ix_logistic_inventory_lines_expected_location_id"),
        "logistic_inventory_lines",
        ["expected_location_id"],
    )
    op.create_index(
        op.f("ix_logistic_inventory_lines_inventory_id"),
        "logistic_inventory_lines",
        ["inventory_id"],
    )
    op.create_index(
        op.f("ix_logistic_inventory_lines_logistic_unit_id"),
        "logistic_inventory_lines",
        ["logistic_unit_id"],
    )
    op.create_index(
        op.f("ix_logistic_inventory_lines_status"),
        "logistic_inventory_lines",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_logistic_inventory_lines_status"),
        table_name="logistic_inventory_lines",
    )
    op.drop_index(
        op.f("ix_logistic_inventory_lines_logistic_unit_id"),
        table_name="logistic_inventory_lines",
    )
    op.drop_index(
        op.f("ix_logistic_inventory_lines_inventory_id"),
        table_name="logistic_inventory_lines",
    )
    op.drop_index(
        op.f("ix_logistic_inventory_lines_expected_location_id"),
        table_name="logistic_inventory_lines",
    )
    op.drop_index(
        op.f("ix_logistic_inventory_lines_actual_location_id"),
        table_name="logistic_inventory_lines",
    )
    op.drop_table("logistic_inventory_lines")

    op.drop_index(
        op.f("ix_logistic_inventory_locations_status"),
        table_name="logistic_inventory_locations",
    )
    op.drop_index(
        op.f("ix_logistic_inventory_locations_location_id"),
        table_name="logistic_inventory_locations",
    )
    op.drop_index(
        op.f("ix_logistic_inventory_locations_inventory_id"),
        table_name="logistic_inventory_locations",
    )
    op.drop_table("logistic_inventory_locations")

    op.drop_index(
        op.f("ix_logistic_inventories_warehouse_id"),
        table_name="logistic_inventories",
    )
    op.drop_index(
        op.f("ix_logistic_inventories_status"),
        table_name="logistic_inventories",
    )
    op.drop_index(
        op.f("ix_logistic_inventories_scope_type"),
        table_name="logistic_inventories",
    )
    op.drop_index(
        op.f("ix_logistic_inventories_inventory_uid"),
        table_name="logistic_inventories",
    )
    op.drop_table("logistic_inventories")
