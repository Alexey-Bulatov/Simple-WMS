"""add logistic documents

Revision ID: c84f05a726d3
Revises: b72ce41f8a10
Create Date: 2026-07-27 22:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c84f05a726d3"
down_revision: Union[str, Sequence[str], None] = "b72ce41f8a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "logistic_shipments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shipment_uid", sa.String(length=40), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("customer_name", sa.String(length=160), nullable=False),
        sa.Column("destination", sa.String(length=160), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "RESERVED",
                "EXPEDITION",
                "LOADING",
                "COMPLETED",
                "CANCELLED",
                name="logisticshipmentstatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("planned_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_logistic_shipments_shipment_uid"),
        "logistic_shipments",
        ["shipment_uid"],
        unique=True,
    )
    op.create_index(op.f("ix_logistic_shipments_status"), "logistic_shipments", ["status"])
    op.create_index(
        op.f("ix_logistic_shipments_warehouse_id"),
        "logistic_shipments",
        ["warehouse_id"],
    )

    op.create_table(
        "logistic_shipment_units",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shipment_id", sa.Integer(), nullable=False),
        sa.Column("logistic_unit_id", sa.Integer(), nullable=False),
        sa.Column("source_location_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("moved_to_expedition_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["logistic_unit_id"], ["logistic_units.id"]),
        sa.ForeignKeyConstraint(["shipment_id"], ["logistic_shipments.id"]),
        sa.ForeignKeyConstraint(["source_location_id"], ["locations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "shipment_id",
            "logistic_unit_id",
            name="uq_logistic_shipment_unit",
        ),
    )
    op.create_index(
        op.f("ix_logistic_shipment_units_logistic_unit_id"),
        "logistic_shipment_units",
        ["logistic_unit_id"],
    )
    op.create_index(
        op.f("ix_logistic_shipment_units_shipment_id"),
        "logistic_shipment_units",
        ["shipment_id"],
    )
    op.create_index(
        op.f("ix_logistic_shipment_units_status"),
        "logistic_shipment_units",
        ["status"],
    )

    op.create_table(
        "logistic_transfers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("transfer_uid", sa.String(length=40), nullable=False),
        sa.Column("source_warehouse_id", sa.Integer(), nullable=False),
        sa.Column("destination_warehouse_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "RESERVED",
                "EXPEDITION",
                "LOADING",
                "IN_TRANSIT",
                "RECEIVING",
                "COMPLETED",
                "CANCELLED",
                name="logistictransferstatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("planned_date", sa.Date(), nullable=True),
        sa.Column("vehicle_number", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["destination_warehouse_id"], ["warehouses.id"]),
        sa.ForeignKeyConstraint(["source_warehouse_id"], ["warehouses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_logistic_transfers_destination_warehouse_id"),
        "logistic_transfers",
        ["destination_warehouse_id"],
    )
    op.create_index(
        op.f("ix_logistic_transfers_source_warehouse_id"),
        "logistic_transfers",
        ["source_warehouse_id"],
    )
    op.create_index(op.f("ix_logistic_transfers_status"), "logistic_transfers", ["status"])
    op.create_index(
        op.f("ix_logistic_transfers_transfer_uid"),
        "logistic_transfers",
        ["transfer_uid"],
        unique=True,
    )

    op.create_table(
        "logistic_transfer_units",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("transfer_id", sa.Integer(), nullable=False),
        sa.Column("logistic_unit_id", sa.Integer(), nullable=False),
        sa.Column("source_location_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("moved_to_expedition_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["logistic_unit_id"], ["logistic_units.id"]),
        sa.ForeignKeyConstraint(["source_location_id"], ["locations.id"]),
        sa.ForeignKeyConstraint(["transfer_id"], ["logistic_transfers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "transfer_id",
            "logistic_unit_id",
            name="uq_logistic_transfer_unit",
        ),
    )
    op.create_index(
        op.f("ix_logistic_transfer_units_logistic_unit_id"),
        "logistic_transfer_units",
        ["logistic_unit_id"],
    )
    op.create_index(
        op.f("ix_logistic_transfer_units_status"),
        "logistic_transfer_units",
        ["status"],
    )
    op.create_index(
        op.f("ix_logistic_transfer_units_transfer_id"),
        "logistic_transfer_units",
        ["transfer_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_logistic_transfer_units_transfer_id"), table_name="logistic_transfer_units")
    op.drop_index(op.f("ix_logistic_transfer_units_status"), table_name="logistic_transfer_units")
    op.drop_index(
        op.f("ix_logistic_transfer_units_logistic_unit_id"),
        table_name="logistic_transfer_units",
    )
    op.drop_table("logistic_transfer_units")
    op.drop_index(op.f("ix_logistic_transfers_transfer_uid"), table_name="logistic_transfers")
    op.drop_index(op.f("ix_logistic_transfers_status"), table_name="logistic_transfers")
    op.drop_index(
        op.f("ix_logistic_transfers_source_warehouse_id"),
        table_name="logistic_transfers",
    )
    op.drop_index(
        op.f("ix_logistic_transfers_destination_warehouse_id"),
        table_name="logistic_transfers",
    )
    op.drop_table("logistic_transfers")

    op.drop_index(op.f("ix_logistic_shipment_units_status"), table_name="logistic_shipment_units")
    op.drop_index(
        op.f("ix_logistic_shipment_units_shipment_id"),
        table_name="logistic_shipment_units",
    )
    op.drop_index(
        op.f("ix_logistic_shipment_units_logistic_unit_id"),
        table_name="logistic_shipment_units",
    )
    op.drop_table("logistic_shipment_units")
    op.drop_index(
        op.f("ix_logistic_shipments_warehouse_id"),
        table_name="logistic_shipments",
    )
    op.drop_index(op.f("ix_logistic_shipments_status"), table_name="logistic_shipments")
    op.drop_index(
        op.f("ix_logistic_shipments_shipment_uid"),
        table_name="logistic_shipments",
    )
    op.drop_table("logistic_shipments")
